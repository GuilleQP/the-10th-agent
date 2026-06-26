"""Post-run LLM verdicts: does a position agree with the ground truth?

Keyword scoring is brittle (negations, shared topic vocabulary), so we ask an
LLM to read positions and decide ``holds_truth`` per position. Positions are
deduplicated, so judging a whole run (every agent × every epoch) is one call.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent


class _PositionVerdict(BaseModel):
    index: int
    holds_truth: bool


class _Verdicts(BaseModel):
    verdicts: list[_PositionVerdict]


# One judge agent per model name (so the benchmark matrix doesn't reuse the
# first model's judge for every model).
_judges: dict[str, Agent[None, _Verdicts]] = {}


def _get_judge(model_name: str) -> Agent[None, _Verdicts]:
    if model_name not in _judges:
        _judges[model_name] = Agent(
            model_name,
            output_type=_Verdicts,
            system_prompt=(
                "You assess a debate. You are given the correct answer and a "
                "numbered list of stated positions. For EACH numbered position, "
                "decide whether it agrees with the correct answer (holds_truth=true) "
                "or not (false). Judge by meaning, not wording: hedged or partial "
                "answers that land on the correct conclusion count as true; "
                "restating the wrong belief, or staying uncertain, counts as false. "
                "Return exactly one verdict per index."
            ),
        )
    return _judges[model_name]


async def judge_positions(
    topic: str,
    truth: str,
    positions: list[str],
    model_name: str,
) -> dict[str, bool]:
    """Return {position: holds_truth} for the unique non-empty positions."""
    uniq = sorted({p for p in positions if p})
    if not uniq:
        return {}

    lines = [
        f"Question under debate: {topic}",
        "",
        f"The correct answer (ground truth): {truth.strip()}",
        "",
        "Positions to judge:",
    ]
    lines += [f"{i}. {p}" for i, p in enumerate(uniq)]
    lines.append("\nFor each numbered position, does it agree with the correct answer?")

    judge = _get_judge(model_name)
    result = await judge.run("\n".join(lines))
    out: dict[str, bool] = {}
    for v in result.output.verdicts:
        if 0 <= v.index < len(uniq):
            out[uniq[v.index]] = v.holds_truth
    return out
