# The 10th Agent, in n8n

The same Spiral of Silence chatroom as the Python engine, built as one n8n workflow.
Submit a case through a form, watch N agents debate, and get a results page saying
whether the truth spread or was silenced.

## Run it on n8n Cloud

1. In n8n: **Create workflow → ⋯ → Import from file** and pick [`the-10th-agent.json`](the-10th-agent.json).
2. Open the three model nodes (**Participant model**, **Judge model**, **Summarizer model**) and select your OpenAI credential.
3. Click **Test workflow**, then **Run the room** on the form. It comes pre-filled with Monty Hall.

A default run (10 agents, 3 epochs, `gpt-4o-mini`) makes about 35 model calls and
takes a minute or two.

## How it works

```
Form ─► Set up the room ─► Next speaker ─► Agent speaks ─► Record message ─► Epoch over?
                            ▲    ▲                                            │      │
                            │    └─────────── no: next agent's turn ──────────┘      │ yes
                            │                                                        ▼
                            │                                                 Judge positions
                            │                                                        ▼
                            │                                                  Score epoch
                            │                                                        ▼
                       Next epoch ◄── Summarize epoch ◄────────── no ────── Discussion over?
                                                                                     │ yes
                                                                                     ▼
                                                                  Build report ─► Show results
```

- **One turn per loop.** A single AI Agent node plays every participant. Each turn is a fresh
  call whose system prompt is that agent's persona, the same as `agent.run()` in `src/chatroom.py`.
  The state (transcript, summary, speaking orders) travels through the loop as one item.
- **Moderator.** At the end of each epoch, an LLM chain with a structured output parser judges
  every stated `[POSITION: ...]` against the ground truth (`src/judge.py`). If the whole room
  has converted, the run stops early.
- **Summaries.** Between epochs the discussion is condensed (`src/summarizer.py`), and the next
  epoch sees that summary plus its own messages.
- **Contamination.** A believer that holds the truth in epoch 1 *before the dissenter has spoken*
  never held the false belief. It is flagged and excluded from the conversion denominator
  (the `exclude` policy).

The prompts are copied verbatim from the Python engine, so results are comparable.

### Differences from the Python engine

- The judge runs every epoch rather than once after the run. This gives the per-epoch
  conversion curve live and drives early stopping, replacing the separate consensus judge.
- Contamination uses the LLM judge instead of keyword matching, so cases don't need
  `truth_keywords`/`false_keywords`.

## Editing

The workflow file is generated. Edit the Code node sources in [`js/`](js/) or the graph in
[`build.py`](build.py), then rebuild:

```bash
python n8n/build.py n8n/the-10th-agent.json
```

`--test <credential_id>` builds a variant with a Manual Trigger instead of the form, so
`n8n execute --id <id>` can run it from the CLI.
