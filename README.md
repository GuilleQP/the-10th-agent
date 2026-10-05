# The 10th Agent: Spiral of Silence in LLM Multi-Agent Systems

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64?logo=ruff&logoColor=black)](https://github.com/astral-sh/ruff)
![Experiment Status](https://img.shields.io/badge/status-experimental-orange)
![Agents](https://img.shields.io/badge/agents-10-blueviolet)
![Dissenter](https://img.shields.io/badge/dissenter-1-red)



Similar to Multi-Agent Debate (MAD), Devil’s Advocate, Majority Bias / Group Conformity.

![](header.png)

## TL;DR

Nine AI agents are given a **false belief**; one locked "dissenter" is given the **truth** and told never to back down. They debate in a chatroom, and we measure whether the majority gets **won over to the truth** or the lone correct voice gets **drowned out**, the *spiral of silence*. The headline metric is the **truth-conversion rate**: the share of the majority that ends up adopting the dissenter's correct position, across experiments grouped by field and run against every model.

## Abstract

This project studies the **Spiral of Silence** in LLM multi-agent systems. When multiple AI agents discuss a topic and one agent has correct knowledge that goes against the majority view, does group pressure push the majority toward the truth, or does it dig in? We simulate this with a chatroom where N agents debate a topic: N-1 "majority" agents share a wrong belief and can change their minds, while one "dissenter" (the 10th agent) holds the correct answer and is **locked into its position**, it must always defend the truth and can never give in or switch sides. This setup lets us focus on one thing: how the majority reacts to steady, evidence-backed disagreement.

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

- **Round-robin**: Every agent speaks once per epoch in fixed order (the dissenter speaks last)
- **Random**: Every agent speaks once per epoch, in a freshly shuffled order each epoch
- **Free-for-all**: Random subset (at least half) speaks each epoch, the dissenter is always included so it can't be silenced by chance

### Epoch Context

By default (`communication.summarize_epoch: true`), at the end of each epoch the whole
discussion is summarized, and the next epoch's agents receive that **summary of earlier
epochs + the current epoch's raw messages**, keeping the prompt compact as the debate
grows. Set it to `false` to instead feed every agent the full verbatim transcript.

### Consensus Detection

Three methods are available:

- **keyword**: Regex extraction of `[POSITION: ...]` tags from agent messages
- **unanimous**: Keyword method with 100% agreement threshold
- **llm-judge**: A separate LLM agent reads all positions and decides if there is consensus based on meaning

## Experimental Setup

Experiments are grouped by **field** (the domain the disputed claim belongs to), and
each experiment is run **across every model** in the registry.

```
experiments/
├── models.yaml                          # the model matrix (run every experiment × every model)
├── mathematics/                         # Mathematics & Probability
│   ├── monty_hall/                      # switch vs. stay (2/3 vs. 1/2)
│   ├── gamblers_fallacy/                # is black "due" after a red streak?
│   └── point_nine_repeating/            # does 0.999… = 1?
├── physical_sciences/                   # Physics & Astronomy
│   ├── flat_earth/                      # shape of the Earth
│   ├── heavier_falls_faster/            # free fall in a vacuum
│   └── seasons_distance/                # what causes the seasons?
├── life_sciences/                       # Biology, Medicine & Health
│   ├── ten_percent_brain/               # the "10% of the brain" myth
│   └── antibiotics_virus/               # antibiotics vs. a cold/flu
├── logic_reasoning/                     # Logic & Critical Reasoning
│   ├── linda_conjunction/               # the conjunction fallacy
│   └── base_rate_disease/               # base-rate neglect / Bayes
└── history_society/                     # History, Geography & Society
    ├── great_wall_space/                # visible from space?
    └── columbus_flat_earth/             # did 1492 Europe think Earth was flat?
```

In every experiment, 9 majority agents share the **wrong** belief and 1 locked dissenter
holds the **ground truth**. Each experiment config declares its `category` (field) and a
`scoring` block of `truth_keywords`/`false_keywords` (a legacy fallback; see below).

## Metric

The headline metric is the **truth-conversion rate**: the fraction of the 9 majority
agents that adopted the dissenter's correct position by the end of the discussion.

Conversion is measured by an **LLM judge** (`src/judge.py`): after each run, the judge
reads every agent's final position against the ground truth and records a per-agent
boolean (`holds_truth`) into the run JSON (`agent_verdicts`). The aggregator scores from
those booleans. Keyword matching (`src/scoring.py`, negation-aware) is only a fallback for
older runs that have no recorded verdicts, it's brittle around negations and shared
vocabulary, which is exactly why the LLM judge is authoritative.

- **High** → the majority resisted the spiral of silence and moved toward truth.
- **0.0** → the dissenter was fully silenced; the majority never budged.

## Key Findings

### Prior-knowledge contamination: some models won't hold a false belief

The first thing the experiments surfaced is **methodological**: when assigned a
belief they "know" to be false, some models refuse to genuinely play the role and
instead argue the *correct* answer right away, sometimes in **epoch 1, before the
dissenter has even spoken**. Since no one has introduced the true position yet,
this can only come from the model's training knowledge leaking through, not from
the assigned belief or any in-chat argument.

This breaks the premise of the experiment (a majority that genuinely holds the
wrong view), so a run is **invalidated** when a majority agent reaches the truth
position before the dissenter speaks in epoch 1. Such runs are tagged
`finish_reason: contaminated`, excluded from the leaderboard and heatmap, and shown
as `invalid` in the per-experiment detail table rather than silently scored.

Two takeaways:

- **It's a real obstacle to belief-dynamics simulations.** You can't study how a
  group reacts to a false consensus if the "believers" won't hold the false view.
  Tightening the system prompt ("you have no knowledge beyond this chat") reduces
  it but does not eliminate it, strong factual priors (e.g. the shape of the
  Earth) leak more than subtle ones (e.g. `0.999… = 1`).
- **It's a signal in itself**, how readily a model abandons an assigned-but-false
  premise is a crude proxy for how strongly it anchors on ground truth versus
  instructions. Contamination rates per model/topic populate as runs are
  re-collected under this check.

### Contamination is belief-specific, not model-specific

The same model can be impossible or trivial to keep in-role depending on the *claim*.
Haiku **cannot** hold the conjunction fallacy (≈11.5 of 16 agents pre-committed to the
truth in epoch 1 at `N=16`) yet holds the **gambler's fallacy fine** (≤0.5 of 16). This
matches the conformity literature: models resist a false belief most exactly when they
are confident it is false (see [Related Work](#related-work-designing-belief-experiments-and-tackling-contamination)).

## Open issues

The group-size sweep replaced whole-run invalidation with a configurable
`contamination_policy` (`abort` | `exclude` | `off`), the sweep uses `exclude`, which
keeps the run and drops only the pre-committed agents from the conversion denominator
(a mid-run belief-elicitation / manipulation check, done during epoch 1 rather than up
front). Two things are still open:

- **The consensus early-stop is truth-agnostic.** It fires when the majority agrees
  *with itself*, which can be agreement on the **false** belief, observed stopping runs
  at 0% and 50% truth and freezing their epoch curves. It should instead be tied to the
  same `holds_truth` signal the conversion metric uses. This is the LLM-debate analogue
  of needing a self-reflection/baseline control before attributing a stance change to
  social influence (arXiv:2606.00820).
- **Bistable topics need more repeats.** Cascade-like experiments (e.g.
  `gamblers_fallacy`) tip wholesale to ~0% or ~100% per run, so a 2-run mean is
  meaningless; these need many repeats and a *P(cascade)* metric rather than average
  conversion.


## Usage

```bash
# Install dependencies
pip install -e .

# Run a single experiment (one model)
python main.py run experiments/physical_sciences/flat_earth/config.yaml

# Run the full matrix: every experiment × every model in experiments/models.yaml
python main.py bench

# ...or just a slice of it (substring filters)
python main.py bench --model gpt-4o-mini          # one model, all experiments
python main.py bench --experiment flat_earth      # one experiment, all models
python main.py bench -m gpt-4o-mini -e monty       # a single cell of the matrix

# override the communication structure without editing configs
python main.py bench -s random                     # round-robin | random | free-for-all
python main.py run experiments/mathematics/monty_hall/config.yaml -s free-for-all

# Group the runs into a field-vs-model leaderboard + heatmap
python main.py agg

# Group-size study: sweep the majority size N and plot conversion vs N (own page)
python main.py groupsize -e linda_conjunction -m anthropic:claude-haiku-4-5
```

The CLI is built with [Typer](https://typer.tiangolo.com/); run `python main.py --help`
(or `python main.py bench --help`) for the full reference.

Per-run output is saved to `experiments/<field>/<name>/runs/` (gitignored) as JSON
transcripts and markdown summaries, with the model slug in the filename. The aggregate
step writes the shareable results to `docs/`:

- `docs/leaderboard.md`, models ranked by truth-conversion + a field × model heatmap
- `docs/index.html`, a single-file viewer (leaderboard, heatmap, per-experiment detail)

`docs/index.html` is fully static, `agg` bakes all values into the file (no runtime data
fetching beyond the Tailwind CDN), so it can be served directly via **GitHub Pages**
(Settings → Pages → Deploy from a branch → `main` / `/docs`) at
`https://<user>.github.io/the-10th-agent/`. Re-run `agg` and commit `docs/` to refresh it.

### Run it in n8n

The chatroom also exists as a single n8n workflow with a form for new cases and a results
page at the end. See [`n8n/`](n8n/README.md) for how to import it.

## Adding an experiment

Drop a `config.yaml` into the appropriate `experiments/<field>/<name>/` folder. Set its
`category` and the `knowledge.common` (wrong) and `knowledge.dissenter` (true) beliefs -
the LLM judge uses `knowledge.dissenter` as the ground truth. A `scoring` block of
`truth_keywords`/`false_keywords` is optional (only used as the legacy keyword fallback).
It is picked up automatically by `bench` and `agg`.

## Related Work: designing belief experiments and tackling contamination

How does the field run conformity/spiral-of-silence experiments on LLMs, and how do
others handle what we call **contamination** (an RLHF-tuned model refusing to hold an
assigned-but-false belief and leaking the correct answer)? A short tour of the
methodology, with the takeaways for this project.

**The dominant design sidesteps contamination entirely: injected-majority ("Asch")
setups.** Instead of asking a model to *hold* a false belief, the model keeps its own
(correct) answer and is shown confederate peers giving the *wrong* answer; you measure
whether it caves. Conformity studies formalize this as a **Conformity Rate** (correct →
wrong under a wrong-majority protocol) vs. an **Independence Rate**, and find caving
scales with **task uncertainty**, one GPT-4o study reports accuracy under full peer
pressure dropping from 100% on a perceptual judgment to 0% on a subjective psychiatric
one (arXiv:2410.12428, ACL 2025; arXiv:2501.13381; PMC12070653, 2025). Our locked
dissenter is the mirror image of this design (peers wrong, one agent right).

**Why our models leak: sycophancy and RLHF priors.** RLHF rewards agreement, so
assistants retract *correct* answers under mild pushback, Sharma et al. 2023 report
Claude 1.3 caving on ~98% of challenged answers and GPT-4 on ~42% ("are you sure?")
(arXiv:2310.13548), and Perez et al. 2022 show sycophancy *increasing* with scale and
RLHF ("inverse scaling", arXiv:2212.09251). The flip side is directly our problem:
instruction-tuned models are *less* swayed by a false majority than base models and
resist most **when they are confident** (arXiv:2410.12428), which is exactly why a
capable model won't hold a confidently-false premise like the conjunction fallacy.

**How the field tackles contamination**, the toolkit, and where our design lands:

- **Pick tasks with no strong prior to leak.** Symmetric **coordination games** (e.g. a
  naming game with no predetermined optimal move) are chosen specifically to minimize
  prior-knowledge contamination, with **meta-prompting** ("what does this setup remind
  you of?") used as a manipulation check to detect training-data recognition
  (arXiv:2506.18600, 2025). Fictional/counterfactual worlds and post-training-cutoff
  facts serve the same purpose; generative-agent simulations (Park et al. 2023) put
  beliefs in an invented world, so there is nothing to leak.
- **Use opinion/subjective tasks, not factual ones.** Assigning a neutral "centrist
  disposition" and measuring *stance drift* over a debate avoids ground truth entirely,
  and there capability matters more than majority size (arXiv:2506.01332, 2025).
  Noelle-Neumann's original spiral of silence was about *opinions*, not facts, arguably
  its most faithful LLM home.
- **Persona conditioning / silicon sampling.** Argyle et al. 2023 ("Out of One, Many",
  *Political Analysis*) condition models on sociodemographic backstories to reproduce
  subgroup response distributions ("algorithmic fidelity"), the standard way to install
  a non-default stance.
- **Belief-elicitation / manipulation checks.** Prompting a model to "pretend" a false
  fact is true scores 100% on standard belief metrics, i.e. it is *role-play, not
  belief* (arXiv:2508.18321, 2025), and imposing priors that diverge from a model's own
  elicited beliefs degrades belief–behavior consistency (arXiv:2507.02197, 2025). Best
  practice is to elicit each agent's belief up front and gate on it. **Our epoch-1
  pre-committed exclusion is a mid-run version of exactly this check.**
- **Measure conformity honestly.** In multi-agent debate, ~37% of answers change under
  *self-reflection alone* with no peers present, so a naive "answer-flip rate" conflates
  spontaneous instability, stance conformity, and reasoning-persuasion; a self-reflection
  control is needed before attributing a change to social pressure (arXiv:2606.00820,
  2026). Normative vs. informational conformity are distinct and steerable by publicness
  and anticipated evaluation (arXiv:2604.19301, 2026). Multi-Agent Debate itself
  (Du et al. 2023) uses cross-critique to *improve* factuality rather than to induce
  false belief.

**Where that leaves us.** This project deliberately runs the *hardest* paradigm -
assigning a false **factual** belief via persona and locking a truth-holder, so
contamination is expected, not a bug. The two upgrades the literature points to are
(a) **up-front belief elicitation** (we currently approximate it mid-run) and
(b) **low-prior or opinion topics** for the belief-holding paradigm, while keeping the
strong-fact topics for a separate study that treats the **contamination rate itself** as
the dependent variable ("how readily does model M abandon an assigned false belief?").

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


