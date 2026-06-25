"""Per-epoch chat summarization.

When ``communication.summarize_epoch`` is enabled, the whole discussion is
condensed at the end of each epoch so the next epoch's agents get a compact
summary instead of the full (and ever-growing) transcript.
"""

from __future__ import annotations

from pydantic_ai import Agent

from src.results import ChatMessage

# Cache one summarizer agent per model name (so the benchmark matrix, which
# runs many models, doesn't reuse the first model's agent for all of them).
_summarizers: dict[str, Agent[None, str]] = {}


def _get_summarizer(model_name: str) -> Agent[None, str]:
    if model_name not in _summarizers:
        _summarizers[model_name] = Agent(
            model_name,
            output_type=str,
            system_prompt=(
                "You summarize an ongoing multi-agent discussion for participants "
                "who will keep debating. Write a concise, neutral summary that "
                "preserves which agents hold which stance and the key arguments "
                "raised so far. Do not take sides, judge, or add new arguments."
            ),
        )
    return _summarizers[model_name]


async def summarize_transcript(
    messages: list[ChatMessage], topic: str, model_name: str
) -> str:
    """Summarize the discussion so far into a short neutral recap."""
    lines = [f"Topic: {topic}\n", "Discussion to summarize:\n"]
    for m in messages:
        lines.append(f"Agent {m.agent_id} (Epoch {m.epoch}): {m.content}\n")
    lines.append("\nWrite a concise summary of the discussion above.")

    agent = _get_summarizer(model_name)
    result = await agent.run("\n".join(lines))
    return result.output
