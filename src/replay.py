"""Animated 'room' replay of a single run.

Reads one run's ``*_chat.json`` and emits a self-contained HTML page that
plays the discussion back turn by turn: agents seated in a ring, colored by
their current stance (truth / false belief / unclear), the active speaker's
message shown on the table, a play/scrub timeline, and a live "majority
converted" meter. Pure static HTML — open it or host it on GitHub Pages.
"""

from __future__ import annotations

import json
import re
from html import escape as _esc
from pathlib import Path

from src.scoring import classify_stance

EXPERIMENTS_ROOT = Path("experiments")
DEFAULT_OUTPUT = Path("docs/room.html")

_POS_RE = re.compile(r"\[POSITION:\s*(.+?)\]", re.IGNORECASE)


def build_turns(data: dict) -> list[dict]:
    """Turn the saved transcript into a compact playback script."""
    cfg = data.get("config", {})
    scoring = cfg.get("scoring", {})
    truth_kw = scoring.get("truth_keywords", [])
    false_kw = scoring.get("false_keywords", [])

    turns: list[dict] = []
    for m in data.get("transcript", []):
        content = m.get("content", "")
        match = _POS_RE.search(content)
        position = match.group(1).strip() if match else ""
        text = _POS_RE.sub("", content).strip()
        stance = classify_stance(position, truth_kw, false_kw)
        if m.get("is_dissenter") and stance != "false":
            stance = "truth"  # the dissenter is locked to the truth
        turns.append(
            {
                "e": m.get("epoch"),
                "a": m.get("agent_id"),
                "d": bool(m.get("is_dissenter")),
                "pos": position,
                "stance": stance,
                "text": text,
            }
        )
    return turns


def find_run(
    experiment: str | None = None,
    model: str | None = None,
    structure: str | None = None,
    root: Path = EXPERIMENTS_ROOT,
) -> tuple[Path | None, dict | None]:
    """Return the latest run (by filename/timestamp) matching the filters."""
    chosen: tuple[Path, dict] | None = None
    for path in sorted(root.rglob("*_chat.json")):
        if experiment and experiment.lower() not in str(path).lower():
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        cfg = data.get("config", {})
        if model and model.lower() not in cfg.get("model", {}).get("name", "").lower():
            continue
        if structure and structure.lower() not in cfg.get("communication", {}).get(
            "structure", ""
        ).lower():
            continue
        chosen = (path, data)  # sorted ascending → last match is newest
    return chosen if chosen else (None, None)


def render_room(data: dict) -> str:
    cfg = data.get("config", {})
    turns = build_turns(data)
    n = cfg.get("agents", {}).get("count", 10)
    diss = cfg.get("agents", {}).get("dissenter_index", 9)
    turns_json = json.dumps(turns).replace("</", "<\\/")

    html = _TEMPLATE
    html = html.replace("__TURNS__", turns_json)
    html = html.replace("__N__", str(n))
    html = html.replace("__DISS__", str(diss))
    html = html.replace("__TITLE__", _esc(data.get("experiment_name", "run")))
    html = html.replace("__TOPIC__", _esc(cfg.get("topic", "")))
    html = html.replace("__MODEL__", _esc(cfg.get("model", {}).get("name", "")))
    html = html.replace(
        "__STRUCTURE__", _esc(cfg.get("communication", {}).get("structure", "round-robin"))
    )
    return html


def main(
    run_file: Path | None = None,
    experiment: str | None = None,
    model: str | None = None,
    structure: str | None = None,
    output: Path = DEFAULT_OUTPUT,
) -> None:
    if run_file:
        src: Path | None = Path(run_file)
        data: dict | None = json.loads(src.read_text())
    else:
        src, data = find_run(experiment, model, structure)

    if not data:
        print("No matching run found. Pass a run file or check -e/-m/-s filters.")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_room(data))
    print(f"Wrote {output}\n  from {src}  ({len(data.get('transcript', []))} turns)")


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The 10th Agent — Replay</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;}
  #stage{position:relative;width:500px;height:500px;max-width:100%;margin:0 auto;}
  .seat{position:absolute;transform:translate(-50%,-50%);text-align:center;width:64px;}
  .seat .dot{width:46px;height:46px;border-radius:9999px;border:3px solid #fff;margin:0 auto;
    box-shadow:0 1px 4px rgba(27,31,36,.25);transition:background .45s ease,transform .2s ease;}
  .seat.dissenter .dot{box-shadow:0 0 0 3px #d4a72c,0 1px 4px rgba(27,31,36,.25);}
  .seat.speaking .dot{transform:scale(1.3);}
  .seat .cap{font-size:11px;color:#57606a;margin-top:5px;white-space:nowrap;}
  .seat.speaking .cap{color:#1f2328;font-weight:600;}
  #center{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:248px;
    max-height:236px;overflow-y:auto;background:#fff;border:1px solid #d0d7de;border-radius:12px;
    box-shadow:0 4px 14px rgba(27,31,36,.12);padding:12px 14px;}
</style></head>
<body class="bg-[#fafafa] text-[#1f2328]">
<header class="bg-[#f6f8fa] border-b border-[#d0d7de]">
  <div class="max-w-3xl mx-auto px-6 py-5">
    <h1 class="text-xl font-semibold">Replay &mdash; __TITLE__</h1>
    <p class="text-sm text-[#656d76] mt-1">__TOPIC__</p>
    <p class="text-xs text-[#8a8780] mt-1">model: __MODEL__ &middot; structure: __STRUCTURE__</p>
  </div>
</header>
<main class="max-w-3xl mx-auto px-6 py-6">
  <div class="flex flex-wrap gap-3 mb-5 text-xs text-[#57606a]">
    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#2da44e"></span> truth</span>
    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#cf222e"></span> false belief</span>
    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#d0d7de"></span> unclear</span>
    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full" style="background:#eaeef2"></span> not spoken yet</span>
    <span class="inline-flex items-center gap-1"><span class="inline-block w-3 h-3 rounded-full ring-2 ring-[#d4a72c]"></span> dissenter &#9733;</span>
  </div>

  <div id="stage">
    <div id="center">
      <div class="flex items-center justify-between mb-1">
        <span id="speaker" class="text-sm font-semibold"></span>
        <span id="epoch" class="text-xs text-[#8a8780]"></span>
      </div>
      <div id="pos" class="inline-block text-xs rounded-full bg-[#eaeef2] text-[#57606a] px-2 py-0.5 mb-2"></div>
      <p id="msg" class="text-sm leading-snug"></p>
    </div>
  </div>

  <div class="max-w-md mx-auto mt-6">
    <div class="h-2 rounded-full bg-[#eaeef2] overflow-hidden">
      <div id="bar" class="h-full bg-[#2da44e] transition-all duration-500" style="width:0%"></div>
    </div>
    <div id="barlbl" class="text-xs text-[#656d76] text-center mt-1"></div>
  </div>

  <div class="flex items-center justify-center gap-3 mt-5">
    <button id="prev" class="px-3 py-1.5 rounded-md border border-[#d0d7de] text-sm hover:bg-[#f3f4f6]">&lsaquo; Prev</button>
    <button id="play" class="px-4 py-1.5 rounded-md bg-[#1f2328] text-white text-sm">&#9654; Play</button>
    <button id="next" class="px-3 py-1.5 rounded-md border border-[#d0d7de] text-sm hover:bg-[#f3f4f6]">Next &rsaquo;</button>
    <span id="counter" class="text-xs text-[#656d76] tabular-nums w-16 text-right"></span>
  </div>
  <input id="slider" type="range" min="0" value="0" class="w-full max-w-md mx-auto block mt-3">
</main>
<script>
const TURNS = __TURNS__;
const N = __N__, DISS = __DISS__;
const COLORS = {truth:'#2da44e','false':'#cf222e',unknown:'#d0d7de',none:'#eaeef2'};
const stage = document.getElementById('stage');
const seats = [];
const CX = 250, CY = 250, R = 200;
for (let i = 0; i < N; i++) {
  const ang = (-90 + i * 360 / N) * Math.PI / 180;
  const s = document.createElement('div');
  s.className = 'seat' + (i === DISS ? ' dissenter' : '');
  s.style.left = (CX + R * Math.cos(ang)) + 'px';
  s.style.top = (CY + R * Math.sin(ang)) + 'px';
  s.innerHTML = '<div class="dot"></div><div class="cap">A' + i + (i === DISS ? ' \\u2605' : '') + '</div>';
  stage.appendChild(s);
  seats.push(s);
}
let idx = 0, timer = null;
const slider = document.getElementById('slider');
slider.max = Math.max(0, TURNS.length - 1);
const playBtn = document.getElementById('play');
function stanceAt(a, upto) {
  for (let j = upto; j >= 0; j--) { if (TURNS[j].a === a) return TURNS[j].stance; }
  return 'none';
}
function render() {
  const t = TURNS[idx];
  if (!t) return;
  for (let i = 0; i < N; i++) {
    const st = stanceAt(i, idx);
    seats[i].querySelector('.dot').style.background = COLORS[st] || COLORS.none;
    seats[i].classList.toggle('speaking', i === t.a);
  }
  document.getElementById('speaker').textContent = 'Agent ' + t.a + (t.d ? ' (dissenter)' : '');
  document.getElementById('epoch').textContent = 'Epoch ' + t.e;
  document.getElementById('pos').textContent = t.pos || '\\u2014';
  document.getElementById('msg').textContent = t.text;
  document.getElementById('counter').textContent = (idx + 1) + ' / ' + TURNS.length;
  let conv = 0, maj = 0;
  for (let i = 0; i < N; i++) { if (i !== DISS) { maj++; if (stanceAt(i, idx) === 'truth') conv++; } }
  document.getElementById('bar').style.width = (maj ? conv / maj * 100 : 0) + '%';
  document.getElementById('barlbl').textContent = conv + ' / ' + maj + ' majority agents converted to truth';
  slider.value = idx;
}
function go(i) { idx = Math.max(0, Math.min(TURNS.length - 1, i)); render(); }
function stop() { if (timer) { clearInterval(timer); timer = null; playBtn.innerHTML = '&#9654; Play'; } }
document.getElementById('prev').onclick = () => { stop(); go(idx - 1); };
document.getElementById('next').onclick = () => { stop(); go(idx + 1); };
slider.oninput = () => { stop(); go(+slider.value); };
playBtn.onclick = () => {
  if (timer) { stop(); return; }
  if (idx >= TURNS.length - 1) idx = 0;
  playBtn.innerHTML = '&#10073;&#10073; Pause';
  timer = setInterval(() => { if (idx >= TURNS.length - 1) { stop(); return; } idx++; render(); }, 1400);
};
render();
</script>
</body></html>
"""
