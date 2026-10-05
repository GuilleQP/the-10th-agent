// Apply the judge's verdicts, measure conversion, and decide whether to stop.
// Contamination: a believer that holds the truth in epoch 1 *before the
// dissenter has spoken* never held the false belief (prior-knowledge leak).
// It is excluded from the denominator (the repo's EXCLUDE policy).
const s = { ...$('Record message').first().json };
const out = $input.first().json.output ?? {};
const verdicts = Array.isArray(out.verdicts) ? out.verdicts : [];

const vmap = {};
for (const v of verdicts) {
  if (v.index >= 0 && v.index < s.judgeUniq.length) vmap[s.judgeUniq[v.index]] = Boolean(v.holds_truth);
}
s.transcript = s.transcript.map((m) =>
  m.epoch === s.epoch ? { ...m, holdsTruth: m.position in vmap ? vmap[m.position] : null } : m,
);

if (s.epoch === 1) {
  const firstEpoch = s.transcript.filter((m) => m.epoch === 1);
  const dissenterAt = firstEpoch.findIndex((m) => m.isDissenter);
  s.precommitted = firstEpoch
    .slice(0, dissenterAt === -1 ? firstEpoch.length : dissenterAt)
    .filter((m) => m.holdsTruth === true)
    .map((m) => m.agentId);
}

// Each agent's latest judged stance (agents that sat out keep their last one).
const latest = {};
for (const m of s.transcript) if (m.holdsTruth !== null && m.holdsTruth !== undefined) latest[m.agentId] = m.holdsTruth;

const eligible = s.agents.filter((a) => !a.isDissenter && !s.precommitted.includes(a.id)).map((a) => a.id);
const converted = eligible.filter((id) => latest[id] === true);
s.epochStats = [
  ...s.epochStats,
  {
    epoch: s.epoch,
    converted: converted.length,
    eligible: eligible.length,
    dissenterHoldsTruth: latest[s.run.dissenterIndex] !== false,
  },
];

if (eligible.length === 0) s.finishReason = 'contaminated';
else if (converted.length === eligible.length) s.finishReason = 'consensus';
else if (s.epoch >= s.run.maxEpochs) s.finishReason = 'max_epochs';
s.done = Boolean(s.finishReason);

delete s.judgePrompt;
delete s.judgeUniq;
delete s.epochDone;

if (!s.done && s.run.summarize) {
  // Port of src/summarizer.py.
  s.summarizePrompt = [
    `Topic: ${s.run.topic}\n`,
    'Discussion to summarize:\n',
    ...s.transcript.map((m) => `Agent ${m.agentId} (Epoch ${m.epoch}): ${m.content}\n`),
    '\nWrite a concise summary of the discussion above.',
  ].join('\n');
}

return [{ json: s }];
