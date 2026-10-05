// Port of src/chatroom.py::_build_prompt. Epoch 1 sees the full transcript;
// later epochs see the previous epoch's summary + this epoch's messages.
const s = $input.first().json;
const order = s.orders[s.epoch - 1];
const speaker = order[s.turn];

const useSummary = s.run.summarize && s.summary;
const summary = useSummary ? s.summary : null;
const messages = useSummary ? s.transcript.filter((m) => m.epoch === s.epoch) : s.transcript;

const lines = [`Topic under discussion: ${s.run.topic}\n`];
if (!summary && messages.length === 0) {
  lines.push('This is the start of the discussion. Share your opening position.');
} else {
  if (summary) {
    lines.push('Summary of the discussion in earlier epochs:\n');
    lines.push(`${summary}\n`);
  }
  if (messages.length) {
    lines.push(`${summary ? 'Messages so far in the current epoch:' : 'Here is the discussion so far:'}\n`);
    for (const m of messages) lines.push(`Agent ${m.agentId} (Epoch ${m.epoch}): ${m.content}\n`);
  }
  lines.push(`\nIt is now Epoch ${s.epoch}. Please contribute to the discussion.`);
}
lines.push('\nRemember: end your message with [POSITION: <your current stance>]');

return [{
  json: {
    ...s,
    speaker,
    systemPrompt: s.agents[speaker].systemPrompt,
    prompt: lines.join('\n'),
  },
}];
