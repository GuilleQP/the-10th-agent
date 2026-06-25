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
from src.summarizer import summarize_transcript

console = Console()


def _speaking_order(
    structure: CommunicationStructure, count: int, dissenter_index: int
) -> list[int]:
    """Determine which agents speak and in what order for one epoch.

    The dissenter is always included: it is the lone source of ground truth,
    so letting a structure silence it would defeat the experiment (e.g. the
    majority could reach consensus before the dissenter ever speaks).
    """
    indices = list(range(count))
    if structure == CommunicationStructure.ROUND_ROBIN:
        return indices
    if structure == CommunicationStructure.RANDOM:
        random.shuffle(indices)
        return indices
    if structure == CommunicationStructure.FREE_FOR_ALL:
        # Random subset (at least half) in random order, but always include
        # the dissenter — inserted at a random spot if it wasn't sampled.
        k = random.randint(count // 2, count)
        order = random.sample(indices, k)
        if dissenter_index not in order:
            order.insert(random.randrange(len(order) + 1), dissenter_index)
        return order
    raise ValueError(f"Unknown structure: {structure}")


def _build_prompt(
    topic: str,
    summary: str | None,
    messages: list[ChatMessage],
    epoch: int,
) -> str:
    """Build the user prompt for an agent's turn.

    ``summary`` is a recap of earlier epochs (when epoch summarization is on),
    and ``messages`` is the context to show verbatim — either the full
    transcript or just the current epoch's messages.
    """
    lines = [f"Topic under discussion: {topic}\n"]

    if not summary and not messages:
        lines.append("This is the start of the discussion. Share your opening position.")
    else:
        if summary:
            lines.append("Summary of the discussion in earlier epochs:\n")
            lines.append(f"{summary}\n")
        if messages:
            header = (
                "Messages so far in the current epoch:"
                if summary
                else "Here is the discussion so far:"
            )
            lines.append(f"{header}\n")
            for msg in messages:
                label = f"Agent {msg.agent_id} (Epoch {msg.epoch})"
                lines.append(f"{label}: {msg.content}\n")
        lines.append(f"\nIt is now Epoch {epoch}. Please contribute to the discussion.")

    lines.append(
        "\nRemember: end your message with [POSITION: <your current stance>]"
    )
    return "\n".join(lines)


def _print_message(msg: ChatMessage, dissenter_index: int, experiment_name: str) -> None:
    """Pretty-print a chat message to the terminal."""
    is_dissenter = msg.agent_id == dissenter_index
    color = "red" if is_dissenter else "cyan"
    label = f"Agent {msg.agent_id}"
    if is_dissenter:
        label += " (dissenter)"

    title = Text(
        f"{experiment_name} · {label} — Epoch {msg.epoch}", style=f"bold {color}"
    )
    console.print(Panel(msg.content, title=title, border_style=color))


async def run_simulation(
    config: ExperimentConfig,
    agents: list[Agent],
) -> ExperimentResult:
    """Run the full chatroom simulation."""
    transcript: list[ChatMessage] = []
    dissenter_positions: list[str] = []
    consensus_result: ConsensusResult | None = None
    # Recap of earlier epochs; stays None until the first epoch is summarized.
    summary: str | None = None
    epoch_summaries: list[dict] = []

    console.print(f"\n[bold green]Starting experiment:[/] {config.name}")
    console.print(f"[dim]{config.description}[/]\n")

    for epoch in range(1, config.communication.max_epochs + 1):
        console.rule(f"[bold]Epoch {epoch}[/]")

        order = _speaking_order(
            config.communication.structure,
            config.agents.count,
            config.agents.dissenter_index,
        )

        for agent_id in order:
            if config.communication.summarize_epoch and summary is not None:
                # Summary of earlier epochs + this epoch's messages so far.
                current = [m for m in transcript if m.epoch == epoch]
                prompt = _build_prompt(config.topic, summary, current, epoch)
            else:
                # Full transcript (no summarization, or the first epoch).
                prompt = _build_prompt(config.topic, None, transcript, epoch)

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
            _print_message(msg, config.agents.dissenter_index, config.name)

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

            # Unanimous agreement (with the dissenter locked to truth, 100%
            # can only mean the whole group converged on the correct answer):
            # there is nothing left to discuss, so stop early.
            if consensus_result.agreement_ratio >= 1.0:
                console.print(
                    f"\n[bold green]Everyone agrees at epoch {epoch} — stopping early.[/]"
                    f" Final position: {consensus_result.majority_position}"
                )
                break

        # Summarize the discussion so far for the next epoch's agents.
        # Skipped on the final epoch (no next epoch will read it).
        if (
            config.communication.summarize_epoch
            and epoch < config.communication.max_epochs
        ):
            console.print(f"[dim]Summarizing epoch {epoch}…[/]")
            summary = await summarize_transcript(
                transcript, config.topic, config.model.name
            )
            epoch_summaries.append({"after_epoch": epoch, "summary": summary})
            console.print(
                f"[dim]Summary ready for epoch {epoch + 1} "
                f"({len(summary)} chars).[/]"
            )

    if consensus_result and consensus_result.agreement_ratio < 1.0:
        console.print(
            f"\n[bold]Ended after {epoch} epochs without full agreement.[/]"
            f" {consensus_result.agreement_ratio:.0%} of agents held"
            f" '{consensus_result.majority_position}'; the dissenter was not silenced."
        )

    return ExperimentResult(
        experiment_name=config.name,
        total_epochs=epoch,
        consensus=consensus_result,
        dissenter_positions=dissenter_positions,
        transcript=transcript,
        config_snapshot=config.model_dump(),
        epoch_summaries=epoch_summaries,
    )
