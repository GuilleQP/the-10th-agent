"""Consensus detection strategies."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from src.config import ConsensusConfig, ConsensusMethod


@dataclass
class ConsensusResult:
    reached: bool
    majority_position: str | None
    dissenter_silenced: bool
    positions: dict[int, str]
    agreement_ratio: float


def extract_positions(messages: dict[int, str]) -> dict[int, str]:
    """Extract [POSITION: ...] tags from the latest message of each agent."""
    positions: dict[int, str] = {}
    pattern = re.compile(r"\[POSITION:\s*(.+?)\]", re.IGNORECASE)
    for agent_id, content in messages.items():
        match = pattern.search(content)
        if match:
            positions[agent_id] = match.group(1).strip()
    return positions


def _keyword_consensus(
    positions: dict[int, str], threshold: float
) -> ConsensusResult:
    """Check consensus by grouping extracted positions."""
    if not positions:
        return ConsensusResult(
            reached=False,
            majority_position=None,
            dissenter_silenced=False,
            positions=positions,
            agreement_ratio=0.0,
        )

    # Normalize positions to lowercase for comparison
    normalized: dict[int, str] = {k: v.lower() for k, v in positions.items()}
    counts: dict[str, list[int]] = {}
    for agent_id, pos in normalized.items():
        counts.setdefault(pos, []).append(agent_id)

    # Find majority
    majority_pos = max(counts, key=lambda p: len(counts[p]))
    ratio = len(counts[majority_pos]) / len(positions)
    reached = ratio >= threshold

    return ConsensusResult(
        reached=reached,
        majority_position=majority_pos,
        dissenter_silenced=False,  # Determined by caller
        positions=positions,
        agreement_ratio=ratio,
    )


class LLMJudgeResult(BaseModel):
    """Structured result from the LLM judge."""

    consensus_reached: bool
    majority_position: str
    agreement_ratio: float = Field(
        description="Fraction of agents that agree with the majority position, between 0.0 and 1.0"
    )
    dissenter_silenced: bool
    reasoning: str


_judge_agent: Agent[None, LLMJudgeResult] | None = None


def _get_judge_agent(model_name: str) -> Agent[None, LLMJudgeResult]:
    global _judge_agent
    if _judge_agent is None:
        _judge_agent = Agent(
            model_name,
            output_type=LLMJudgeResult,
            system_prompt=(
                "You are a consensus judge. Analyze the positions of all agents "
                "in a group discussion and determine if consensus has been reached. "
                "Consider positions that are semantically similar as agreeing even "
                "if worded differently."
            ),
        )
    return _judge_agent


async def _llm_judge_consensus(
    latest_messages: dict[int, str],
    dissenter_index: int,
    threshold: float,
    model_name: str,
) -> ConsensusResult:
    """Use an LLM judge to assess consensus."""
    positions = extract_positions(latest_messages)

    prompt_lines = ["Here are the latest positions from each agent:\n"]
    for agent_id in sorted(latest_messages.keys()):
        prompt_lines.append(f"Agent {agent_id}: {latest_messages[agent_id]}\n")
    prompt_lines.append(
        f"\nThreshold for consensus: {threshold:.0%} agreement. "
        f"Is there consensus? Did the dissenter (Agent {dissenter_index}) "
        "change their position to match the majority?"
    )

    judge = _get_judge_agent(model_name)
    result = await judge.run("\n".join(prompt_lines))
    judge_result = result.output

    ratio = judge_result.agreement_ratio
    if ratio > 1.0:
        ratio = ratio / 100.0

    return ConsensusResult(
        reached=judge_result.consensus_reached,
        majority_position=judge_result.majority_position,
        dissenter_silenced=judge_result.dissenter_silenced,
        positions=positions,
        agreement_ratio=ratio,
    )


async def check_consensus(
    latest_messages: dict[int, str],
    config: ConsensusConfig,
    dissenter_index: int,
    model_name: str,
) -> ConsensusResult:
    """Check for consensus using the configured method."""
    if config.method == ConsensusMethod.KEYWORD:
        positions = extract_positions(latest_messages)
        return _keyword_consensus(positions, config.threshold)

    if config.method == ConsensusMethod.UNANIMOUS:
        positions = extract_positions(latest_messages)
        return _keyword_consensus(positions, threshold=1.0)

    if config.method == ConsensusMethod.LLM_JUDGE:
        return await _llm_judge_consensus(
            latest_messages, dissenter_index, config.threshold, model_name
        )

    raise ValueError(f"Unknown consensus method: {config.method}")
