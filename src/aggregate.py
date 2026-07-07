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
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.charts import Series, color_for, legend_html, line_chart_svg
from src.config import CATEGORY_LABELS, Category, load_config
from src.scoring import classify_stance

EXPERIMENTS_ROOT = Path("experiments")
RESULTS_DIR = Path("docs")  # GitHub Pages serves from /docs on the main branch
CHARTS_DIR = Path("charts")  # local per-model conversion-curve checks (gitignored)
MODELS_REGISTRY = EXPERIMENTS_ROOT / "models.yaml"

# X-axis horizon for conversion-over-epoch curves. All current configs cap at 5
# epochs; shorter runs (e.g. early consensus) carry their last value forward,
# and any stale longer run is truncated here.
EPOCH_HORIZON = 5

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


# The "standard" condition; leaderboard + heatmap use only these runs so
# structure experiments don't skew the headline model comparison.
CANONICAL_STRUCTURE = "round-robin"

# Group-size sweep runs live here; they reuse an experiment's name but vary the
# agent count, so they must NOT feed the field × model leaderboard/heatmap.
GROUP_SIZE_DIRNAME = "group_size"


@dataclass
class RunScore:
    experiment: str
    category: str
    model: str
    structure: str
    finish_reason: str
    conversion_rate: float
    majority_count: int
    converted: int
    consensus_reached: bool
    dissenter_silenced: bool
    # Per-epoch conversion fraction (carry-forward), length EPOCH_HORIZON. Only
    # populated from LLM-judged verdicts_by_epoch; empty for keyword fallback.
    epoch_curve: list[float] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """Contaminated runs (prior-knowledge leak) don't count as results."""
        return self.finish_reason != "contaminated"


def _epoch_curve(
    vbe: list[dict], dissenter_index: int, horizon: int, precommitted: set | None = None
) -> list[float]:
    """Per-epoch majority conversion via carry-forward of each agent's verdict.

    For epoch e, each majority agent contributes its latest verdict with
    epoch <= e (False before it first speaks). A run that stopped early at 100%
    consensus therefore stays at 100% through the horizon; non-speakers in a
    given epoch keep their previous stance.
    """
    precommitted = precommitted or set()
    by_agent: dict[int, list[tuple[int, bool]]] = {}
    for v in vbe:
        aid = v.get("agent_id")
        if aid == dissenter_index or aid in precommitted:
            continue
        by_agent.setdefault(aid, []).append((v.get("epoch", 0), bool(v.get("holds_truth"))))
    if not by_agent:
        return []
    for hist in by_agent.values():
        hist.sort()

    curve: list[float] = []
    for e in range(1, horizon + 1):
        holding = 0
        for hist in by_agent.values():
            latest = [h for ep, h in hist if ep <= e]
            if latest and latest[-1]:
                holding += 1
        curve.append(holding / len(by_agent))
    return curve


def score_run(data: dict) -> RunScore | None:
    """Compute a conversion score for one run JSON payload."""
    config = data.get("config", {})
    scoring = config.get("scoring", {})
    truth_kw = scoring.get("truth_keywords", [])
    false_kw = scoring.get("false_keywords", [])
    dissenter_index = config.get("agents", {}).get("dissenter_index", 9)
    finish_reason = data.get("finish_reason", "max_epochs")

    common = dict(
        experiment=data.get("experiment_name", "unknown"),
        category=config.get("category", "uncategorized"),
        model=config.get("model", {}).get("name", "unknown"),
        structure=config.get("communication", {}).get("structure", CANONICAL_STRUCTURE),
        finish_reason=finish_reason,
    )

    # A contaminated run is invalid — record it (so it's visible) but unscored.
    if finish_reason == "contaminated":
        return RunScore(
            **common,
            conversion_rate=0.0,
            majority_count=0,
            converted=0,
            consensus_reached=False,
            dissenter_silenced=False,
        )

    consensus = data.get("consensus") or {}

    # Agents that leaked the truth in epoch 1 before the dissenter spoke never
    # held the false belief, so they're not part of the population the spiral
    # acts on — drop them from the denominator (EXCLUDE policy).
    precommitted = set(data.get("precommitted_agents", []))

    # Preferred: LLM-judged per-epoch verdicts. Final conversion uses each
    # majority agent's latest-epoch verdict.
    vbe = data.get("verdicts_by_epoch")
    if vbe:
        final: dict[int, tuple[int, bool]] = {}
        for v in vbe:
            aid = v.get("agent_id")
            if aid == dissenter_index or aid in precommitted:
                continue
            ep = v.get("epoch", 0)
            if aid not in final or ep >= final[aid][0]:
                final[aid] = (ep, bool(v.get("holds_truth")))
        if final:
            converted = sum(1 for _, holds in final.values() if holds)
            return RunScore(
                **common,
                conversion_rate=converted / len(final),
                majority_count=len(final),
                converted=converted,
                consensus_reached=bool(consensus.get("reached")),
                dissenter_silenced=bool(consensus.get("dissenter_silenced")),
                epoch_curve=_epoch_curve(vbe, dissenter_index, EPOCH_HORIZON, precommitted),
            )

    # Legacy fallback: negation-aware keyword scoring on final positions.
    positions: dict[str, str] = consensus.get("positions", {})
    if not positions:
        return None

    majority = {int(k): v for k, v in positions.items() if int(k) != dissenter_index}
    if not majority:
        return None

    converted = sum(
        1 for pos in majority.values()
        if classify_stance(pos, truth_kw, false_kw) == "truth"
    )

    return RunScore(
        **common,
        conversion_rate=converted / len(majority),
        majority_count=len(majority),
        converted=converted,
        consensus_reached=bool(consensus.get("reached")),
        dissenter_silenced=bool(consensus.get("dissenter_silenced")),
    )


def collect_latest_scores(root: Path = EXPERIMENTS_ROOT) -> list[RunScore]:
    """Score the latest run per (experiment, structure, model).

    Files are named ``<timestamp>_<model-slug>_<structure>_chat.json``; sorting
    by filename sorts by timestamp, so the last one per key wins.
    """
    latest: dict[tuple[str, str, str], RunScore] = {}
    for path in sorted(root.rglob("*_chat.json")):
        if GROUP_SIZE_DIRNAME in path.parts:
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        score = score_run(data)
        if score is None:
            continue
        latest[(score.experiment, score.structure, score.model)] = score
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
        if GROUP_SIZE_DIRNAME in path.parts:
            continue
        try:
            c = load_config(path)
        except Exception:  # noqa: BLE001 — skip malformed configs
            continue
        out.append(
            {
                "name": c.name,
                # Collapse YAML block-scalar line wraps into flowing prose.
                "topic": " ".join(c.topic.split()),
                "category": c.category.value,
                "common": " ".join(c.knowledge.common.split()),
                "dissenter": " ".join(c.knowledge.dissenter.split()),
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
    # (category, experiment, structure)
    experiments: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def canonical(self) -> list[RunScore]:
        """Standard (round-robin), valid runs — used for headline metrics."""
        return [
            s for s in self.scores if s.structure == CANONICAL_STRUCTURE and s.valid
        ]

    def model_field_rate(self, model: str, category: str) -> float | None:
        vals = [
            s.conversion_rate
            for s in self.canonical
            if s.model == model and s.category == category
        ]
        return sum(vals) / len(vals) if vals else None

    def model_overall(self, model: str) -> float | None:
        vals = [s.conversion_rate for s in self.canonical if s.model == model]
        return sum(vals) / len(vals) if vals else None

    def cell(self, model: str, experiment: str, structure: str) -> RunScore | None:
        for s in self.scores:
            if s.model == model and s.experiment == experiment and s.structure == structure:
                return s
        return None

    def model_curve(self, model: str) -> list[float]:
        """Mean per-epoch conversion across this model's canonical runs."""
        curves = [s.epoch_curve for s in self.canonical if s.model == model and s.epoch_curve]
        if not curves:
            return []
        return [sum(c[e] for c in curves) / len(curves) for e in range(EPOCH_HORIZON)]

    def model_experiment_curves(self, model: str) -> list[tuple[str, list[float]]]:
        """(experiment, curve) for this model's canonical runs, sorted by name."""
        out = [
            (s.experiment, s.epoch_curve)
            for s in self.canonical
            if s.model == model and s.epoch_curve
        ]
        return sorted(out)


def aggregate(scores: list[RunScore]) -> Aggregation:
    models = sorted({s.model for s in scores})
    # Order categories by the canonical enum, keeping only those present.
    present = {s.category for s in scores}
    categories = [c.value for c in Category if c.value in present]
    categories += sorted(present - set(categories))
    # Detail rows are per (category, experiment, structure); non-round-robin
    # structures sort after round-robin within each experiment.
    experiments = sorted(
        {(s.category, s.experiment, s.structure) for s in scores},
        key=lambda t: (t[0], t[1], t[2] != CANONICAL_STRUCTURE, t[2]),
    )
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
    lines += ["## Field × Model heatmap (avg conversion, round-robin runs)", ""]
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

    # Per-experiment detail (round-robin runs only, like the leaderboard/heatmap)
    lines += ["## Per-experiment detail (conversion rate, round-robin runs)", ""]
    detail_header = (
        "| Field | Experiment | " + " | ".join(label(m) for m in ranked) + " |"
    )
    detail_sep = "|---|---|" + "|".join(["---"] * len(ranked)) + "|"
    lines += [detail_header, detail_sep]
    for cat, exp, struct in agg.experiments:
        if struct != CANONICAL_STRUCTURE:
            continue
        cells = []
        for m in ranked:
            s = agg.cell(m, exp, struct)
            if s is None:
                cells.append("—")
            elif not s.valid:
                cells.append("contaminated")
            else:
                cells.append(f"{s.conversion_rate:.0%}")
        lines.append(
            f"| {_cat_label(cat)} | {exp} | " + " | ".join(cells) + " |"
        )
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

    # Detail rows (round-robin runs only, like the leaderboard/heatmap)
    dt_head = "".join(f'<th class="{head_cls} text-center">{label(m)}</th>' for m in ranked)
    dt_rows = ""
    for cat, exp, struct in agg.experiments:
        if struct != CANONICAL_STRUCTURE:
            continue
        cells = ""
        for m in ranked:
            s = agg.cell(m, exp, struct)
            if s and not s.valid:
                cells += (
                    f'<td class="{hm_cls}" style="background:#eaeef2;color:#8a8780" '
                    'title="Contaminated: a majority agent argued the truth in epoch 1 '
                    'before the dissenter spoke (prior-knowledge leak).">contaminated</td>'
                )
            else:
                cells += cell(s.conversion_rate if s else None)
        dt_rows += (
            f'<tr><th class="{rowh_cls}">{_cat_label(cat)}</th>'
            f'<td class="{base_cls}">{exp}</td>{cells}</tr>'
        )

    legend = "".join(
        '<span class="inline-flex items-center rounded-full px-3 py-0.5 mr-2 mb-2 text-xs font-medium border" '
        f'style="background:{bg};color:{fg};border-color:{fg}33">{lbl}</span>'
        for _, _, lbl, bg, fg in BUCKETS
    )

    # Conversion-over-epochs: one averaged line per model (canonical runs).
    x_labels = [str(e) for e in range(1, EPOCH_HORIZON + 1)]
    curve_series = [
        Series(label=label(m), color=color_for(i), points=agg.model_curve(m))
        for i, m in enumerate(ranked)
    ]
    curve_series = [s for s in curve_series if s.points]
    curve_svg = line_chart_svg(curve_series, x_labels)
    curve_legend = legend_html(curve_series)

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
        "correct position by the end, averaged over this model's round-robin "
        "experiments. Higher is better (100% = the whole majority was converted)."
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
    panel_body = "px-4 py-3 text-sm text-[#1f2328] leading-relaxed"

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
  <div class="rounded-md border border-[#d0d7de] bg-[#f6f8fa] px-4 py-3 mb-8 text-sm leading-relaxed text-[#1f2328]">
    <span class="font-semibold">TL;DR —</span> Nine AI agents get a false belief; one locked &ldquo;dissenter&rdquo; gets the truth and never backs down. They debate, and we measure whether the majority is converted to the truth or the lone correct voice gets drowned out (the <em>spiral of silence</em>). Score = <span class="font-semibold">truth-conversion rate</span>: the share of the majority that comes around.
  </div>
  <section class="{section_cls}">
    <h2 class="{h2_cls}">Leaderboard</h2>
    <div class="{box_cls}">
      <table class="{table_cls}"><thead><tr>
        <th class="{head_cls} text-center">Rank</th><th class="{head_cls}">Model</th><th class="{head_cls}">Org</th><th class="{head_cls} text-center">Experiments</th><th class="{head_cls}">Avg conversion{info_icon}</th>
      </tr></thead><tbody>{lb_rows}</tbody></table>
    </div>
  </section>
  <section class="{section_cls}">
    <h2 class="{h2_cls}">Field &times; Model heatmap <span class="text-xs font-normal text-[#8a8780]">(round-robin runs)</span></h2>
    <div class="mb-4">{legend}</div>
    <div class="{box_cls}">
      <table class="{table_cls}"><thead><tr><th class="{head_cls}">Model</th>{hm_head}</tr></thead><tbody>{hm_rows}</tbody></table>
    </div>
  </section>
  <section class="{section_cls}">
    <h2 class="{h2_cls}">Conversion over epochs <span class="text-xs font-normal text-[#8a8780]">(avg per model, round-robin runs)</span></h2>
    <p class="text-sm text-[#656d76] mb-3">Share of the 9 majority agents holding the truth at the end of each epoch, averaged over every experiment. Shows <em>when</em> agents come around &mdash; a steep early rise means the dissenter broke the consensus fast; a flat line near 0 means it was silenced.</p>
    <div class="mb-3">{curve_legend}</div>
    <div class="{box_cls} p-4">{curve_svg}</div>
  </section>
  <section class="{section_cls}">
    <h2 class="{h2_cls}">Per-experiment detail <span class="text-xs font-normal text-[#8a8780]">(round-robin runs)</span></h2>
    <p class="text-sm text-[#656d76] mb-3"><span class="inline-block rounded-full bg-[#eaeef2] px-2 py-0.5 text-xs font-medium text-[#8a8780] mr-1">contaminated</span> the run was discarded &mdash; a majority agent argued the truth in epoch&nbsp;1 before the dissenter spoke, leaking prior knowledge instead of holding its assigned false belief.</p>
    <div class="{box_cls}">
      <table class="{table_cls}"><thead><tr><th class="{head_cls}">Field</th><th class="{head_cls}">Experiment</th>{dt_head}</tr></thead><tbody>{dt_rows}</tbody></table>
    </div>
  </section>
  {inspector}
</main>
{inspector_js}
</body></html>
"""


def render_model_curve_page(agg: Aggregation, model: str, model_label: str) -> str:
    """Standalone HTML: one conversion line per experiment for a single model."""
    x_labels = [str(e) for e in range(1, EPOCH_HORIZON + 1)]
    series = [
        Series(label=exp, color=color_for(i), points=curve)
        for i, (exp, curve) in enumerate(agg.model_experiment_curves(model))
    ]
    svg = line_chart_svg(series, x_labels, width=820, height=420)
    legend = legend_html(series)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conversion over epochs — {model_label}</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}</style>
</head>
<body class="bg-white text-[#1f2328] antialiased">
<main class="max-w-4xl mx-auto px-6 py-8">
  <h1 class="text-xl font-semibold mb-1">Conversion over epochs &mdash; {model_label}</h1>
  <p class="text-sm text-[#656d76] mb-4">Share of the 9 majority agents holding the truth at the end of each epoch. One line per experiment (round-robin runs).</p>
  <div class="mb-3">{legend}</div>
  <div class="rounded-md border border-[#d0d7de] p-4">{svg}</div>
</main>
</body></html>
"""


def write_model_curve_pages(agg: Aggregation, meta: dict[str, dict], out_dir: Path) -> list[Path]:
    """Write one local per-model conversion-curve page; return the paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for m in agg.models:
        if not agg.model_experiment_curves(m):
            continue
        label = meta.get(m, {}).get("label", m)
        slug = re.sub(r"[^a-z0-9]+", "-", m.lower()).strip("-")
        path = out_dir / f"{slug}_epochs.html"
        path.write_text(render_model_curve_page(agg, m, label))
        written.append(path)
    return written


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
    curve_pages = write_model_curve_pages(agg, meta, CHARTS_DIR)

    # Group-size study (if any sweeps have been run) — kept on its own page.
    from src.groupsize import write_group_size_page

    gs_page = write_group_size_page(out_dir)
    if gs_page:
        print(f"  → {gs_page}")

    print(
        f"Aggregated {len(scores)} runs "
        f"({len(agg.models)} models × {len(agg.experiments)} experiments).\n"
        f"  → {out_dir / 'leaderboard.md'}\n  → {out_dir / 'index.html'}\n"
        f"  → {len(curve_pages)} per-model conversion-curve pages in {CHARTS_DIR}/"
    )
