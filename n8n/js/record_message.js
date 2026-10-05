// Append the agent's reply to the transcript and advance the turn. When the
// epoch's last speaker is done, prepare the judge prompt (port of src/judge.py).
const prev = $('Next speaker').first().json;
const content = String($input.first().json.output ?? '').trim();
const tag = content.match(/\[POSITION:\s*(.+?)\]/i);

const { speaker, prompt, systemPrompt, ...s } = prev;
s.transcript = [
  ...s.transcript,
  {
    epoch: s.epoch,
    agentId: speaker,
    isDissenter: speaker === s.run.dissenterIndex,
    content,
    position: tag ? tag[1].trim() : '',
  },
];
s.turn += 1;
s.epochDone = s.turn >= s.orders[s.epoch - 1].length;

if (s.epochDone) {
  // Positions are deduplicated, so one judge call covers the whole epoch.
  const uniq = [...new Set(
    s.transcript.filter((m) => m.epoch === s.epoch && m.position).map((m) => m.position),
  )].sort();
  s.judgeUniq = uniq;
  s.judgePrompt = [
    `Question under debate: ${s.run.topic}`,
    '',
    `The correct answer (ground truth): ${s.run.truth}`,
    '',
    'Positions to judge:',
    ...(uniq.length ? uniq.map((p, i) => `${i}. ${p}`) : ['(no positions were stated)']),
    '\nFor each numbered position, does it agree with the correct answer?',
  ].join('\n');
}

return [{ json: s }];
