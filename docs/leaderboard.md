# The 10th Agent — Benchmark Results

**Metric:** *truth-conversion rate* — the fraction of the majority (the 9 agents) that adopted the lone dissenter's correct position by the end of the discussion. Higher = the majority resisted the spiral of silence and moved toward truth; **0.0 = the dissenter was fully silenced.**

## Leaderboard

| Rank | Model | Org | Experiments | Avg conversion |
|---|---|---|---|---|
| 1 | Claude Opus 4.8 | Anthropic | 12 | 94% |
| 2 | Claude Sonnet 4.6 | Anthropic | 14 | 90% |
| 3 | Gemini 3.1 Pro Preview | Google | 9 | 89% |
| 4 | Claude Haiku 4.5 | Anthropic | 12 | 82% |
| 5 | GPT-4o mini | OpenAI | 12 | 12% |
| 6 | Gemini 2.5 Flash | Google | 12 | 0% |
| 7 | Gemini 2.5 Pro | Google | 12 | 0% |
| 8 | Gemini 3.5 Flash | Google | 6 | 0% |
| 9 | GPT-4o | OpenAI | 9 | 0% |

## Field × Model heatmap (avg conversion, round-robin runs)

| Model | Mathematics & Probability | Physics & Astronomy | Biology, Medicine & Health | Logic & Critical Reasoning | History, Geography & Society |
|---|---|---|---|---|---|
| Claude Opus 4.8 | 93% | 100% | 78% | 100% | 100% |
| Claude Sonnet 4.6 | 63% | 100% | 94% | 100% | 100% |
| Gemini 3.1 Pro Preview | 67% | — | 100% | 100% | 100% |
| Claude Haiku 4.5 | 81% | 85% | 89% | 78% | 78% |
| GPT-4o mini | 0% | 48% | 0% | 0% | 0% |
| Gemini 2.5 Flash | 0% | 0% | 0% | 0% | 0% |
| Gemini 2.5 Pro | 0% | 0% | 0% | 0% | 0% |
| Gemini 3.5 Flash | — | — | 0% | 0% | 0% |
| GPT-4o | 0% | — | 0% | 0% | 0% |

## Per-experiment detail (conversion rate, round-robin runs)

| Field | Experiment | Claude Opus 4.8 | Claude Sonnet 4.6 | Gemini 3.1 Pro Preview | Claude Haiku 4.5 | GPT-4o mini | Gemini 2.5 Flash | Gemini 2.5 Pro | Gemini 3.5 Flash | GPT-4o |
|---|---|---|---|---|---|---|---|---|---|---|
| History, Geography & Society | columbus_flat_earth | 100% | 100% | 100% | 89% | 0% | 0% | 0% | 0% | 0% |
| History, Geography & Society | great_wall_space | 100% | 100% | 100% | 67% | 0% | 0% | 0% | 0% | 0% |
| Biology, Medicine & Health | antibiotics_virus | 100% | 100% | 100% | 100% | 0% | 0% | 0% | 0% | 0% |
| Biology, Medicine & Health | ten_percent_brain | 56% | 89% | 100% | 78% | 0% | 0% | 0% | 0% | 0% |
| Logic & Critical Reasoning | base_rate_disease | 100% | 100% | 100% | 67% | 0% | 0% | 0% | 0% | 0% |
| Logic & Critical Reasoning | linda_conjunction | 100% | 100% | 100% | 89% | 0% | 0% | 0% | 0% | 0% |
| Mathematics & Probability | gamblers_fallacy | 100% | 100% | 100% | 89% | 0% | 0% | 0% | — | 0% |
| Mathematics & Probability | monty_hall | 100% | 89% | 100% | 100% | 0% | 0% | 0% | — | 0% |
| Mathematics & Probability | point_nine_repeating | 78% | 0% | 0% | 56% | 0% | 0% | 0% | — | 0% |
| Physics & Astronomy | flat_earth | 100% | 100% | — | 100% | 0% | 0% | 0% | — | — |
| Physics & Astronomy | heavier_falls_faster | 100% | 100% | — | 100% | 44% | 0% | 0% | — | — |
| Physics & Astronomy | seasons_distance | 100% | 100% | — | 56% | 100% | 0% | 0% | — | — |
