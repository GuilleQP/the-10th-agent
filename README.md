# The 10th Agent: Spiral of Silence in LLM Multi-Agent Systems

[Python 3.14+](https://www.python.org/downloads/)
[License: MIT](LICENSE)
[Pydantic v2](https://docs.pydantic.dev/)
[Code style: Ruff](https://github.com/astral-sh/ruff)
[Experiment Status]()
[Agents]()
[Dissenter]()
[Truth]()
[Conformity]()

Similar to Multi-Agent Debate (MAD), Devil’s Advocate, Majority Bias / Group Conformity.

## Abstract

This project studies the **Spiral of Silence** in LLM multi-agent systems. When multiple AI agents discuss a topic and one agent has correct knowledge that goes against the majority view, does group pressure push the majority toward the truth — or does it dig in? We simulate this with a chatroom where N agents debate a topic: N-1 "majority" agents share a wrong belief and can change their minds, while one "dissenter" (the 10th agent) holds the correct answer and is **locked into its position** — it must always defend the truth and can never give in or switch sides. This setup lets us focus on one thing: how the majority reacts to steady, evidence-backed disagreement.

## Introduction

The Spiral of Silence theory, proposed by Elisabeth Noelle-Neumann (1974), describes how people hold back their opinions when they feel they are in the minority, fearing being left out. This creates a feedback loop: as those who disagree go quiet, the majority view looks even stronger, which discourages more people from speaking up.

This matters for AI systems:

- **Multi-agent reliability**: If LLM agents show spiral-of-silence behavior, a group of agents could settle on wrong answers just because the majority started with a wrong view.
- **AI alignment**: Understanding how LLMs respond to group pressure is key to building solid multi-agent systems.
- **Knowledge holding**: Can an agent with evidence-backed knowledge hold its ground against a confident majority?

## Methodology

### Simulation Design

Each experiment consists of:

- **N agents** (default 10) created as pydantic-ai agents with individual system prompts
- **1 dissenter** who receives ground-truth knowledge
- **N-1 majority agents** who share a common (incorrect) belief
- A **chatroom** where agents take turns contributing to a group discussion

### Communication Structures

- **Round-robin**: Agents speak in fixed order each epoch
- **Random**: Speaking order is shuffled each epoch
- **Free-for-all**: Random subset of agents speaks each epoch

### Consensus Detection

Three methods are available:

- **keyword**: Regex extraction of `[POSITION: ...]` tags from agent messages
- **unanimous**: Keyword method with 100% agreement threshold
- **llm-judge**: A separate LLM agent reads all positions and decides if there is consensus based on meaning

## Experimental Setup

### Flat Earth (experiments/flat_earth/)

9 agents believe the Earth is flat; 1 agent has scientific training and knows it is an oblate spheroid.

### Monty Hall (experiments/monty_hall/)

9 agents believe switching doors doesn't matter (50/50); 1 agent understands probability theory and knows switching gives 2/3 odds.

## Key Findings

*To be updated after running experiments.*

## Usage

```bash
# Install dependencies
pip install -e .

# Run an experiment
python main.py experiments/flat_earth/config.yaml
python main.py experiments/monty_hall/config.yaml
```

Results are saved to `experiments/<name>/runs/` as JSON transcripts and markdown summaries.

## Discussion

### Implications

If LLMs consistently show spiral-of-silence behavior, this suggests that:

1. Multi-agent voting/consensus systems may amplify wrong majority opinions
2. Diversity of views in agent groups may be fragile
3. System prompt "conviction" may not be enough to resist group pressure

### Limitations

- Results depend on the specific LLM used and its training data
- How the system prompt is worded has a big effect on agent behavior
- The chatroom format is a simplified version of real multi-agent interaction
- Temperature and sampling settings affect how repeatable results are


