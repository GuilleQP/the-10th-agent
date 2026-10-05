// Final metrics (mirrors ExperimentResult in src/results.py) + the HTML page
// the form shows when the run ends.
const s = $input.first().json;
const last = s.epochStats[s.epochStats.length - 1];
const rate = last.eligible ? last.converted / last.eligible : 0;
const epochs = s.epochStats.length;
const dissenterHeld = s.epochStats.every((e) => e.dissenterHoldsTruth);

const result = {
  topic: s.run.topic,
  model: s.run.model,
  agents: s.run.n,
  structure: s.run.structure,
  epochs,
  maxEpochs: s.run.maxEpochs,
  finishReason: s.finishReason,
  converted: last.converted,
  eligible: last.eligible,
  conversionRate: Math.round(rate * 1000) / 1000,
  dissenterHeld,
  precommitted: s.precommitted,
  contaminated: s.precommitted.length > 0,
  curve: s.epochStats.map((e) => (e.eligible ? e.converted / e.eligible : 0)),
  startedAt: s.run.startedAt,
  finishedAt: new Date().toISOString(),
};

const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (x) => `${Math.round(x * 100)}%`;

let headline, tone;
if (s.finishReason === 'contaminated') {
  headline = 'Invalid run: every believer already knew the answer'; tone = 'warn';
} else if (rate === 1) {
  headline = `The truth spread: all ${last.eligible} believers converted in ${epochs} epoch${epochs > 1 ? 's' : ''}`; tone = 'good';
} else if (rate === 0) {
  headline = `Spiral of silence: no believer moved after ${epochs} epoch${epochs > 1 ? 's' : ''}`; tone = 'bad';
} else {
  headline = `Partial: ${last.converted} of ${last.eligible} believers converted`; tone = 'mid';
}

const bars = s.epochStats.map((e) => {
  const r = e.eligible ? e.converted / e.eligible : 0;
  return `<div class="bar"><span class="lbl">Epoch ${e.epoch}</span><span class="track"><span class="fill" style="width:${Math.max(r * 100, 1)}%"></span></span><span class="val">${e.converted}/${e.eligible}</span></div>`;
}).join('');

const summaries = Object.fromEntries(s.epochSummaries.map((x) => [x.afterEpoch, x.summary]));
const body = s.transcript.map((m) => m.epoch).filter((v, i, a) => a.indexOf(v) === i).map((ep) => {
  const msgs = s.transcript.filter((m) => m.epoch === ep).map((m) => {
    const who = m.isDissenter ? `Agent ${m.agentId} · dissenter` : `Agent ${m.agentId}`;
    const pre = s.precommitted.includes(m.agentId) && ep === 1 ? '<span class="chip warn">knew it already</span>' : '';
    const verdict = m.holdsTruth === true ? '<span class="chip good">holds truth</span>'
      : m.holdsTruth === false ? '<span class="chip bad">holds belief</span>' : '<span class="chip">no position</span>';
    const text = esc(m.content.replace(/\s*\[POSITION:.*?\]\s*$/i, ''));
    return `<div class="msg${m.isDissenter ? ' dissent' : ''}"><div class="who">${who} ${verdict}${pre}</div><p>${text}</p><div class="pos">${esc(m.position || 'n/a')}</div></div>`;
  }).join('');
  const recap = summaries[ep] ? `<details><summary>Summary passed to epoch ${ep + 1}</summary><p>${esc(summaries[ep])}</p></details>` : '';
  return `<h3>Epoch ${ep}</h3>${msgs}${recap}`;
}).join('');

const reasons = { consensus: 'everyone converted', max_epochs: 'hit max epochs', contaminated: 'contaminated' };
const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>The 10th Agent: result</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1f;--mute:#6b6b70;--line:#e4e2dc;--good:#1f7a4d;--bad:#b3261e;--mid:#9a6700;--warn:#9a6700;--accent:#ea4b71}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:860px;margin:0 auto;padding:32px 16px 64px}
.kicker{color:var(--accent);font-weight:600;letter-spacing:.04em;text-transform:uppercase;font-size:12px}
h1{font-size:26px;line-height:1.25;margin:6px 0 4px}h1.good{color:var(--good)}h1.bad{color:var(--bad)}h1.mid,h1.warn{color:var(--mid)}
.q{color:var(--mute);margin:0 0 24px}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}@media (max-width:640px){.tiles{grid-template-columns:repeat(2,1fr)}}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.tile b{display:block;font-size:24px}.tile span{color:var(--mute);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:24px}
.bar{display:grid;grid-template-columns:70px 1fr 48px;gap:10px;align-items:center;margin:6px 0;font-size:13px}
.track{background:#eeece7;border-radius:6px;height:12px;overflow:hidden}.fill{display:block;height:100%;background:var(--good);border-radius:6px}
.lbl,.val{color:var(--mute)}.val{text-align:right;font-variant-numeric:tabular-nums}
h2{font-size:17px;margin:0 0 10px}h3{font-size:14px;color:var(--mute);margin:24px 0 8px;text-transform:uppercase;letter-spacing:.04em}
.msg{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:8px 0}
.msg.dissent{border-left:4px solid var(--accent)}
.who{font-weight:600;font-size:13px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.msg p{margin:6px 0}.pos{font-size:12px;color:var(--mute)}.pos:before{content:"Position: "}
.chip{font-size:11px;font-weight:600;padding:1px 8px;border-radius:999px;background:#eeece7;color:var(--mute)}
.chip.good{background:#e3f1e9;color:var(--good)}.chip.bad{background:#f8e3e1;color:var(--bad)}.chip.warn{background:#fbf0d9;color:var(--warn)}
details{margin:8px 0 0;color:var(--mute);font-size:13px}summary{cursor:pointer}
</style></head><body><main>
<div class="kicker">The 10th Agent · ${esc(result.model)}</div>
<h1 class="${tone}">${esc(headline)}</h1>
<p class="q">${esc(s.run.topic)}</p>
<div class="tiles">
<div class="tile"><b>${pct(rate)}</b><span>believers converted</span></div>
<div class="tile"><b>${epochs}/${s.run.maxEpochs}</b><span>epochs (${esc(reasons[s.finishReason] || s.finishReason)})</span></div>
<div class="tile"><b>${dissenterHeld ? 'Held' : 'Caved'}</b><span>the dissenter</span></div>
<div class="tile"><b>${s.precommitted.length}</b><span>contaminated agents${s.precommitted.length ? ' (excluded)' : ''}</span></div>
</div>
<div class="card"><h2>Conversion per epoch</h2>${bars}</div>
<h2>Transcript</h2>${body}
</main></body></html>`;

return [{ json: { result, html, transcript: s.transcript } }];
