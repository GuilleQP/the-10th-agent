"""CLI entry point for the Spiral of Silence experiment."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from rich.console import Console

from src.agents import build_agents
from src.chatroom import run_simulation
from src.config import load_config

console = Console()


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        console.print("[bold]Usage:[/] python main.py <path/to/config.yaml>")
        console.print("\nExample:")
        console.print("  python main.py experiments/flat_earth/config.yaml")
        sys.exit(0 if "--help" in sys.argv or "-h" in sys.argv else 1)

    config_path = Path(sys.argv[1])
    if not config_path.exists():
        console.print(f"[bold red]Error:[/] Config file not found: {config_path}")
        sys.exit(1)

    config = load_config(config_path)
    agents = build_agents(config)

    experiment_dir = config_path.parent
    result = asyncio.run(run_simulation(config, agents))

    saved_path = result.save(experiment_dir)
    console.print(f"\n[bold green]Results saved to:[/] {saved_path}")

    # Print final summary
    console.print("\n[bold]--- Final Summary ---[/]")
    console.print(f"Epochs: {result.total_epochs}")
    if result.consensus:
        console.print(f"Consensus reached: {result.consensus.reached}")
        console.print(f"Majority position: {result.consensus.majority_position}")
        console.print(f"Agreement ratio: {result.consensus.agreement_ratio:.0%}")
        console.print(f"Dissenter silenced: {result.consensus.dissenter_silenced}")
    if result.dissenter_positions:
        console.print(f"\nDissenter position over time:")
        for i, pos in enumerate(result.dissenter_positions):
            console.print(f"  Epoch {i + 1}: {pos}")


if __name__ == "__main__":
    main()
