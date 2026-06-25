"""Benchmark matrix runner — every experiment against every model.

Discovers all ``config.yaml`` files under ``experiments/`` and runs each one
against every model in the registry (``experiments/models.yaml``), so results
can later be grouped by field and compared across models.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from rich.console import Console

from src.agents import build_agents
from src.chatroom import run_simulation
from src.config import load_config

console = Console()

EXPERIMENTS_ROOT = Path("experiments")
MODELS_REGISTRY = EXPERIMENTS_ROOT / "models.yaml"


def discover_experiments(root: Path = EXPERIMENTS_ROOT) -> list[Path]:
    """Find every experiment config under ``root`` (recursively)."""
    return sorted(p for p in root.rglob("config.yaml"))


def load_models(path: Path = MODELS_REGISTRY) -> tuple[list[dict], float]:
    """Load the model registry. Returns (models, default_temperature)."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    return raw["models"], float(raw.get("temperature", 0.7))


async def run_matrix(
    experiment_paths: list[Path],
    models: list[dict],
    temperature: float,
    structure_override=None,
) -> None:
    """Run every experiment against every model, saving each run."""
    total = len(experiment_paths) * len(models)
    done = 0

    for config_path in experiment_paths:
        base = load_config(config_path)
        for model in models:
            done += 1
            label = model.get("label", model["name"])
            console.rule(
                f"[bold]({done}/{total})[/] {base.name} × {label}"
            )

            # Clone the config with this model (and optional structure) swapped in.
            config = base.model_copy(deep=True)
            config.model.name = model["name"]
            config.model.temperature = temperature
            if structure_override is not None:
                config.communication.structure = structure_override

            agents = build_agents(config)
            try:
                result = await run_simulation(config, agents)
            except Exception as exc:  # noqa: BLE001 — keep the matrix going
                console.print(
                    f"[bold red]Skipped {base.name} × {label}:[/] {exc}"
                )
                continue

            result.save(config_path.parent)

    console.print(f"\n[bold green]Matrix complete:[/] {done} runs attempted.")


def main(
    models_path: Path = MODELS_REGISTRY,
    model_filter: str | None = None,
    exp_filter: str | None = None,
    structure_override=None,
) -> None:
    experiment_paths = discover_experiments()
    if exp_filter:
        needle = exp_filter.lower()
        experiment_paths = [p for p in experiment_paths if needle in str(p).lower()]
    if not experiment_paths:
        console.print(
            f"[bold red]No experiments matched[/] '{exp_filter}'."
            if exp_filter
            else "[bold red]No experiments found under experiments/[/]"
        )
        return

    models, temperature = load_models(models_path)
    if model_filter:
        needle = model_filter.lower()
        models = [
            m
            for m in models
            if needle in m["name"].lower() or needle in m.get("label", "").lower()
        ]
    if not models:
        console.print(f"[bold red]No models matched[/] '{model_filter}'.")
        return

    structure_note = (
        f" — structure: {structure_override.value}" if structure_override else ""
    )
    console.print(
        f"[bold]Benchmark matrix:[/] {len(experiment_paths)} experiment(s) "
        f"× {len(models)} model(s){structure_note}"
    )
    asyncio.run(run_matrix(experiment_paths, models, temperature, structure_override))
