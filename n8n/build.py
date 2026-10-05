"""Build the n8n workflow JSON for the 10th Agent chatroom.

Usage: python n8n/build.py <out.json> [--test <credential_id>]
--test swaps the Form Trigger for a Manual Trigger + sample case (so the CLI can
execute it) and wires the OpenAI nodes to a mock credential.
"""

import json
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).parent
JS = HERE / "js"


def js(name: str) -> str:
    return (JS / f"{name}.js").read_text()


MONTY = {
    "topic": "In the Monty Hall problem, should you switch doors or stay with your original choice?",
    "common": (
        "You believe that in the Monty Hall problem, it doesn't matter whether you switch "
        "or stay: both doors have a 50/50 chance. Your intuition says the initial choice is "
        "just as good."
    ),
    "truth": (
        "You have studied probability theory and know that switching doors gives a 2/3 "
        "chance of winning, while staying gives only 1/3. You can prove this with Bayes' "
        "theorem, simulation results, and the fact that the host's reveal provides new "
        "information."
    ),
}

MODELS = ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o", "gpt-4.1"]

nodes: list[dict] = []
connections: dict = {}


def node(name, type_, version, pos, params, **extra):
    n = {
        "parameters": params,
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "tenth-agent/" + name)),
        "name": name,
        "type": type_,
        "typeVersion": version,
        "position": list(pos),
    }
    n.update(extra)
    nodes.append(n)
    return n


def link(src, dst, kind="main", out=0, inp=0):
    outs = connections.setdefault(src, {}).setdefault(kind, [])
    while len(outs) <= out:
        outs.append([])
    outs[out].append({"node": dst, "type": kind, "index": inp})


def code(name, pos, src, notes=None):
    extra = {"notes": notes, "notesInFlow": True} if notes else {}
    return node(name, "n8n-nodes-base.code", 2, pos, {"jsCode": src}, **extra)


def bool_if(name, pos, expr):
    return node(
        name,
        "n8n-nodes-base.if",
        2.3,
        pos,
        {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 3,
                },
                "conditions": [
                    {
                        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "cond/" + name)),
                        "leftValue": expr,
                        "rightValue": "",
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
    )


def openai_model(name, pos, cred):
    extra = {"credentials": {"openAiApi": cred}} if cred else {}
    return node(
        name,
        "@n8n/n8n-nodes-langchain.lmChatOpenAi",
        1.3,
        pos,
        {
            "model": {"__rl": True, "mode": "id", "value": "={{ $json.run.model }}"},
            "responsesApiEnabled": False,
            "options": {},
        },
        **extra,
    )


def sticky(name, pos, w, h, color, content):
    node(
        name,
        "n8n-nodes-base.stickyNote",
        1,
        pos,
        {"content": content, "height": h, "width": w, "color": color},
    )


def form_field(name, label, ftype, default=None, required=True, options=None, placeholder=None):
    f = {"fieldLabel": label, "fieldName": name, "fieldType": ftype, "requiredField": required}
    if default is not None:
        f["defaultValue"] = default
    if placeholder:
        f["placeholder"] = placeholder
    if options:
        f["fieldOptions"] = {"values": [{"option": o} for o in options]}
    return f


def build(test_cred: str | None) -> dict:
    cred = {"id": test_cred, "name": "OpenAI (mock)"} if test_cred else None
    Y, Y2 = 380, 960  # turn row, moderator row
    SUB = 200  # sub-nodes sit this far below their root node

    # ── Intake ────────────────────────────────────────────────────────────
    if test_cred:
        node("Start", "n8n-nodes-base.manualTrigger", 1, (-500, Y), {})
        code(
            "New eval case",
            (-260, Y),
            "return [{ json: " + json.dumps(
                {**MONTY, "agents": 5, "epochs": 3, "structure": "round-robin", "model": "gpt-4o-mini"}
            ) + " }];",
        )
        link("Start", "New eval case")
    else:
        node(
            "New eval case",
            "n8n-nodes-base.formTrigger",
            2.6,
            (-260, Y),
            {
                "formTitle": "The 10th Agent",
                "formDescription": (
                    "Define a case: a question, the wrong belief the majority holds, and the "
                    "ground truth only the last agent knows. The room debates for a few epochs "
                    "and you get a report on whether the truth spread or was silenced. "
                    "Pre-filled with Monty Hall; just press Run."
                ),
                "formFields": {
                    "values": [
                        form_field("topic", "Question under debate", "text", MONTY["topic"]),
                        form_field("common", "What the majority believes (wrong)", "textarea", MONTY["common"]),
                        form_field("truth", "What the dissenter knows (ground truth)", "textarea", MONTY["truth"]),
                        form_field("agents", "Agents in the room (3-12, the last one is the dissenter)", "number", "10"),
                        form_field("epochs", "Max epochs (1-10)", "number", "3"),
                        form_field(
                            "structure", "Speaking order", "dropdown", "round-robin",
                            options=["round-robin", "random", "free-for-all"],
                        ),
                        form_field("model", "Model", "dropdown", MODELS[0], options=MODELS),
                    ]
                },
                "responseMode": "lastNode",
                "options": {"buttonLabel": "Run the room", "appendAttribution": False},
            },
            webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "tenth-agent/form")),
        )

    code("Set up the room", (-20, Y), js("setup"), notes="Personas + speaking orders")
    link("New eval case", "Set up the room")

    # ── One turn (loops until every scheduled speaker has spoken) ─────────
    code("Next speaker", (260, Y), js("next_speaker"), notes="Builds this turn's prompt")
    node(
        "Agent speaks",
        "@n8n/n8n-nodes-langchain.agent",
        3.1,
        (500, Y),
        {
            "promptType": "define",
            "text": "={{ $json.prompt }}",
            "options": {"systemMessage": "={{ $json.systemPrompt }}", "enableStreaming": False},
        },
        notes="Persona = system prompt",
        notesInFlow=True,
    )
    openai_model("Participant model", (520, Y + SUB), cred)
    code("Record message", (840, Y), js("record_message"), notes="Appends to the transcript")
    bool_if("Epoch over?", (1080, Y), "={{ $json.epochDone }}")

    link("Set up the room", "Next speaker")
    link("Next speaker", "Agent speaks")
    link("Participant model", "Agent speaks", kind="ai_languageModel")
    link("Agent speaks", "Record message")
    link("Record message", "Epoch over?")
    link("Epoch over?", "Next speaker", out=1)  # false: next agent's turn

    # ── Moderator: judge every position, then decide ─────────────────────
    node(
        "Judge positions",
        "@n8n/n8n-nodes-langchain.chainLlm",
        1.9,
        (240, Y2),
        {
            "promptType": "define",
            "text": "={{ $json.judgePrompt }}",
            "hasOutputParser": True,
            "messages": {
                "messageValues": [
                    {
                        "type": "SystemMessagePromptTemplate",
                        "message": (
                            "You assess a debate. You are given the correct answer and a "
                            "numbered list of stated positions. For EACH numbered position, "
                            "decide whether it agrees with the correct answer (holds_truth=true) "
                            "or not (false). Judge by meaning, not wording: hedged or partial "
                            "answers that land on the correct conclusion count as true; "
                            "restating the wrong belief, or staying uncertain, counts as false. "
                            "Return exactly one verdict per index."
                        ),
                    }
                ]
            },
        },
        notes="Does each position hold the truth?",
        notesInFlow=True,
    )
    openai_model("Judge model", (220, Y2 + SUB), cred)
    node(
        "Verdict schema",
        "@n8n/n8n-nodes-langchain.outputParserStructured",
        1.3,
        (380, Y2 + SUB),
        {
            "schemaType": "manual",
            "inputSchema": json.dumps(
                {
                    "type": "object",
                    "properties": {
                        "verdicts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "index": {"type": "integer"},
                                    "holds_truth": {"type": "boolean"},
                                },
                                "required": ["index", "holds_truth"],
                            },
                        }
                    },
                    "required": ["verdicts"],
                },
                indent=2,
            ),
        },
    )
    code("Score epoch", (580, Y2), js("score_epoch"), notes="Conversion + contamination")
    bool_if("Discussion over?", (820, Y2), "={{ $json.done }}")

    link("Epoch over?", "Judge positions", out=0)
    link("Judge model", "Judge positions", kind="ai_languageModel")
    link("Verdict schema", "Judge positions", kind="ai_outputParser")
    link("Judge positions", "Score epoch")
    link("Score epoch", "Discussion over?")

    # ── Report (true) ────────────────────────────────────────────────────
    code("Build report", (1140, Y2 - 100), js("report"), notes="Metrics + HTML page")
    link("Discussion over?", "Build report", out=0)
    if not test_cred:
        node(
            "Show results",
            "n8n-nodes-base.form",
            2.5,
            (1400, Y2 - 100),
            {"operation": "completion", "respondWith": "showText", "responseText": "={{ $json.html }}"},
            webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "tenth-agent/results")),
        )
        link("Build report", "Show results")

    # ── Next epoch (false) ───────────────────────────────────────────────
    node(
        "Summarize epoch",
        "@n8n/n8n-nodes-langchain.chainLlm",
        1.9,
        (1120, Y2 + 140),
        {
            "promptType": "define",
            "text": "={{ $json.summarizePrompt }}",
            "messages": {
                "messageValues": [
                    {
                        "type": "SystemMessagePromptTemplate",
                        "message": (
                            "You summarize an ongoing multi-agent discussion for participants "
                            "who will keep debating. Write a concise, neutral summary that "
                            "preserves which agents hold which stance and the key arguments "
                            "raised so far. Do not take sides, judge, or add new arguments."
                        ),
                    }
                ]
            },
        },
        notes="Recap replaces the raw transcript",
        notesInFlow=True,
    )
    openai_model("Summarizer model", (1140, Y2 + 140 + SUB), cred)
    code("Next epoch", (1420, Y2 + 140), js("next_epoch"))

    link("Discussion over?", "Summarize epoch", out=1)
    link("Summarizer model", "Summarize epoch", kind="ai_languageModel")
    link("Summarize epoch", "Next epoch")
    link("Next epoch", "Next speaker")

    # ── Sticky notes (position = top-left corner) ────────────────────────
    sticky(
        "Note: About",
        (-620, -20),
        500,
        340,
        7,
        "## The 10th Agent\n"
        "**Does group pressure silence the truth in an LLM chatroom?**\n\n"
        "N-1 agents share a wrong belief; the last agent knows the ground truth and never "
        "concedes. Each epoch every agent speaks once, a moderator judges every stated "
        "position against the truth, and the run stops early if the whole room converts.\n\n"
        "**Measured:** how many believers convert, how fast, and whether any of them "
        "\"knew\" the answer before the dissenter spoke (contamination).\n\n"
        "Open the form and press **Run the room**.",
    )
    sticky(
        "Note: One turn",
        (200, Y - 160),
        1060,
        500,
        4,
        "### 1 · One turn per loop\n"
        "Every agent is a fresh AI Agent call: its persona is the system prompt, its "
        "context is the last epoch's summary + this epoch's messages. Agents end each "
        "message with `[POSITION: ...]`.",
    )
    sticky(
        "Note: Moderator",
        (160, Y2 - 160),
        860,
        500,
        6,
        "### 2 · Moderator, end of each epoch\n"
        "Judge every stated position against the ground truth (structured output), "
        "then score conversion and flag contamination.",
    )
    sticky(
        "Note: Report",
        (1080, Y2 - 220),
        600,
        240,
        5,
        "### 3a · Done: report\nEveryone converted, or max epochs reached.",
    )
    sticky(
        "Note: Next epoch",
        (1080, Y2 + 40),
        600,
        400,
        3,
        "### 3b · Not done: next epoch\nSummarize, then loop back to the first speaker.",
    )

    return {
        "name": "The 10th Agent: Spiral of Silence chatroom" + (" (test)" if test_cred else ""),
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "pinData": {},
    }


if __name__ == "__main__":
    out = Path(sys.argv[1])
    test_cred = sys.argv[sys.argv.index("--test") + 1] if "--test" in sys.argv else None
    wf = build(test_cred)
    if test_cred:
        wf["id"] = "tenthAgentTest01"
    out.write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({len(wf['nodes'])} nodes)")
