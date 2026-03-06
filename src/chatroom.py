"""Simulation engine — the core chatroom loop."""

from __future__ import annotations

import random

from pydantic_ai import Agent
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from src.config import CommunicationStructure, ExperimentConfig
from src.consensus import ConsensusResult, check_consensus, extract_positions
from src.results import ChatMessage, ExperimentResult

console = Console()


def _speaking_order(structure: CommunicationStructure, count: int) -> list[int]:
    """Determine which agents speak and in what order for one epoch."""
    indices = list(range(count))
    if structure == CommunicationStructure.ROUND_ROBIN:
        return indices
    if structure == CommunicationStructure.RANDOM:
        random.shuffle(indices)
        return indices
    if structure == CommunicationStructure.FREE_FOR_ALL:
        # Random subset (at least half) in random order
        k = random.randint(count // 2, count)
        return random.sample(indices, k)
    raise ValueError(f"Unknown structure: {structure}")


def _build_transcript_prompt(
    topic: str, transcript: list[ChatMessage], epoch: int
) -> str:
    """Build the user prompt containing the discussion so far."""
    lines = [f"Topic under discussion: {topic}\n"]

    if not transcript:
        lines.append("This is the start of the discussion. Share your opening position.")
    else:
        lines.append("Here is the discussion so far:\n")
        for msg in transcript:
            label = f"Agent {msg.agent_id} (Epoch {msg.epoch})"
            lines.append(f"{label}: {msg.content}\n")
        lines.append(f"\nIt is now Epoch {epoch}. Please contribute to the discussion.")

    lines.append(
        "\nRemember: end your message with [POSITION: <your current stance>]"
    )
    return "\n".join(lines)


def _print_message(msg: ChatMessage, dissenter_index: int) -> None:
    """Pretty-print a chat message to the terminal."""
    is_dissenter = msg.agent_id == dissenter_index
    color = "red" if is_dissenter else "cyan"
    label = f"Agent {msg.agent_id}"
    if is_dissenter:
        label += " (dissenter)"

    title = Text(f"{label} — Epoch {msg.epoch}", style=f"bold {color}")
    console.print(Panel(msg.content, title=title, border_style=color))


async def run_simulation(
    config: ExperimentConfig,
    agents: list[Agent],
) -> ExperimentResult:
    """Run the full chatroom simulation."""
    transcript: list[ChatMessage] = []
    dissenter_positions: list[str] = []
    consensus_result: ConsensusResult | None = None

    console.print(f"\n[bold green]Starting experiment:[/] {config.name}")
    console.print(f"[dim]{config.description}[/]\n")

    for epoch in range(1, config.communication.max_epochs + 1):
        console.rule(f"[bold]Epoch {epoch}[/]")

        order = _speaking_order(config.communication.structure, config.agents.count)

        for agent_id in order:
            prompt = _build_transcript_prompt(config.topic, transcript, epoch)

            result = await agents[agent_id].run(prompt)
            content = result.output

            is_dissenter = agent_id == config.agents.dissenter_index
            msg = ChatMessage(
                epoch=epoch,
                agent_id=agent_id,
                content=content,
                is_dissenter=is_dissenter,
            )
            transcript.append(msg)
            _print_message(msg, config.agents.dissenter_index)

        # Track dissenter position
        dissenter_msgs = [m for m in transcript if m.is_dissenter and m.epoch == epoch]
        if dissenter_msgs:
            positions = extract_positions({0: dissenter_msgs[-1].content})
            dissenter_positions.append(positions.get(0, "unknown"))

        # Check consensus
        if epoch % config.consensus.check_every == 0:
            latest: dict[int, str] = {}
            for msg in reversed(transcript):
                if msg.agent_id not in latest:
                    latest[msg.agent_id] = msg.content
                if len(latest) == config.agents.count:
                    break

            consensus_result = await check_consensus(
                latest,
                config.consensus,
                config.agents.dissenter_index,
                config.model.name,
            )

            if consensus_result.reached:
                console.print(
                    f"\n[bold yellow]Consensus reached at epoch {epoch}![/]"
                    f" Majority: {consensus_result.majority_position}"
                    f" (agreement: {consensus_result.agreement_ratio:.0%})"
                )

    if consensus_result and not consensus_result.reached:
        console.print(
            f"\n[bold red]No consensus after {config.communication.max_epochs} epochs.[/]"
        )

    return ExperimentResult(
        experiment_name=config.name,
        total_epochs=epoch,
        consensus=consensus_result,
        dissenter_positions=dissenter_positions,
        transcript=transcript,
        config_snapshot=config.model_dump(),
    )
