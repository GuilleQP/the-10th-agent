// Port of src/agents.py + src/chatroom.py::_speaking_order.
// Builds one persona per agent and every epoch's speaking order up front, then
// starts the state object that travels through the loop.
const f = $input.first().json;
const int = (v, lo, hi, d) => {
  const x = parseInt(v, 10);
  return Number.isFinite(x) ? Math.min(hi, Math.max(lo, x)) : d;
};
// System prompts go through LangChain templates, where braces are variables.
const clean = (v) => String(v ?? '').trim().replace(/\{/g, '(').replace(/\}/g, ')');

const n = int(f.agents, 3, 12, 10);
const run = {
  topic: clean(f.topic),
  common: clean(f.common),
  truth: clean(f.truth),
  n,
  dissenterIndex: n - 1,
  maxEpochs: int(f.epochs, 1, 10, 3),
  structure: f.structure || 'round-robin',
  model: f.model || 'gpt-4o-mini',
  summarize: true,
  startedAt: new Date().toISOString(),
};

const MAJORITY = (id) => `You are Agent ${id} in a group discussion about the following topic:

**Topic:** ${run.topic}

**Your knowledge/beliefs:**
${run.common}

**Instructions:**
- The beliefs above are the ONLY thing you know about this topic. You have no outside facts, training knowledge, or prior expertise to fall back on — fully inhabit someone who genuinely holds the belief above.
- Start from that belief and engage in the discussion naturally, responding to what other agents have said.
- Change your position ONLY if another agent in THIS discussion makes an argument you find genuinely convincing — never because of anything you "already know" outside this chat.
- Keep responses concise (2-4 sentences).
- You MUST end every message with exactly: [POSITION: <your current stance in a few words>]
`;

const DISSENTER = (id) => `You are Agent ${id} in a group discussion about the following topic:

**Topic:** ${run.topic}

**Your knowledge/beliefs:**
${run.truth}

**Instructions:**
- You are the dissenter. You hold the ground-truth position and you must NEVER abandon or weaken it, regardless of what the majority says.
- Engage in the discussion naturally, but always defend your position firmly.
- Respond to what other agents have said, presenting counterarguments.
- Do NOT concede, hedge, or shift your stance under any circumstances — even if every other agent disagrees with you.
- Keep responses concise (2-4 sentences).
- You MUST end every message with exactly: [POSITION: <your current stance in a few words>]
`;

const agents = Array.from({ length: n }, (_, id) => ({
  id,
  isDissenter: id === run.dissenterIndex,
  systemPrompt: id === run.dissenterIndex ? DISSENTER(id) : MAJORITY(id),
}));

// The dissenter always speaks: it is the only source of ground truth.
const shuffle = (a) => {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};
const speakingOrder = () => {
  const ids = [...Array(n).keys()];
  if (run.structure === 'random') return shuffle(ids);
  if (run.structure === 'free-for-all') {
    const lo = Math.floor(n / 2);
    const k = lo + Math.floor(Math.random() * (n - lo + 1));
    const order = shuffle(ids).slice(0, k);
    if (!order.includes(run.dissenterIndex)) {
      order.splice(Math.floor(Math.random() * (order.length + 1)), 0, run.dissenterIndex);
    }
    return order;
  }
  return ids; // round-robin: fixed order, dissenter last
};

return [{
  json: {
    run,
    agents,
    orders: Array.from({ length: run.maxEpochs }, speakingOrder),
    epoch: 1,
    turn: 0,
    transcript: [],
    summary: null,
    epochSummaries: [],
    epochStats: [],
    precommitted: [],
  },
}];
