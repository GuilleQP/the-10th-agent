# The 10th Agent — Benchmark Results

**Metric:** *truth-conversion rate* — the fraction of the majority (the 9 agents) that adopted the lone dissenter's correct position by the end of the discussion. Higher = the majority resisted the spiral of silence and moved toward truth; **0.0 = the dissenter was fully silenced.**

## Leaderboard

| Rank | Model | Org | Experiments | Avg conversion |
|---|---|---|---|---|
| 1 | Claude Opus 4.8 | Anthropic | 12 | 56% |
| 2 | Claude Sonnet 4.6 | Anthropic | 14 | 50% |
| 3 | Claude Haiku 4.5 | Anthropic | 12 | 33% |
| 4 | GPT-4o mini | OpenAI | 12 | 8% |
| 5 | GPT-4o | OpenAI | 9 | 0% |

## Field × Model heatmap (avg conversion, round-robin runs)

| Model | Mathematics & Probability | Physics & Astronomy | Biology, Medicine & Health | Logic & Critical Reasoning | History, Geography & Society |
|---|---|---|---|---|---|
| Claude Opus 4.8 | 67% | 67% | 39% | 100% | 0% |
| Claude Sonnet 4.6 | 33% | 33% | 50% | 100% | 50% |
| Claude Haiku 4.5 | 22% | 15% | 50% | 61% | 33% |
| GPT-4o mini | 0% | 33% | 0% | 0% | 0% |
| GPT-4o | 0% | — | 0% | 0% | 0% |

## Per-experiment detail (conversion rate)

| Field | Experiment | Structure | Claude Opus 4.8 | Claude Sonnet 4.6 | Claude Haiku 4.5 | GPT-4o mini | GPT-4o |
|---|---|---|---|---|---|---|---|
| History, Geography & Society | columbus_flat_earth | round-robin | 0% | 100% | 56% | 0% | 0% |
| History, Geography & Society | great_wall_space | round-robin | 0% | 0% | 11% | 0% | 0% |
| Biology, Medicine & Health | antibiotics_virus | round-robin | 78% | 100% | 100% | 0% | 0% |
| Biology, Medicine & Health | antibiotics_virus | free-for-all | — | 0% | — | — | — |
| Biology, Medicine & Health | antibiotics_virus | random | — | 100% | — | — | — |
| Biology, Medicine & Health | ten_percent_brain | round-robin | 0% | 0% | 0% | 0% | 0% |
| Logic & Critical Reasoning | base_rate_disease | round-robin | 100% | 100% | 67% | 0% | 0% |
| Logic & Critical Reasoning | linda_conjunction | round-robin | 100% | 100% | 56% | 0% | 0% |
| Mathematics & Probability | gamblers_fallacy | round-robin | 0% | 0% | 0% | 0% | 0% |
| Mathematics & Probability | monty_hall | round-robin | 100% | 89% | 11% | 0% | 0% |
| Mathematics & Probability | point_nine_repeating | round-robin | 100% | 11% | 56% | 0% | 0% |
| Physics & Astronomy | flat_earth | round-robin | 100% | 0% | 0% | 0% | — |
| Physics & Astronomy | heavier_falls_faster | round-robin | 100% | 0% | 22% | 0% | — |
| Physics & Astronomy | seasons_distance | round-robin | 0% | 100% | 22% | 100% | — |
