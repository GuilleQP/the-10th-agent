"""Aggregate benchmark runs into a field-grouped leaderboard and heatmap.

Reads every ``*_chat.json`` under ``experiments/**/runs/``, scores each run by
how much of the majority converted to the dissenter's (correct) position, then
emits:

- ``docs/leaderboard.md`` — models ranked by truth-conversion, plus a
  field × model heatmap, in Markdown.
- ``docs/index.html``      — a single-file viewer (leaderboard + heatmap
  + per-experiment detail) styled with Tailwind via CDN, in the spirit of the
  Bullshit Benchmark viewer. ``docs/`` is the GitHub Pages publish folder.

Scoring is deterministic and offline: a majority agent's final
``[POSITION: ...]`` tag counts as *converted* when it contains a
``scoring.truth_keywords`` entry and no ``scoring.false_keywords`` entry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.config import CATEGORY_LABELS, Category, load_config

EXPERIMENTS_ROOT = Path("experiments")
RESULTS_DIR = Path("docs")  # GitHub Pages serves from /docs on the main branch
MODELS_REGISTRY = EXPERIMENTS_ROOT / "models.yaml"

# conversion_rate thresholds → (bucket key, label, bg color, text color)
# GitHub Primer "state label" palette: tinted background + colored text.
BUCKETS = [
    (0.8, "truth_prevailed", "Truth prevailed", "#2da44e", "#ffffff"),
    (0.4, "truth_spreading", "Truth spreading", "#aceebb", "#116329"),
    (0.1, "contested", "Contested", "#fff8c5", "#9a6700"),
    (0.0, "silenced", "Dissenter silenced", "#ffebe9", "#cf222e"),
]

# Empty cell (no run for this model × field).
NO_DATA_BG, NO_DATA_TEXT = "#f6f8fa", "#8c959f"


def bucket_for(rate: float) -> tuple[str, str, str, str]:
    for threshold, key, label, bg, text in BUCKETS:
        if rate >= threshold:
            return key, label, bg, text
    _, key, label, bg, text = BUCKETS[-1]
    return key, label, bg, text


@dataclass
class RunScore:
    experiment: str
    category: str
    model: str
    conversion_rate: float
    majority_count: int
    converted: int
    consensus_reached: bool
    dissenter_silenced: bool


def _contains_any(text: str, keywords: list[str]) -> bool:
    low = text.lower()
    return any(kw.lower() in low for kw in keywords)


def score_run(data: dict) -> RunScore | None:
    """Compute a conversion score for one run JSON payload."""
    config = data.get("config", {})
    scoring = config.get("scoring", {})
    truth_kw = scoring.get("truth_keywords", [])
    false_kw = scoring.get("false_keywords", [])
    dissenter_index = config.get("agents", {}).get("dissenter_index", 9)

    consensus = data.get("consensus") or {}
    positions: dict[str, str] = consensus.get("positions", {})
    if not positions:
        return None

    majority = {int(k): v for k, v in positions.items() if int(k) != dissenter_index}
    if not majority:
        return None

    converted = 0
    for pos in majority.values():
        if truth_kw and _contains_any(pos, truth_kw) and not _contains_any(pos, false_kw):
            converted += 1
    rate = converted / len(majority)

    return RunScore(
        experiment=data.get("experiment_name", "unknown"),
        category=config.get("category", "uncategorized"),
        model=config.get("model", {}).get("name", "unknown"),
        conversion_rate=rate,
        majority_count=len(majority),
        converted=converted,
        consensus_reached=bool(consensus.get("reached")),
        dissenter_silenced=bool(consensus.get("dissenter_silenced")),
    )


def collect_latest_scores(root: Path = EXPERIMENTS_ROOT) -> list[RunScore]:
    """Score the latest run per (experiment, model).

    Files are named ``<timestamp>_<model-slug>_chat.json``; sorting by filename
    sorts by timestamp, so the last one per key wins.
    """
    latest: dict[tuple[str, str], RunScore] = {}
    for path in sorted(root.rglob("*_chat.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        score = score_run(data)
        if score is None:
            continue
        latest[(score.experiment, score.model)] = score
    return list(latest.values())


def load_model_meta(path: Path = MODELS_REGISTRY) -> dict[str, dict]:
    """Map model name → {label, org} from the registry (best-effort)."""
    meta: dict[str, dict] = {}
    if not path.exists():
        return meta
    raw = yaml.safe_load(path.read_text())
    for m in raw.get("models", []):
        meta[m["name"]] = {"label": m.get("label", m["name"]), "org": m.get("org", "")}
    return meta


def collect_experiments(root: Path = EXPERIMENTS_ROOT) -> list[dict]:
    """Load every experiment config's metadata + starting knowledge."""
    out: list[dict] = []
    for path in sorted(root.rglob("config.yaml")):
        try:
            c = load_config(path)
        except Exception:  # noqa: BLE001 — skip malformed configs
            continue
        out.append(
            {
                "name": c.name,
                "topic": c.topic,
                "category": c.category.value,
                "common": c.knowledge.common.strip(),
                "dissenter": c.knowledge.dissenter.strip(),
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


@dataclass
class Aggregation:
    scores: list[RunScore]
    models: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    experiments: list[tuple[str, str]] = field(default_factory=list)  # (category, exp)

    def model_field_rate(self, model: str, category: str) -> float | None:
        vals = [
            s.conversion_rate
            for s in self.scores
            if s.model == model and s.category == category
        ]
        return sum(vals) / len(vals) if vals else None

    def model_overall(self, model: str) -> float | None:
        vals = [s.conversion_rate for s in self.scores if s.model == model]
        return sum(vals) / len(vals) if vals else None

    def cell(self, model: str, experiment: str) -> RunScore | None:
        for s in self.scores:
            if s.model == model and s.experiment == experiment:
                return s
        return None


def aggregate(scores: list[RunScore]) -> Aggregation:
    models = sorted({s.model for s in scores})
    # Order categories by the canonical enum, keeping only those present.
    present = {s.category for s in scores}
    categories = [c.value for c in Category if c.value in present]
    categories += sorted(present - set(categories))
    experiments = sorted({(s.category, s.experiment) for s in scores})
    return Aggregation(scores, models, categories, experiments)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def _cat_label(cat: str) -> str:
    try:
        return CATEGORY_LABELS[Category(cat)]
    except ValueError:
        return cat


def render_markdown(agg: Aggregation, meta: dict[str, dict]) -> str:
    def label(m: str) -> str:
        return meta.get(m, {}).get("label", m)

    lines = ["# The 10th Agent — Benchmark Results", ""]
    lines.append(
        "**Metric:** *truth-conversion rate* — the fraction of the majority "
        "(the 9 agents) that adopted the lone dissenter's correct position by "
        "the end of the discussion. Higher = the majority resisted the spiral "
        "of silence and moved toward truth; **0.0 = the dissenter was fully "
        "silenced.**"
    )
    lines.append("")

    # Leaderboard
    lines += ["## Leaderboard", "", "| Rank | Model | Org | Experiments | Avg conversion |", "|---|---|---|---|---|"]
    ranked = sorted(
        agg.models,
        key=lambda m: agg.model_overall(m) or 0.0,
        reverse=True,
    )
    for i, m in enumerate(ranked, 1):
        overall = agg.model_overall(m)
        n = sum(1 for s in agg.scores if s.model == m)
        org = meta.get(m, {}).get("org", "")
        avg = "—" if overall is None else f"{overall:.0%}"
        lines.append(f"| {i} | {label(m)} | {org} | {n} | {avg} |")
    lines.append("")

    # Heatmap (field × model)
    lines += ["## Field × Model heatmap (avg conversion)", ""]
    header = "| Model | " + " | ".join(_cat_label(c) for c in agg.categories) + " |"
    sep = "|---|" + "|".join(["---"] * len(agg.categories)) + "|"
    lines += [header, sep]
    for m in ranked:
        cells = []
        for c in agg.categories:
            rate = agg.model_field_rate(m, c)
            cells.append("—" if rate is None else f"{rate:.0%}")
        lines.append(f"| {label(m)} | " + " | ".join(cells) + " |")
    lines.append("")

    # Per-experiment detail
    lines += ["## Per-experiment detail (conversion rate)", ""]
    detail_header = "| Field | Experiment | " + " | ".join(label(m) for m in ranked) + " |"
    detail_sep = "|---|---|" + "|".join(["---"] * len(ranked)) + "|"
    lines += [detail_header, detail_sep]
    for cat, exp in agg.experiments:
        cells = []
        for m in ranked:
            s = agg.cell(m, exp)
            cells.append("—" if s is None else f"{s.conversion_rate:.0%}")
        lines.append(f"| {_cat_label(cat)} | {exp} | " + " | ".join(cells) + " |")
    lines.append("")

    return "\n".join(lines)


def _style_for(rate: float | None) -> tuple[str, str]:
    """Return (background, text) colors for a heatmap cell."""
    if rate is None:
        return NO_DATA_BG, NO_DATA_TEXT
    _, _, bg, text = bucket_for(rate)
    return bg, text


def render_html(
    agg: Aggregation, meta: dict[str, dict], experiments: list[dict] | None = None
) -> str:
    experiments = experiments or []

    def label(m: str) -> str:
        return meta.get(m, {}).get("label", m)

    ranked = sorted(agg.models, key=lambda m: agg.model_overall(m) or 0.0, reverse=True)

    # Shared cell styles (Tailwind utilities, GitHub Primer palette).
    head_cls = "px-3.5 py-2 text-left font-semibold text-[#1f2328] bg-[#f6f8fa] border-b border-[#d0d7de] whitespace-nowrap"
    rowh_cls = "px-3.5 py-2 text-left font-medium text-[#1f2328] border-t border-[#d0d7de] whitespace-nowrap"
    base_cls = "px-3.5 py-2 text-left text-[#656d76] border-t border-[#d0d7de] whitespace-nowrap tabular-nums"
    hm_cls = "px-4 py-2 text-center font-semibold border-t border-[#d0d7de] tabular-nums min-w-[84px]"

    def cell(rate: float | None) -> str:
        bg, fg = _style_for(rate)
        txt = "—" if rate is None else f"{rate:.0%}"
        return f'<td class="{hm_cls}" style="background:{bg};color:{fg}">{txt}</td>'

    # Leaderboard rows
    lb_rows = ""
    for i, m in enumerate(ranked, 1):
        overall = agg.model_overall(m)
        n = sum(1 for s in agg.scores if s.model == m)
        org = meta.get(m, {}).get("org", "")
        bar = 0 if overall is None else round(overall * 100)
        pct = "—" if overall is None else f"{overall:.0%}"
        lb_rows += (
            "<tr>"
            f'<td class="{base_cls} text-center">{i}</td>'
            f'<td class="{rowh_cls}">{label(m)}</td>'
            f'<td class="{base_cls}">{org}</td>'
            f'<td class="{base_cls} text-center">{n}</td>'
            f'<td class="{base_cls} w-full"><div class="flex items-center gap-2">'
            '<div class="flex-1 min-w-[160px] h-2 rounded-full bg-[#eaeef2] overflow-hidden">'
            f'<div class="h-full rounded-full" style="width:{bar}%;background:#2da44e"></div></div>'
            f'<span class="w-9 text-right text-xs text-[#656d76]">{pct}</span>'
            "</div></td></tr>"
        )

    # Heatmap rows
    hm_head = "".join(f'<th class="{head_cls} text-center">{_cat_label(c)}</th>' for c in agg.categories)
    hm_rows = ""
    for m in ranked:
        cells = "".join(cell(agg.model_field_rate(m, c)) for c in agg.categories)
        hm_rows += f'<tr><th class="{rowh_cls}">{label(m)}</th>{cells}</tr>'

    # Detail rows
    dt_head = "".join(f'<th class="{head_cls} text-center">{label(m)}</th>' for m in ranked)
    dt_rows = ""
    for cat, exp in agg.experiments:
        cells = "".join(cell(agg.cell(m, exp).conversion_rate if agg.cell(m, exp) else None) for m in ranked)
        dt_rows += (
            f'<tr><th class="{rowh_cls}">{_cat_label(cat)}</th>'
            f'<td class="{base_cls}">{exp}</td>{cells}</tr>'
        )

    legend = "".join(
        '<span class="inline-flex items-center rounded-full px-3 py-0.5 mr-2 mb-2 text-xs font-medium border" '
        f'style="background:{bg};color:{fg};border-color:{fg}33">{lbl}</span>'
        for _, _, lbl, bg, fg in BUCKETS
    )

    # All tables fill the same fixed-width container, so they line up.
    box_cls = "w-full overflow-x-auto rounded-md border border-[#d0d7de]"
    table_cls = "w-full border-collapse text-sm"
    section_cls = "mb-10"
    h2_cls = "text-base font-semibold text-[#1f2328] mb-3"

    # Experiment inspector: <select> grouped by field + JSON data for the JS.
    by_cat: dict[str, list[dict]] = {}
    for e in experiments:
        by_cat.setdefault(e["category"], []).append(e)
    cat_order = [c.value for c in Category if c.value in by_cat]
    cat_order += sorted(set(by_cat) - set(cat_order))
    exp_options = ""
    for cat in cat_order:
        opts = "".join(
            f'<option value="{e["name"]}">{e["name"]}</option>'
            for e in sorted(by_cat[cat], key=lambda x: x["name"])
        )
        exp_options += f'<optgroup label="{_cat_label(cat)}">{opts}</optgroup>'
    exp_json = json.dumps({e["name"]: e for e in experiments})

    # Info tooltip for the leaderboard's "Avg conversion" column.
    conv_help = (
        "Average share of the 9 majority agents that adopted the dissenter's "
        "correct position by the end, averaged over this model's experiments. "
        "Higher is better (100% = the whole majority was converted to the truth)."
    )
    info_icon = (
        '<span class="relative group inline-flex align-middle ml-1 cursor-help text-[#656d76]" '
        f'tabindex="0" aria-label="{conv_help}">'
        '<svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true">'
        '<path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8zm6.5-.25A.75.75 0 '
        "017.25 7h1a.75.75 0 01.75.75v2.75h.25a.75.75 0 010 1.5h-2a.75.75 0 010-1.5h.25v-2h-.25a.75.75 0 "
        '01-.75-.75zM8 6a1 1 0 100-2 1 1 0 000 2z"></path></svg>'
        '<span role="tooltip" class="pointer-events-none absolute top-full right-0 mt-1.5 z-20 '
        "hidden group-hover:block group-focus:block w-64 whitespace-normal rounded-md bg-[#24292f] "
        f'px-3 py-2 text-xs font-normal leading-snug text-white shadow-lg">{conv_help}</span>'
        "</span>"
    )

    panel_cls = "rounded-md border border-[#d0d7de] overflow-hidden"
    panel_head = "px-4 py-2 bg-[#f6f8fa] border-b border-[#d0d7de] text-sm font-semibold"
    panel_body = "px-4 py-3 text-sm text-[#1f2328] whitespace-pre-wrap leading-relaxed"

    inspector = (
        f"""<section class="{section_cls}">
    <h2 class="{h2_cls}">Inspect experiments</h2>
    <select id="exp-select" class="border border-[#d0d7de] rounded-md px-3 py-1.5 bg-white text-sm mb-4 max-w-full">{exp_options}</select>
    <p class="text-sm text-[#656d76] mb-4"><span class="font-semibold text-[#1f2328]">Topic:</span> <span id="exp-topic"></span></p>
    <div class="grid md:grid-cols-2 gap-4">
      <div class="{panel_cls}"><div class="{panel_head} text-[#1f2328]">Majority &mdash; shared (incorrect) belief</div><div id="exp-common" class="{panel_body}"></div></div>
      <div class="{panel_cls}"><div class="{panel_head} text-[#116329]">Dissenter &mdash; ground truth</div><div id="exp-dissenter" class="{panel_body}"></div></div>
    </div>
  </section>"""
        if experiments
        else ""
    )

    inspector_js = (
        f"""<script>
const EXP = {exp_json};
function showExp(name) {{
  const e = EXP[name] || {{}};
  document.getElementById('exp-topic').textContent = e.topic || '';
  document.getElementById('exp-common').textContent = e.common || '';
  document.getElementById('exp-dissenter').textContent = e.dissenter || '';
}}
document.addEventListener('DOMContentLoaded', () => {{
  const sel = document.getElementById('exp-select');
  if (sel) {{ sel.addEventListener('change', ev => showExp(ev.target.value)); showExp(sel.value); }}
}});
</script>"""
        if experiments
        else ""
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The 10th Agent — Benchmark</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif}}</style>
</head>
<body class="bg-white text-[#1f2328] antialiased">
<header class="bg-[#f6f8fa] border-b border-[#d0d7de]">
  <div class="max-w-5xl mx-auto px-6 py-6">
    <h1 class="text-2xl font-semibold mb-2">Spiral-of-Silence Benchmark</h1>
    <p class="text-[#656d76] leading-relaxed max-w-2xl">Each experiment pits 9 agents sharing a wrong belief against 1 locked dissenter holding ground truth.
    The headline metric is the <b class="text-[#1f2328]">truth-conversion rate</b>: the fraction of the majority that adopted the dissenter's correct
    position by the end &mdash; green means the majority moved toward truth, red means the dissenter was silenced.</p>
  </div>
</header>
<main class="max-w-5xl mx-auto px-6 py-8">
  <section class="{section_cls}">
    <h2 class="{h2_cls}">Leaderboard</h2>
    <div class="{box_cls}">
      <table class="{table_cls}"><thead><tr>
        <th class="{head_cls} text-center">Rank</th><th class="{head_cls}">Model</th><th class="{head_cls}">Org</th><th class="{head_cls} text-center">Experiments</th><th class="{head_cls}">Avg conversion{info_icon}</th>
      </tr></thead><tbody>{lb_rows}</tbody></table>
    </div>
  </section>
  <section class="{section_cls}">
    <h2 class="{h2_cls}">Field &times; Model heatmap</h2>
    <div class="mb-4">{legend}</div>
    <div class="{box_cls}">
      <table class="{table_cls}"><thead><tr><th class="{head_cls}">Model</th>{hm_head}</tr></thead><tbody>{hm_rows}</tbody></table>
    </div>
  </section>
  <section class="{section_cls}">
    <h2 class="{h2_cls}">Per-experiment detail</h2>
    <div class="{box_cls}">
      <table class="{table_cls}"><thead><tr><th class="{head_cls}">Field</th><th class="{head_cls}">Experiment</th>{dt_head}</tr></thead><tbody>{dt_rows}</tbody></table>
    </div>
  </section>
  {inspector}
</main>
{inspector_js}
</body></html>
"""


def main(root: Path = EXPERIMENTS_ROOT, out_dir: Path = RESULTS_DIR) -> None:
    scores = collect_latest_scores(root)
    if not scores:
        print("No scored runs found. Run `python main.py bench` first.")
        return

    agg = aggregate(scores)
    meta = load_model_meta()
    experiments = collect_experiments(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "leaderboard.md").write_text(render_markdown(agg, meta))
    (out_dir / "index.html").write_text(render_html(agg, meta, experiments))
    print(
        f"Aggregated {len(scores)} runs "
        f"({len(agg.models)} models × {len(agg.experiments)} experiments).\n"
        f"  → {out_dir / 'leaderboard.md'}\n  → {out_dir / 'index.html'}"
    )
