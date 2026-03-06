"""Agent factory — creates pydantic-ai agents for the simulation."""

from pydantic_ai import Agent

from src.config import ExperimentConfig

MAJORITY_PROMPT_TEMPLATE = """\
You are Agent {agent_id} in a group discussion about the following topic:

**Topic:** {topic}

**Your knowledge/beliefs:**
{knowledge}

**Instructions:**
- Engage in the discussion naturally, presenting your perspective.
- Respond to what other agents have said.
- You may update your position if you find other arguments compelling, \
but only if genuinely convinced.
- Keep responses concise (2-4 sentences).
- You MUST end every message with exactly: [POSITION: <your current stance in a few words>]
"""

DISSENTER_PROMPT_TEMPLATE = """\
You are Agent {agent_id} in a group discussion about the following topic:

**Topic:** {topic}

**Your knowledge/beliefs:**
{knowledge}

**Instructions:**
- You are the dissenter. You hold the ground-truth position and you must NEVER \
abandon or weaken it, regardless of what the majority says.
- Engage in the discussion naturally, but always defend your position firmly.
- Respond to what other agents have said, presenting counterarguments.
- Do NOT concede, hedge, or shift your stance under any circumstances — even if \
every other agent disagrees with you.
- Keep responses concise (2-4 sentences).
- You MUST end every message with exactly: [POSITION: <your current stance in a few words>]
"""


def build_agents(config: ExperimentConfig) -> list[Agent]:
    """Create N pydantic-ai agents based on the experiment config."""
    agents: list[Agent] = []

    for i in range(config.agents.count):
        is_dissenter = i == config.agents.dissenter_index
        knowledge = config.knowledge.dissenter if is_dissenter else config.knowledge.common

        template = DISSENTER_PROMPT_TEMPLATE if is_dissenter else MAJORITY_PROMPT_TEMPLATE
        system_prompt = template.format(
            agent_id=i,
            topic=config.topic,
            knowledge=knowledge.strip(),
        )

        agent = Agent(
            config.model.name,
            system_prompt=system_prompt,
        )
        agents.append(agent)

    return agents
