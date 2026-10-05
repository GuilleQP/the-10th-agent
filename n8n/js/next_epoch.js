// Store the recap and move to the next epoch's first speaker.
const { summarizePrompt, done, ...s } = $('Score epoch').first().json;
const summary = String($input.first().json.text ?? '').trim();
return [{
  json: {
    ...s,
    summary,
    epochSummaries: [...s.epochSummaries, { afterEpoch: s.epoch, summary }],
    epoch: s.epoch + 1,
    turn: 0,
  },
}];
