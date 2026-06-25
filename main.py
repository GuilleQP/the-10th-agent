"""CLI entry point for the Spiral of Silence experiment.

  python main.py run <path/to/config.yaml>   Run a single experiment
  python main.py bench [--model ...] [...]    Run every experiment × every model
  python main.py agg                          Group runs into results/ (leaderboard + heatmap)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from src.agents import build_agents
from src.chatroom import run_simulation
from src.config import load_config

console = Console()

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Investigate the Spiral of Silence in LLM multi-agent systems.",
)


@app.command()
def run(
    config_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            help="Path to an experiment config.yaml",
        ),
    ],
) -> None:
    """Run a single experiment using the model declared in its config."""
    config = load_config(config_path)
    agents = build_agents(config)

    result = asyncio.run(run_simulation(config, agents))
    saved_path = result.save(config_path.parent)
    console.print(f"\n[bold green]Results saved to:[/] {saved_path}")

    console.print("\n[bold]--- Final Summary ---[/]")
    console.print(f"Epochs: {result.total_epochs}")
    if result.consensus:
        console.print(f"Consensus reached: {result.consensus.reached}")
        console.print(f"Majority position: {result.consensus.majority_position}")
        console.print(f"Agreement ratio: {result.consensus.agreement_ratio:.0%}")
        console.print(f"Dissenter silenced: {result.consensus.dissenter_silenced}")
    if result.dissenter_positions:
        console.print("\nDissenter position over time:")
        for i, pos in enumerate(result.dissenter_positions):
            console.print(f"  Epoch {i + 1}: {pos}")


@app.command()
def bench(
    model: Annotated[
        Optional[str],
        typer.Option(
            "--model",
            "-m",
            help="Only models whose name/label contains this substring.",
        ),
    ] = None,
    experiment: Annotated[
        Optional[str],
        typer.Option(
            "--experiment",
            "-e",
            help="Only experiments whose path contains this substring.",
        ),
    ] = None,
    models_file: Annotated[
        Optional[Path],
        typer.Option(
            "--models",
            exists=True,
            dir_okay=False,
            help="Use a different model registry (default: experiments/models.yaml).",
        ),
    ] = None,
) -> None:
    """Run the matrix of every experiment × every model (optionally filtered)."""
    from src.benchmark import MODELS_REGISTRY
    from src.benchmark import main as bench_main

    bench_main(
        models_file or MODELS_REGISTRY,
        model_filter=model,
        exp_filter=experiment,
    )


@app.command()
def agg() -> None:
    """Group runs into results/ as a leaderboard + field × model heatmap."""
    from src.aggregate import main as aggregate_main

    aggregate_main()


if __name__ == "__main__":
    app()
