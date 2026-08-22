#!/usr/bin/env python
"""Render a .replay26 from a match of bots/gcsprobe into a self-contained HTML
page showing the game board side by side with the Global Communication Store,
round by round, as seen through any of our units' registries.

    .venv/bin/python tools/gcs_viz.py replay.replay26 out.html
    .venv/bin/python tools/gcs_viz.py replay.replay26 --report     # tallies only

Data sources (all inside the replay):
  - field 1: the map (.map26 schema) and the two Cores
  - field 3 (per round): spawn events (unwrapped field 1), moves (field 2),
    HP deltas (field 5) and the print log (field 9 = {1: unit id, 2: text}),
    where the probe's `GCSTRACE {...}` lines live.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bots.utils.GCS.Base.protocol import TILE_STATES  # noqa: E402

TYPE_MARKERS = {10: "builder_bot", 11: "conveyor", 15: "harvester", 21: "gunner",
                24: "launcher"}


# --------------------------------------------------------------------------- protobuf
def _varint(b, i):
    v = s = 0
    while True:
        c = b[i]
        i += 1
        v |= (c & 0x7F) << s
        s += 7
        if not c & 0x80:
            return v, i


def _fields(b):
    i, out = 0, []
    while i < len(b):
        key, i = _varint(b, i)
        f, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 2:
            n, i = _varint(b, i)
            v = b[i:i + n]
            i += n
        elif wt == 1:
            v = b[i:i + 8]
            i += 8
        elif wt == 5:
            v = b[i:i + 4]
            i += 4
        else:
            raise ValueError(f"wire type {wt}")
        out.append((f, wt, v))
    return out


def _unwrap(v):
    while True:
        fs = _fields(v)
        if len(fs) == 1 and fs[0][0] == 1 and fs[0][1] == 2:
            v = fs[0][2]
            continue
        return fs


def _pos(b):
    d = {f: v for f, _, v in _fields(b)}
    return d.get(1, 0), d.get(2, 0)


def _signed(v):          # protobuf int32 stored as two's-complement varint
    return v - (1 << 64) if v >= (1 << 63) else v


# --------------------------------------------------------------------------- parse
def parse_replay(path: str) -> dict:
    top = _fields(open(path, "rb").read())
    map_msg = next(v for f, _, v in top if f == 1)
    width = height = 0
    rows, cores = [], []
    for f, wt, v in _fields(map_msg):
        if f == 1:
            width = v
        elif f == 2:
            height = v
        elif f == 3:
            rows.append(list(next(vv for ff, _, vv in _fields(v) if ff == 1)))
        elif f == 4:
            d = {ff: vv for ff, _, vv in _fields(v)}
            cores.append({"owner": d.get(1, 1), "pos": _pos(d[3])})

    entities: dict[int, dict] = {}
    rounds = []
    for ri, rb in enumerate(v for f, _, v in top if f == 3):
        traces = {}
        for f, wt, ev in _fields(rb):
            u = _unwrap(ev)
            nums = {ff for ff, _, _ in u}
            if 1 in nums and 3 in nums and 4 in nums:                 # spawn
                d = {ff: vv for ff, _, vv in u}
                marker = next((ff for ff in nums if ff >= 10), None)
                entities[d[1]] = {"team": "B" if d.get(2) == 1 else "A",
                                  "type": TYPE_MARKERS.get(marker, f"type{marker}"),
                                  "pos": _pos(d[3]), "hp": d[4], "maxhp": d[5]}
            elif u and u[0][0] == 2:                                   # move
                d = {ff: vv for ff, _, vv in _fields(u[0][2])}
                if d.get(1) in entities:
                    entities[d[1]]["pos"] = _pos(d[2])
            elif u and u[0][0] == 5:                                   # hp delta
                d = {ff: vv for ff, _, vv in _fields(u[0][2])}
                if d.get(1) in entities:
                    entities[d[1]]["hp"] += _signed(d.get(2, 0))
            elif u and u[0][0] == 9:                                   # print
                d = {ff: vv for ff, _, vv in _fields(u[0][2])}
                text = d.get(2, b"")
                if isinstance(text, bytes) and text.startswith(b"GCSTRACE "):
                    traces[d[1]] = json.loads(text[9:])
        for uid in [u for u, e in entities.items() if e["hp"] <= 0]:
            del entities[uid]
        rounds.append({
            "ents": [{"id": uid, **e, "pos": list(e["pos"])} for uid, e in entities.items()],
            "traces": traces,
        })
    return {"w": width, "h": height, "tiles": rows,
            "cores": [{"owner": c["owner"], "pos": list(c["pos"])} for c in cores],
            "rounds": rounds, "states": list(TILE_STATES)}


# --------------------------------------------------------------------------- html
TEMPLATE = r"""<title>Store Scope</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{
  --bg:#F2F4F3;--panel:#FFFFFF;--line:#D6DBD9;--text:#1B2229;--muted:#66737E;
  --accent:#B9821D;--accent-soft:#F3E4C4;--truth:#1F8FA3;--ok:#2E8B45;--bad:#C2335F;
  --ore:#B8893A;--wall:#9AA3AB;--floor:#E6E9E7;--enemy:#8B93A0;--learned:#BFD9E0;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#10151A;--panel:#182028;--line:#27313B;--text:#D9E1E8;--muted:#7D8B99;
  --accent:#E3A93B;--accent-soft:#3A2E16;--truth:#52C4D8;--ok:#6FC27A;--bad:#E0678F;
  --ore:#B8893A;--wall:#3B444E;--floor:#1E262E;--enemy:#5C6673;--learned:#24404A;
}}
:root[data-theme="dark"]{
  --bg:#10151A;--panel:#182028;--line:#27313B;--text:#D9E1E8;--muted:#7D8B99;
  --accent:#E3A93B;--accent-soft:#3A2E16;--truth:#52C4D8;--ok:#6FC27A;--bad:#E0678F;
  --ore:#B8893A;--wall:#3B444E;--floor:#1E262E;--enemy:#5C6673;--learned:#24404A;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 "IBM Plex Sans",system-ui,sans-serif}
.mono{font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
header{display:flex;flex-wrap:wrap;align-items:center;gap:14px 22px;padding:12px 18px;border-bottom:1px solid var(--line);background:var(--panel)}
header h1{font-size:16px;font-weight:600;margin:0;letter-spacing:.01em}
header .sub{color:var(--muted);font-size:12px}
.transport{display:flex;align-items:center;gap:10px}
button{font:inherit;color:var(--text);background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:4px 10px;cursor:pointer}
button:hover{border-color:var(--accent)}
button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
input[type=range]{width:min(420px,40vw);accent-color:var(--accent)}
select{font:inherit;color:var(--text);background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:4px 8px}
.round{font-size:18px;font-weight:500;min-width:5.5ch}
main{display:grid;grid-template-columns:minmax(320px,1fr) minmax(420px,1.1fr);gap:18px;padding:18px;align-items:start}
@media (max-width:900px){main{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;overflow:hidden}
.panel h2{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0;padding:10px 14px;border-bottom:1px solid var(--line)}
canvas{display:block;width:100%;height:auto;background:var(--floor)}
.status{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px 18px;padding:12px 14px;border-top:1px solid var(--line)}
.status b{display:block;font-size:11px;font-weight:500;color:var(--muted);letter-spacing:.06em;text-transform:uppercase}
.status span{font-size:15px}
.pill{display:inline-block;padding:1px 7px;border-radius:3px;font-size:11px;font-weight:500;letter-spacing:.02em;background:var(--accent-soft);color:var(--accent)}
.pill.ok{background:transparent;color:var(--ok);border:1px solid var(--ok)}
.pill.bad{background:transparent;color:var(--bad);border:1px solid var(--bad)}
.pill.dim{background:transparent;color:var(--muted);border:1px solid var(--line)}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:11px;font-weight:500;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top;font-size:13px}
tr.me td{background:var(--accent-soft)}
tr.wrote td:first-child{box-shadow:inset 3px 0 0 var(--accent)}
td.raw{font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--muted)}
td.raw.changed{color:var(--text)}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--line);margin-right:6px;vertical-align:middle}
.dot.on{background:var(--accent)}
.decoded{color:var(--muted);font-size:12px}
.decoded b{color:var(--text);font-weight:500}
.legend{display:flex;flex-wrap:wrap;gap:8px 18px;padding:10px 14px;font-size:12px;color:var(--muted);border-top:1px solid var(--line)}
.legend i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.legend i.ring{border-radius:50%;background:transparent;border:2px solid currentColor}
.wrap{overflow-x:auto}
@media (prefers-reduced-motion: reduce){*{transition:none!important}}
</style>

<header>
  <div><h1>Store Scope</h1><div class="sub" id="subtitle"></div></div>
  <div class="transport">
    <button id="play" aria-label="Play or pause">Play</button>
    <button id="back" aria-label="Back one round">−1</button>
    <input type="range" id="scrub" min="0" value="0" aria-label="Round">
    <button id="fwd" aria-label="Forward one round">+1</button>
    <span class="round mono" id="roundLabel">r 0</span>
    <select id="speed" aria-label="Playback speed"><option value="500">2 rounds/s</option><option value="200" selected>5 rounds/s</option><option value="66">15 rounds/s</option></select>
  </div>
  <label>Seen through <select id="viewer" aria-label="Viewer unit"></select></label>
</header>

<main>
  <section class="panel">
    <h2>Board — engine truth, with the viewer's picture overlaid</h2>
    <canvas id="board" width="900" height="900"></canvas>
    <div class="legend">
      <span><i style="background:var(--ore)"></i>ore</span>
      <span><i style="background:var(--wall)"></i>wall</span>
      <span><i style="background:var(--truth)"></i>our unit (true position, slot number)</span>
      <span><i class="ring" style="color:var(--ok)"></i>viewer's reckoning — matches the unit's position at the end of last round (what this round's store describes)</span>
      <span><i class="ring" style="color:var(--bad)"></i>viewer's reckoning — off (line to where the unit really was)</span>
      <span><i style="background:var(--learned)"></i>tile the viewer learned via the store</span>
      <span><i style="background:var(--bad)"></i>learned fact that contradicts the map</span>
      <span><i style="background:var(--enemy)"></i>enemy</span>
    </div>
    <div class="status" id="status"></div>
  </section>
  <section class="panel">
    <h2>Global Communication Store — 16 slots, as the viewer decodes them</h2>
    <div class="wrap"><table id="slots"><thead><tr><th>slot</th><th>owner</th><th>raw u32</th><th>format</th><th>decoded</th></tr></thead><tbody></tbody></table></div>
  </section>
</main>

<script>
const DATA = __DATA__;
const STATES = DATA.states;
const R = DATA.rounds, W = DATA.w, H = DATA.h;
const FOV_R2 = {core:36, builder_bot:20, gunner:13, sentinel:32, launcher:26};
const CTRL = ["ASSIGN","SYMMETRY","DIRECTIVE"];
const MOVES = ["", "N", "E", "S", "W"];

// unit id -> slot, learned across the whole replay (from each unit's own trace)
const slotOf = {}; const kindOf = {};
R.forEach(rd => { for (const [id, t] of Object.entries(rd.traces)) { if (t.slot !== null) slotOf[id] = t.slot; kindOf[id] = t.kind; } });
const viewers = Object.keys(kindOf).map(Number).sort((a,b)=>a-b);
const tileIs = (x,y) => DATA.tiles[y] && DATA.tiles[y][x];

// accumulated per-viewer knowledge learned via the store, up to round r
const learnedCache = {};
function learnedUpTo(viewer, r) {
  const key = viewer;
  if (!learnedCache[key]) learnedCache[key] = {upto: -1, map: new Map()};
  const c = learnedCache[key];
  if (r < c.upto) { c.upto = -1; c.map = new Map(); }
  for (let i = c.upto + 1; i <= r; i++) {
    const t = R[i].traces[viewer];
    if (t) for (const [x,y,s] of t.learned) c.map.set(x+","+y, {s, r:i});
  }
  c.upto = r;
  return c.map;
}

const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const cv = document.getElementById('board'), ctx = cv.getContext('2d');
let round = 0, viewer = viewers[0], timer = null;

function draw() {
  const size = Math.min(cv.width / W, cv.height / H);
  const ox = (cv.width - size*W)/2, oy = (cv.height - size*H)/2;
  const C = {floor:cssVar('--floor'), ore:cssVar('--ore'), wall:cssVar('--wall'), truth:cssVar('--truth'),
             ok:cssVar('--ok'), bad:cssVar('--bad'), learned:cssVar('--learned'), enemy:cssVar('--enemy'),
             text:cssVar('--text'), accent:cssVar('--accent'), line:cssVar('--line'), panel:cssVar('--panel')};
  ctx.fillStyle = C.floor; ctx.fillRect(0,0,cv.width,cv.height);
  const rd = R[round], t = rd.traces[viewer];
  const learned = learnedUpTo(viewer, round);
  let learnedOk = 0, learnedBad = 0;
  for (let y=0;y<H;y++) for (let x=0;x<W;x++) {
    const v = DATA.tiles[y][x];
    ctx.fillStyle = v===1 ? C.wall : v===2 ? C.ore : C.floor;
    ctx.fillRect(ox+x*size, oy+y*size, size, size);
    const l = learned.get(x+","+y);
    if (l) {
      const name = STATES[l.s] || "";
      const agrees = (name==="WALL" && v===1) || (name==="ORE_FREE" && v===2) || (name==="EMPTY" && v===0) || (!["WALL","ORE_FREE","EMPTY"].includes(name));
      if (agrees) learnedOk++; else learnedBad++;
      ctx.fillStyle = agrees ? C.learned : C.bad;
      ctx.globalAlpha = l.r === round ? 1 : 0.75;
      ctx.fillRect(ox+x*size+2, oy+y*size+2, size-4, size-4);
      ctx.globalAlpha = 1;
      if (l.r === round) { ctx.strokeStyle = C.accent; ctx.lineWidth = 2; ctx.strokeRect(ox+x*size+1, oy+y*size+1, size-2, size-2); }
    }
  }
  // grid
  ctx.strokeStyle = C.line; ctx.lineWidth = 0.5; ctx.globalAlpha = .6;
  for (let x=0;x<=W;x++){ctx.beginPath();ctx.moveTo(ox+x*size,oy);ctx.lineTo(ox+x*size,oy+H*size);ctx.stroke();}
  for (let y=0;y<=H;y++){ctx.beginPath();ctx.moveTo(ox,oy+y*size);ctx.lineTo(ox+W*size,oy+y*size);ctx.stroke();}
  ctx.globalAlpha = 1;
  // cores (2x2, anchor = top-left)
  for (const c of DATA.cores) {
    ctx.fillStyle = c.owner===1 ? C.truth : C.enemy;
    ctx.fillRect(ox+c.pos[0]*size+1, oy+c.pos[1]*size+1, 2*size-2, 2*size-2);
  }
  // viewer FOV disc
  const me = rd.ents.find(e => e.id === viewer);
  const vpos = me ? me.pos : (t ? t.pos : null);
  if (vpos) {
    const r2 = FOV_R2[kindOf[viewer]] || 20; const rr = Math.floor(Math.sqrt(r2));
    ctx.fillStyle = C.accent; ctx.globalAlpha = .10;
    for (let dy=-rr;dy<=rr;dy++) for (let dx=-rr;dx<=rr;dx++) if (dx*dx+dy*dy<=r2)
      ctx.fillRect(ox+(vpos[0]+dx)*size, oy+(vpos[1]+dy)*size, size, size);
    ctx.globalAlpha = 1;
  }
  // entities
  const truePos = {};
  for (const e of rd.ents) {
    const cx = ox+(e.pos[0]+.5)*size, cy = oy+(e.pos[1]+.5)*size;
    truePos[e.id] = e.pos;
    if (e.type !== "builder_bot" && !["gunner","launcher","sentinel"].includes(e.type)) {
      ctx.fillStyle = e.team==="A" ? C.truth : C.enemy; ctx.globalAlpha = .45;
      ctx.fillRect(cx-size*.3, cy-size*.3, size*.6, size*.6); ctx.globalAlpha = 1; continue;
    }
    ctx.beginPath(); ctx.arc(cx, cy, size*.36, 0, Math.PI*2);
    ctx.fillStyle = e.team==="A" ? C.truth : C.enemy; ctx.fill();
    if (e.team==="A" && slotOf[e.id] !== undefined) {
      ctx.fillStyle = C.panel; ctx.font = `500 ${Math.max(9,size*.5)}px "IBM Plex Mono",monospace`;
      ctx.textAlign="center"; ctx.textBaseline="middle"; ctx.fillText(slotOf[e.id], cx, cy+0.5);
    }
  }
  if (me) { const cx = ox+(me.pos[0]+.5)*size, cy = oy+(me.pos[1]+.5)*size;
    ctx.strokeStyle = C.accent; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(cx,cy,size*.5,0,Math.PI*2); ctx.stroke(); }
  // viewer's reckoning of each owned slot.  What the store says in round r
  // was written in round r-1, so the reckoning describes positions as of the
  // end of the previous round — compare against those, not this round's.
  const prevPos = {};
  if (round > 0) for (const e of R[round-1].ents) prevPos[e.id] = e.pos;
  let reckOk = 0, reckBad = 0, reckUnknown = 0;
  if (t) for (const [slot, [kind, pos]] of Object.entries(t.owners)) {
    if (!pos || kind==="core") continue;
    const id = Object.keys(slotOf).find(i => slotOf[i] == slot && kindOf[i] === kind);
    const truth = id !== undefined ? (prevPos[id] || null) : null;
    const match = truth && truth[0]===pos[0] && truth[1]===pos[1];
    if (!truth) reckUnknown++; else if (match) reckOk++; else reckBad++;
    const cx = ox+(pos[0]+.5)*size, cy = oy+(pos[1]+.5)*size;
    ctx.strokeStyle = !truth ? C.text : match ? C.ok : C.bad; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.arc(cx, cy, size*.46, 0, Math.PI*2); ctx.stroke();
    if (truth && !match) { ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(ox+(truth[0]+.5)*size, oy+(truth[1]+.5)*size); ctx.stroke(); }
  }
  renderStatus(t, {learnedOk, learnedBad, reckOk, reckBad, reckUnknown, learnedTotal: learned.size});
  renderSlots(t);
}

function pill(text, cls) { return `<span class="pill ${cls||''}">${text}</span>`; }

function renderStatus(t, s) {
  const el = document.getElementById('status');
  if (!t) { el.innerHTML = `<div><b>viewer</b><span>no trace this round (unit not alive yet / already dead)</span></div>`; return; }
  let win = 'normal';
  if (t.resync === t.r) win = 'resync round — everyone writes its absolute position';
  else if (t.onboard_until !== null && t.resync !== null && t.r > t.resync && t.r <= t.onboard_until) win = `onboarding ${t.r - t.resync} / ${t.onboard_until - t.resync} — Core streams through turret slots`;
  el.innerHTML = `
    <div><b>viewer</b><span>${t.kind} #${viewer} · slot ${t.slot ?? '—'} · at (${t.pos})</span></div>
    <div><b>round window</b><span>${win}</span></div>
    <div><b>core HP (latched)</b><span class="mono">${t.core_hp}</span></div>
    <div><b>wrote this round</b><span class="mono">${t.wrote === null ? '— (silent)' : t.wrote}</span></div>
    <div><b>tiles in viewer's map</b><span class="mono">${t.known}</span></div>
    <div><b>learned via store so far</b><span>${s.learnedTotal} &nbsp;${pill(s.learnedOk+' agree with map','ok')} ${s.learnedBad ? pill(s.learnedBad+' contradict','bad') : ''}</span></div>
    <div><b>reckoned positions</b><span>${pill(s.reckOk+' exact','ok')} ${s.reckBad ? pill(s.reckBad+' off','bad') : ''} ${s.reckUnknown ? pill(s.reckUnknown+' unit not on board','dim') : ''}</span></div>`;
}

function renderSlots(t) {
  const tb = document.querySelector('#slots tbody');
  if (!t) { tb.innerHTML = ''; return; }
  let html = '';
  for (let s=0; s<16; s++) {
    const d = t.slots[s] || {raw:0, changed:false, format:'-', facts:[], events:[]};
    const owner = t.owners[s];
    const ownerTxt = owner ? `${owner[0]}${owner[1] ? ' @('+owner[1]+')' : ''}` : '<span class="decoded">free</span>';
    const parts = [];
    if (d.events && d.events.length) for (const [k,a] of d.events) parts.push(`<b>${CTRL[k]||'ctrl'+k}</b>(${a.join(', ')})`);
    if (d.position) parts.push(`<b>pos</b> (${d.position})`);
    if (d.move) parts.push(`move <b>${MOVES[d.move]}</b>`);
    if (d.turn) parts.push(`turn <b>${d.turn===1?'CW':'CCW'}</b>`);
    if (d.aux) parts.push(`grants slot <b>${d.aux}</b>`);
    if (d.facts && d.facts.length) parts.push(d.facts.slice(0,4).map(([x,y,st]) => `(${x},${y})=<b>${STATES[st]||st}</b>`).join(' ') + (d.facts.length>4 ? ` +${d.facts.length-4}` : ''));
    const fmtCls = d.format.startsWith('undecodable') ? 'bad' : ['idle','stale','-','empty','unknown owner'].includes(d.format) ? 'dim' : '';
    const cls = [(t.slot===s?'me':''), (t.wrote!==null && t.slot===s ? 'wrote':'')].join(' ');
    html += `<tr class="${cls}"><td class="mono">${s}</td><td>${ownerTxt}</td><td class="raw ${d.changed?'changed':''}"><span class="dot ${d.changed?'on':''}"></span>${d.raw}</td><td>${pill(d.format, fmtCls)}</td><td class="decoded">${parts.join(' · ') || '—'}</td></tr>`;
  }
  tb.innerHTML = html;
}

// transport
const scrub = document.getElementById('scrub'); scrub.max = R.length-1;
const vsel = document.getElementById('viewer');
for (const v of viewers) { const o = document.createElement('option'); o.value = v; o.textContent = `${kindOf[v]} #${v}${slotOf[v]!==undefined ? ' (slot '+slotOf[v]+')' : ''}`; vsel.appendChild(o); }
function setRound(r) { round = Math.max(0, Math.min(R.length-1, r)); scrub.value = round; document.getElementById('roundLabel').textContent = 'r ' + round; draw(); }
scrub.addEventListener('input', () => setRound(+scrub.value));
document.getElementById('back').onclick = () => setRound(round-1);
document.getElementById('fwd').onclick = () => setRound(round+1);
vsel.onchange = () => { viewer = +vsel.value; draw(); };
const playBtn = document.getElementById('play');
function stop(){ clearInterval(timer); timer=null; playBtn.textContent='Play'; }
playBtn.onclick = () => { if (timer) return stop(); playBtn.textContent='Pause'; timer = setInterval(() => { if (round >= R.length-1) return stop(); setRound(round+1); }, +document.getElementById('speed').value); };
document.getElementById('speed').onchange = () => { if (timer) { stop(); playBtn.click(); } };
document.addEventListener('keydown', e => { if (e.key==='ArrowRight') setRound(round+1); else if (e.key==='ArrowLeft') setRound(round-1); else if (e.key===' ') { e.preventDefault(); playBtn.click(); } });
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', draw);
new MutationObserver(draw).observe(document.documentElement, {attributes:true, attributeFilter:['data-theme']});
document.getElementById('subtitle').textContent = `${W}×${H} map · ${R.length} rounds · ${viewers.length} of our units traced · ← → step, space plays`;
const hash = Object.fromEntries(location.hash.slice(1).split('&').filter(Boolean).map(kv => kv.split('=')));
if (hash.v && viewers.includes(+hash.v)) { viewer = +hash.v; vsel.value = viewer; }
setRound(+(hash.r || 0));
</script>
"""


def report(data: dict) -> str:
    """Whole-replay tallies: reckoning accuracy and learned-fact agreement,
    for every traced unit.  The store in round r describes round r-1, so
    reckoned positions are checked against the previous round's entities."""
    rounds, states = data["rounds"], data["states"]
    slot_of, kind_of = {}, {}
    for rd in rounds:
        for uid, t in rd["traces"].items():
            if t["slot"] is not None:
                slot_of[int(uid)] = t["slot"]
            kind_of[int(uid)] = t["kind"]
    lines = []
    for viewer in sorted(kind_of):
        ok = bad = unknown = 0
        learned = {}
        for r, rd in enumerate(rounds):
            t = rd["traces"].get(viewer) or rd["traces"].get(str(viewer))
            if not t:
                continue
            prev = {e["id"]: e["pos"] for e in rounds[r - 1]["ents"]} if r else {}
            for slot, (kind, pos, _) in t["owners"].items():
                if not pos or kind == "core":
                    continue
                uid = next((u for u, s in slot_of.items() if s == int(slot) and kind_of[u] == kind), None)
                truth = prev.get(uid)
                if truth is None:
                    unknown += 1
                elif truth == pos:
                    ok += 1
                else:
                    bad += 1
            for x, y, st in t["learned"]:
                learned[(x, y)] = st
        agree = contradict = 0
        for (x, y), st in learned.items():
            name = states[st] if st < len(states) else ""
            v = data["tiles"][y][x]
            if name in ("WALL", "ORE_FREE", "EMPTY"):
                if (name, v) in (("WALL", 1), ("ORE_FREE", 2), ("EMPTY", 0)):
                    agree += 1
                else:
                    contradict += 1
        lines.append(f"{kind_of[viewer]:>11} #{viewer:<3} slot {slot_of.get(viewer, '-')!s:<2} "
                     f"reckoning: {ok} exact / {bad} off / {unknown} unverifiable   "
                     f"learned via store: {len(learned)} tiles, {agree} agree, {contradict} contradict")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    data = parse_replay(sys.argv[1])
    if sys.argv[2] == "--report":
        print(report(data))
        return
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    Path(sys.argv[2]).write_text(html)
    n_tr = sum(len(r["traces"]) for r in data["rounds"])
    print(f"{sys.argv[2]}: {data['w']}x{data['h']} map, {len(data['rounds'])} rounds, "
          f"{n_tr} trace lines, {len(html)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
