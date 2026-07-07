"""Group-size study — how majority size affects truth-conversion.

Sweeps the number of *majority* agents (the dissenter is always exactly 1) for a
single experiment and model, e.g. 16 → 8 → 4 → 2 → 1, running a few repeats per
size and averaging. The hypothesis (spiral of silence) is that a larger wrong
majority is harder for the lone truth-teller to convert, so we sweep high → low
and can optionally stop the whole sweep once conversion saturates at 100% (all
smaller sizes are then assumed to convert too).

Runs are saved under ``experiments/group_size/runs/`` (kept out of the main
field × model leaderboard) and rendered to a dedicated ``docs/group_size.html``
with conversion plotted against N.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from pathlib import Path

from rich.console import Console

from src.aggregate import load_model_meta, score_run
from src.agents import build_agents
from src.benchmark import discover_experiments, load_models
from src.charts import Series, color_for, legend_html, line_chart_svg
from src.chatroom import run_simulation
from src.config import CommunicationStructure, ContaminationPolicy, load_config

console = Console()

GROUP_SIZE_DIR = Path("experiments/group_size")
DEFAULT_COUNTS = [16, 8, 4, 2, 1]
DEFAULT_MODEL = "anthropic:claude-haiku-4-5"
DEFAULT_EXPERIMENT = "linda_conjunction"


def _resolve_experiment(substring: str) -> Path | None:
    needle = substring.lower()
    for p in discover_experiments():
        if "group_size" in p.parts:
            continue
        if needle in str(p).lower():
            return p
    return None


async def _run_sweep(
    base_config_path: Path,
    model_name: str,
    counts: list[int],
    repeats: int,
    temperature: float,
    structure: CommunicationStructure | None,
    early_stop: bool,
) -> None:
    """Run the N-sweep for one experiment × model, saving every run."""
    base = load_config(base_config_path)
    console.print(
        f"[bold]Group-size sweep:[/] {base.name} × {model_name}\n"
        f"  N (majority) = {counts}  ·  {repeats} repeat(s) each  ·  "
        f"whole-sweep early stop: {'on' if early_stop else 'off'}"
    )

    for n_majority in counts:
        console.rule(f"[bold]N = {n_majority} majority + 1 dissenter[/]")
        conversions: list[float] = []
        for rep in range(1, repeats + 1):
            config = base.model_copy(deep=True)
            config.model.name = model_name
            config.model.temperature = temperature
            # N majority agents + 1 dissenter, dissenter last (speaks last in
            # round-robin), so build_agents assigns the truth to index N.
            config.agents.count = n_majority + 1
            config.agents.dissenter_index = n_majority
            # A single early-breaker shouldn't invalidate a 16-agent run; drop
            # only the pre-committed agents and keep the rest of the majority.
            config.contamination_policy = ContaminationPolicy.EXCLUDE
            if structure is not None:
                config.communication.structure = structure

            agents = build_agents(config)
            try:
                result = await run_simulation(config, agents)
            except Exception as exc:  # noqa: BLE001 — keep the sweep going
                console.print(f"[bold red]Run failed (N={n_majority}, rep {rep}):[/] {exc}")
                continue

            saved = result.save(GROUP_SIZE_DIR, name_suffix=f"n{n_majority:02d}_r{rep}")
            score = score_run(json.loads(saved.read_text()))
            if score is None:
                continue
            if score.valid:
                conversions.append(score.conversion_rate)
                console.print(
                    f"  rep {rep}: {score.converted}/{score.majority_count} converted "
                    f"({score.conversion_rate:.0%})  [{result.finish_reason}]"
                )
            else:
                console.print(f"  rep {rep}: [yellow]contaminated[/] — excluded")

        if conversions:
            mean = sum(conversions) / len(conversions)
            console.print(
                f"[bold]N={n_majority} mean conversion:[/] {mean:.0%} "
                f"({len(conversions)} valid run(s))"
            )
            if early_stop and mean >= 1.0:
                console.print(
                    "[bold green]Full conversion reached — stopping sweep early "
                    "(smaller N assumed to convert too).[/]"
                )
                break
        else:
            console.print(f"[yellow]N={n_majority}: no valid runs.[/]")


# --------------------------------------------------------------------------- #
# Aggregation + rendering
# --------------------------------------------------------------------------- #


def collect_group_scores(root: Path = GROUP_SIZE_DIR) -> dict:
    """Group sweep runs into {(model, experiment): {N: stats}}.

    ``stats`` = {conversion, n_valid, n_total, contamination}. Conversion is the
    mean over valid (non-contaminated) runs at that N; all repeats are averaged.
    """
    runs_dir = root / "runs"
    grouped: dict[tuple[str, str], dict[int, list]] = defaultdict(lambda: defaultdict(list))
    if not runs_dir.exists():
        return {}
    for path in sorted(runs_dir.glob("*_chat.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        score = score_run(data)
        if score is None:
            continue
        n_majority = data.get("config", {}).get("agents", {}).get("count", 1) - 1
        grouped[(score.model, score.experiment)][n_majority].append(score)

    out: dict[tuple[str, str], dict[int, dict]] = {}
    for key, by_n in grouped.items():
        out[key] = {}
        for n, scores in by_n.items():
            valid = [s for s in scores if s.valid]
            conv = sum(s.conversion_rate for s in valid) / len(valid) if valid else None
            # Pre-committed = nominal majority (N) minus the effective denominator
            # (majority_count already excludes them under the EXCLUDE policy).
            precommitted = (
                sum(n - s.majority_count for s in valid) / len(valid) if valid else 0.0
            )
            out[key][n] = {
                "conversion": conv,
                "n_valid": len(valid),
                "n_total": len(scores),
                "precommitted": precommitted,
                "contamination": (len(scores) - len(valid)) / len(scores) if scores else 0.0,
            }
    return out


def render_group_size_html(groups: dict, meta: dict[str, dict]) -> str:
    def mlabel(m: str) -> str:
        return meta.get(m, {}).get("label", m)

    # Union of all N across series, ascending → categorical (log-looking) x-axis.
    all_n = sorted({n for by_n in groups.values() for n in by_n})
    x_labels = [str(n) for n in all_n]

    series: list[Series] = []
    for i, ((model, exp), by_n) in enumerate(sorted(groups.items())):
        pts: list[float | None] = [
            (by_n[n]["conversion"] if n in by_n else None) for n in all_n
        ]
        series.append(Series(label=f"{mlabel(model)} · {exp}", color=color_for(i), points=pts))

    svg = line_chart_svg(
        series,
        x_labels,
        width=820,
        height=440,
        y_label="Majority converted to truth",
        x_title="Majority agents, N (log scale)",
    )
    legend = legend_html(series)

    # Detail table: one row per (model, experiment, N).
    rows = ""
    for (model, exp), by_n in sorted(groups.items()):
        for n in sorted(by_n):
            st = by_n[n]
            conv = "—" if st["conversion"] is None else f"{st['conversion']:.0%}"
            rows += (
                "<tr>"
                f'<td class="px-3 py-1.5 border-t border-[#d0d7de]">{mlabel(model)}</td>'
                f'<td class="px-3 py-1.5 border-t border-[#d0d7de]">{exp}</td>'
                f'<td class="px-3 py-1.5 border-t border-[#d0d7de] text-center tabular-nums">{n}</td>'
                f'<td class="px-3 py-1.5 border-t border-[#d0d7de] text-center tabular-nums">{conv}</td>'
                f'<td class="px-3 py-1.5 border-t border-[#d0d7de] text-center tabular-nums">{st["n_valid"]}/{st["n_total"]}</td>'
                f'<td class="px-3 py-1.5 border-t border-[#d0d7de] text-center tabular-nums">{st["precommitted"]:.1f}/{n}</td>'
                "</tr>"
            )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The 10th Agent — Group Size study</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}</style>
</head>
<body class="bg-white text-[#1f2328] antialiased">
<header class="bg-[#f6f8fa] border-b border-[#d0d7de]">
  <div class="max-w-4xl mx-auto px-6 py-6">
    <h1 class="text-2xl font-semibold mb-2">Group Size &mdash; does a bigger majority resist the truth?</h1>
    <p class="text-[#656d76] leading-relaxed max-w-2xl">One locked dissenter (the truth) faces a majority of size <b class="text-[#1f2328]">N</b> holding a false belief. We sweep N in powers of two and measure how much of the majority is converted. If the spiral of silence is real, conversion should <em>fall</em> as N grows.</p>
  </div>
</header>
<main class="max-w-4xl mx-auto px-6 py-8">
  <section class="mb-10">
    <h2 class="text-base font-semibold mb-3">Conversion vs. majority size</h2>
    <p class="text-sm text-[#656d76] mb-3">Conversion is measured only over agents that genuinely started with the false belief: any majority agent that argued the truth in epoch&nbsp;1 <em>before</em> the dissenter spoke never held the belief, so it's dropped from the denominator (see &ldquo;Pre-committed&rdquo; below). This keeps a single early-breaker from invalidating a large-N run.</p>
    <div class="mb-3">{legend}</div>
    <div class="rounded-md border border-[#d0d7de] p-4">{svg}</div>
  </section>
  <section class="mb-10">
    <h2 class="text-base font-semibold mb-3">Detail</h2>
    <div class="w-full overflow-x-auto rounded-md border border-[#d0d7de]">
      <table class="w-full border-collapse text-sm">
        <thead><tr class="bg-[#f6f8fa]">
          <th class="px-3 py-2 text-left font-semibold">Model</th>
          <th class="px-3 py-2 text-left font-semibold">Experiment</th>
          <th class="px-3 py-2 text-center font-semibold">N</th>
          <th class="px-3 py-2 text-center font-semibold">Avg conversion</th>
          <th class="px-3 py-2 text-center font-semibold">Valid runs</th>
          <th class="px-3 py-2 text-center font-semibold">Pre-committed (avg)</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </section>
</main>
</body></html>
"""


def write_group_size_page(out_dir: Path = Path("docs")) -> Path | None:
    """Render docs/group_size.html from whatever sweep runs exist; None if none."""
    groups = collect_group_scores()
    if not groups:
        return None
    meta = load_model_meta()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "group_size.html"
    path.write_text(render_group_size_html(groups, meta))
    return path


def main(
    experiment: str = DEFAULT_EXPERIMENT,
    model_name: str = DEFAULT_MODEL,
    counts: list[int] | None = None,
    repeats: int = 2,
    structure: CommunicationStructure | None = None,
    early_stop: bool = False,
) -> None:
    base_path = _resolve_experiment(experiment)
    if base_path is None:
        console.print(f"[bold red]No experiment matched[/] '{experiment}'.")
        return
    _, temperature = load_models()
    asyncio.run(
        _run_sweep(
            base_path,
            model_name,
            counts or DEFAULT_COUNTS,
            repeats,
            temperature,
            structure,
            early_stop,
        )
    )
    page = write_group_size_page()
    if page:
        console.print(f"\n[bold green]Group-size study written to:[/] {page}")
