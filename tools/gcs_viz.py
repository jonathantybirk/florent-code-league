#!/usr/bin/env python
"""Render a .replay26 from a match of a GCS-tracing bot (bots/test/*) into a self-contained HTML
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

import base64
import gzip
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
        for t in traces.values():                       # compact: drop what the viewer defaults
            t.pop("store", None)
            t["slots"] = {k: v for k, v in t.get("slots", {}).items()
                          if v.get("facts") or v.get("events") or v.get("format") not in ("stale", "empty", "-")}
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
  --ore:#B8893A;--wall:#9AA3AB;--floor:#E6E9E7;--unknown:#D3D8D6;--enemy:#8B93A0;--learned:#BFD9E0;
  --ours:#1F8FA3;--theirs:#8B93A0;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#10151A;--panel:#182028;--line:#27313B;--text:#D9E1E8;--muted:#7D8B99;
  --accent:#E3A93B;--accent-soft:#3A2E16;--truth:#52C4D8;--ok:#6FC27A;--bad:#E0678F;
  --ore:#B8893A;--wall:#3B444E;--floor:#1E262E;--unknown:#0E1216;--enemy:#5C6673;--learned:#24404A;
  --ours:#52C4D8;--theirs:#8A94A0;
}}
:root[data-theme="dark"]{
  --bg:#10151A;--panel:#182028;--line:#27313B;--text:#D9E1E8;--muted:#7D8B99;
  --accent:#E3A93B;--accent-soft:#3A2E16;--truth:#52C4D8;--ok:#6FC27A;--bad:#E0678F;
  --ore:#B8893A;--wall:#3B444E;--floor:#1E262E;--unknown:#0E1216;--enemy:#5C6673;--learned:#24404A;
  --ours:#52C4D8;--theirs:#8A94A0;
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
input[type=range]{width:min(360px,34vw);accent-color:var(--accent)}
select{font:inherit;color:var(--text);background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:4px 8px}
.round{font-size:18px;font-weight:500;min-width:5.5ch}
main{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding:18px;align-items:start}
.store{grid-column:1 / -1}
@media (max-width:980px){main{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;overflow:hidden}
.panel h2{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0;padding:10px 14px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:10px}
.panel h2 span{font-weight:400;letter-spacing:0;text-transform:none;color:var(--text)}
canvas{display:block;width:100%;height:auto;background:var(--floor);cursor:crosshair}
.status{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px 18px;padding:12px 14px;border-top:1px solid var(--line)}
.status b{display:block;font-size:11px;font-weight:500;color:var(--muted);letter-spacing:.06em;text-transform:uppercase}
.status span{font-size:15px}
.inspect{min-height:2.6em;padding:8px 14px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
.inspect b{color:var(--text);font-weight:500}
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
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;padding:10px 14px;font-size:12px;color:var(--muted);border-top:1px solid var(--line)}
.legend i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.legend i.ring{border-radius:50%;background:transparent;border:2px solid currentColor}
.legend i.dash{background:transparent;border:2px dashed currentColor}
.legend i.dot{width:11px;height:11px;margin-right:6px;border-radius:50%}
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
  <label>Unit <select id="viewer" aria-label="Viewer unit"></select> <span class="sub">— or click one on the board</span></label>
</header>

<main>
  <section class="panel">
    <h2>Engine truth <span id="truthSub"></span></h2>
    <canvas id="board" width="800" height="800"></canvas>
    <div class="inspect" id="inspectTruth">Hover a tile.</div>
    <div class="legend">
      <span><i style="background:var(--ore)"></i>ore</span>
      <span><i style="background:var(--wall)"></i>wall</span>
      <span><i class="dot" style="background:var(--truth)"></i>our unit (slot number) — click to select</span>
      <span><i class="dot" style="background:var(--enemy)"></i>enemy unit / building</span>
      <span><i class="ring" style="color:var(--ok)"></i>selected unit's reckoning — matches where the unit was at the end of last round</span>
      <span><i class="ring" style="color:var(--bad)"></i>reckoning off (line to truth)</span>
    </div>
  </section>

  <section class="panel">
    <h2>Internal map of the selected unit <span id="mapSub"></span></h2>
    <canvas id="imap" width="800" height="800"></canvas>
    <div class="inspect" id="inspectMap">Hover a tile.</div>
    <div class="legend">
      <span><i style="background:var(--unknown)"></i>never heard of</span>
      <span><i style="background:var(--floor)"></i>known empty</span>
      <span><i style="background:var(--ore)"></i>ore</span><span><i style="background:var(--wall)"></i>wall</span>
      <span><i class="dot" style="background:var(--ours)"></i>ours</span><span><i class="dot" style="background:var(--theirs)"></i>enemy</span>
      <span><i style="border:2px solid var(--text);background:transparent"></i>seen with own eyes</span>
      <span><i class="dash" style="color:var(--accent)"></i>heard via the store</span>
      <span><i class="dash" style="color:var(--muted)"></i>inferred from symmetry</span>
      <span><i style="background:var(--bad)"></i>disagrees with truth</span>
      <span>faded = old information · ground colour, building glyph and bot dot are three separate facts</span>
    </div>
    <div class="status" id="status"></div>
  </section>

  <section class="panel store">
    <h2>Global Communication Store — 16 slots, as the selected unit decodes them</h2>
    <div class="wrap"><table id="slots"><thead><tr><th>slot</th><th>owner</th><th>raw u32</th><th>format</th><th>decoded</th></tr></thead><tbody></tbody></table></div>
  </section>
</main>

<script type="module">
const DATA = await (async () => {
  const bytes = Uint8Array.from(atob("__DATA__"), c => c.charCodeAt(0));
  const ds = new DecompressionStream("gzip");
  const stream = new Blob([bytes]).stream().pipeThrough(ds);
  return JSON.parse(await new Response(stream).text());
})();
const STATES = DATA.states;
const R = DATA.rounds, W = DATA.w, H = DATA.h;
const FOV_R2 = {core:36, builder_bot:20, gunner:13, sentinel:32, launcher:26};
const CTRL = ["ASSIGN","SYMMETRY","DIRECTIVE"];
const MOVES = ["", "N", "E", "S", "W"];
const SYM = ["left-right mirror", "top-bottom mirror", "180° rotation"];
const SRC = {s:"seen with own eyes", g:"heard via the store", i:"inferred from symmetry"};

const slotOf = {}, kindOf = {}, holder = [];   // holder[r][slot] = unit id claiming it that round
R.forEach(rd => { const h = {}; for (const [id, t] of Object.entries(rd.traces)) { if (t.slot !== null) { slotOf[id] = t.slot; h[t.slot] = +id; } kindOf[id] = t.kind; } holder.push(h); });
const viewers = Object.keys(kindOf).map(Number).sort((a,b)=>a-b);

// the selected unit's internal map, rebuilt from per-round deltas
const mapCache = {};
function mapUpTo(viewer, r) {
  if (!mapCache[viewer]) mapCache[viewer] = {upto:-1, tiles:new Map()};
  const c = mapCache[viewer];
  if (r < c.upto) { c.upto = -1; c.tiles = new Map(); }
  for (let i = c.upto + 1; i <= r; i++) {
    const t = R[i].traces[viewer];
    if (t && t.map_delta) for (const [x,y,st,src,rnd,layer] of t.map_delta) {
      const k = x+","+y, cur = c.tiles.get(k) || {};
      cur[layer] = {st, src, rnd, at:i};          // "t" terrain, "b" building, "u" unit
      c.tiles.set(k, cur);
    }
  }
  c.upto = r;
  return c.tiles;
}

const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const board = document.getElementById('board'), bctx = board.getContext('2d');
const imap = document.getElementById('imap'), mctx = imap.getContext('2d');
let round = 0, viewer = viewers[0], timer = null, C = {};
const geo = cv => { const size = Math.min(cv.width / W, cv.height / H); return {size, ox:(cv.width-size*W)/2, oy:(cv.height-size*H)/2}; };

function stateName(st){ return STATES[st] || ("#"+st); }
function terrainOf(name){ return name==="WALL" ? 1 : name==="ORE" ? 2 : name==="EMPTY" ? 0 : null; }

function drawGrid(ctx, g) {
  // axis labels: x runs right, y runs down, (0,0) top-left — the engine's own convention
  ctx.fillStyle = C.muted; ctx.font = `${Math.max(8, g.size*.38)}px "IBM Plex Mono",monospace`; ctx.textAlign = "left"; ctx.textBaseline = "top";
  for (let x=0;x<W;x++) ctx.fillText(x, g.ox+x*g.size+2, g.oy+1);
  for (let y=1;y<H;y++) ctx.fillText(y, g.ox+2, g.oy+y*g.size+1);
  ctx.strokeStyle = C.line; ctx.lineWidth = 0.5; ctx.globalAlpha = .6;
  for (let x=0;x<=W;x++){ctx.beginPath();ctx.moveTo(g.ox+x*g.size,g.oy);ctx.lineTo(g.ox+x*g.size,g.oy+H*g.size);ctx.stroke();}
  for (let y=0;y<=H;y++){ctx.beginPath();ctx.moveTo(g.ox,g.oy+y*g.size);ctx.lineTo(g.ox+W*g.size,g.oy+y*g.size);ctx.stroke();}
  ctx.globalAlpha = 1;
}
function glyph(ctx, cx, cy, size, name, color) {
  // units: circle; buildings: square; turrets/conveyors get a facing tick
  const unit = name.endsWith("BUILDER_BOT");
  ctx.fillStyle = color;
  if (unit) { ctx.beginPath(); ctx.arc(cx, cy, size*.3, 0, Math.PI*2); ctx.fill(); }
  else if (name.endsWith("CORE")) ctx.fillRect(cx-size*.42, cy-size*.42, size*.84, size*.84);
  else ctx.fillRect(cx-size*.28, cy-size*.28, size*.56, size*.56);
  const m = name.match(/_(N|NE|E|SE|S|SW|W|NW)$/);
  if (m) {
    const ang = {N:-90,NE:-45,E:0,SE:45,S:90,SW:135,W:180,NW:-135}[m[1]] * Math.PI/180;
    ctx.strokeStyle = C.panel; ctx.lineWidth = Math.max(1.5, size*.12);
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(ang)*size*.42, cy + Math.sin(ang)*size*.42); ctx.stroke();
  }
}

function drawTruth() {
  const g = geo(board), ctx = bctx, rd = R[round], t = rd.traces[viewer];
  ctx.fillStyle = C.floor; ctx.fillRect(0,0,board.width,board.height);
  for (let y=0;y<H;y++) for (let x=0;x<W;x++) {
    const v = DATA.tiles[y][x];
    ctx.fillStyle = v===1 ? C.wall : v===2 ? C.ore : C.floor;
    ctx.fillRect(g.ox+x*g.size, g.oy+y*g.size, g.size, g.size);
  }
  drawGrid(ctx, g);
  for (const c of DATA.cores) { ctx.fillStyle = c.owner===1 ? C.truth : C.enemy; ctx.fillRect(g.ox+c.pos[0]*g.size+1, g.oy+c.pos[1]*g.size+1, 2*g.size-2, 2*g.size-2); }
  const me = rd.ents.find(e => e.id === viewer);
  const vpos = me ? me.pos : (t ? t.pos : null);
  if (vpos) { const r2 = FOV_R2[kindOf[viewer]] || 20, rr = Math.floor(Math.sqrt(r2));
    ctx.fillStyle = C.accent; ctx.globalAlpha = .10;
    for (let dy=-rr;dy<=rr;dy++) for (let dx=-rr;dx<=rr;dx++) if (dx*dx+dy*dy<=r2) ctx.fillRect(g.ox+(vpos[0]+dx)*g.size, g.oy+(vpos[1]+dy)*g.size, g.size, g.size);
    ctx.globalAlpha = 1; }
  for (const e of rd.ents) {
    const cx = g.ox+(e.pos[0]+.5)*g.size, cy = g.oy+(e.pos[1]+.5)*g.size, color = e.team==="A" ? C.truth : C.enemy;
    if (["builder_bot","gunner","launcher","sentinel"].includes(e.type)) {
      ctx.beginPath(); ctx.arc(cx, cy, g.size*.36, 0, Math.PI*2); ctx.fillStyle = color; ctx.fill();
      const slotNow = (rd.traces[e.id] || {}).slot;
      if (e.team==="A" && slotNow !== null && slotNow !== undefined) { ctx.fillStyle = C.panel; ctx.font = `500 ${Math.max(9,g.size*.5)}px "IBM Plex Mono",monospace`; ctx.textAlign="center"; ctx.textBaseline="middle"; ctx.fillText(slotNow, cx, cy+0.5); }
    } else { ctx.fillStyle = color; ctx.globalAlpha = .45; ctx.fillRect(cx-g.size*.3, cy-g.size*.3, g.size*.6, g.size*.6); ctx.globalAlpha = 1; }
  }
  if (me) { ctx.strokeStyle = C.accent; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(g.ox+(me.pos[0]+.5)*g.size, g.oy+(me.pos[1]+.5)*g.size, g.size*.5, 0, Math.PI*2); ctx.stroke(); }
  // reckoning vs where units were at the end of last round (what this round's store describes)
  const prevPos = {}; if (round > 0) for (const e of R[round-1].ents) prevPos[e.id] = e.pos;
  let ok = 0, bad = 0, unknown = 0;
  if (t) for (const [slot, [kind, pos]] of Object.entries(t.owners)) {
    if (!pos || kind==="core") continue;
    const id = round > 0 ? holder[round-1][slot] : undefined;
    const truth = id !== undefined ? (prevPos[id] || null) : null;
    const match = truth && truth[0]===pos[0] && truth[1]===pos[1];
    if (!truth) unknown++; else if (match) ok++; else bad++;
    const cx = g.ox+(pos[0]+.5)*g.size, cy = g.oy+(pos[1]+.5)*g.size;
    ctx.strokeStyle = !truth ? C.text : match ? C.ok : C.bad; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.arc(cx, cy, g.size*.46, 0, Math.PI*2); ctx.stroke();
    if (truth && !match) { ctx.beginPath(); ctx.moveTo(cx,cy); ctx.lineTo(g.ox+(truth[0]+.5)*g.size, g.oy+(truth[1]+.5)*g.size); ctx.stroke(); }
  }
  document.getElementById('truthSub').textContent = `${rd.ents.filter(e=>e.team==="A").length} ours · ${rd.ents.filter(e=>e.team==="B").length} enemy on the board`;
  return {ok, bad, unknown};
}

function drawInternal() {
  const g = geo(imap), ctx = mctx, rd = R[round], t = rd.traces[viewer];
  const tiles = mapUpTo(viewer, round);
  ctx.fillStyle = C.unknown; ctx.fillRect(0,0,imap.width,imap.height);
  let known = 0, seen = 0, heard = 0, inferred = 0, wrong = 0, terrainKnown = 0;
  // truth per tile, split by layer: a conveyor and the bot on it are both there
  const entsNow = new Map();
  for (const e of rd.ents) { const k = e.pos[0]+","+e.pos[1], cur = entsNow.get(k) || {};
    if (e.type === "builder_bot") cur.unit = e; else cur.building = e; entsNow.set(k, cur); }
  const border = (rec, px, py) => {
    ctx.lineWidth = 1.5;
    if (rec.src === "s") { ctx.setLineDash([]); ctx.strokeStyle = C.text; ctx.globalAlpha = .35; }
    else if (rec.src === "g") { ctx.setLineDash([3,2]); ctx.strokeStyle = C.accent; ctx.globalAlpha = .9; }
    else { ctx.setLineDash([1,2]); ctx.strokeStyle = C.muted; ctx.globalAlpha = .8; }
    ctx.strokeRect(px+1.5, py+1.5, g.size-3, g.size-3); ctx.setLineDash([]); ctx.globalAlpha = 1;
  };
  const live = rec => rec && stateName(rec.st) !== "EMPTY" ? rec : null;
  for (const [k, tile] of tiles) {
    const [x, y] = k.split(",").map(Number), px = g.ox+x*g.size, py = g.oy+y*g.size;
    const terr = tile.t, bld = live(tile.b), unit = live(tile.u);
    known++;
    const top = unit || bld || terr || tile.b || tile.u;
    if (top.src==="s") seen++; else if (top.src==="g") heard++; else inferred++;
    // terrain layer: what the unit believes the ground is
    const tname = terr ? stateName(terr.st) : null;
    ctx.fillStyle = tname==="WALL" ? C.wall : tname==="ORE" ? C.ore : C.floor;
    ctx.fillRect(px, py, g.size, g.size);
    let disagree = false;
    if (terr) { terrainKnown++; if (terrainOf(tname) !== DATA.tiles[y][x]) disagree = true; }
    const truth = entsNow.get(k) || {};
    // building layer
    if (bld) {
      const name = stateName(bld.st), ours = name.startsWith("OUR_"), age = round - bld.rnd;
      const onCore = DATA.cores.some(c => x>=c.pos[0] && x<=c.pos[0]+1 && y>=c.pos[1] && y<=c.pos[1]+1 && (c.owner===1)===ours);
      const e = truth.building;
      if (name.endsWith("CORE")) { if (!onCore) disagree = true; }
      else if (name.startsWith("TOOK_FIRE") || name.endsWith("_ISSUE")) {}
      else if (!e) disagree = age > 0;
      else if ((e.team==="A") !== ours) disagree = true;
      ctx.globalAlpha = Math.max(.35, 1 - age/60);
      glyph(ctx, px+g.size/2, py+g.size/2, g.size, name, ours ? C.ours : C.theirs);
      ctx.globalAlpha = 1;
    }
    // unit layer: a bot on top, drawn smaller so the building stays visible
    if (unit) {
      const name = stateName(unit.st), ours = name.startsWith("OUR_"), age = round - unit.rnd;
      const e = truth.unit;
      if (!e) disagree = disagree || age > 0; else if ((e.team==="A") !== ours) disagree = true;
      ctx.globalAlpha = Math.max(.35, 1 - age/60);
      ctx.fillStyle = ours ? C.ours : C.theirs; ctx.beginPath(); ctx.arc(px+g.size/2, py+g.size/2, g.size*.22, 0, Math.PI*2); ctx.fill();
      ctx.strokeStyle = C.panel; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.globalAlpha = 1;
    }
    if (disagree) { wrong++; ctx.fillStyle = C.bad; ctx.globalAlpha = .45; ctx.fillRect(px+1, py+1, g.size-2, g.size-2); ctx.globalAlpha = 1; }
    border(top, px, py);
    const at = Math.max(...[tile.t, tile.b, tile.u].filter(Boolean).map(r => r.at));
    if (at === round) { ctx.strokeStyle = C.accent; ctx.lineWidth = 2.5; ctx.strokeRect(px+1, py+1, g.size-2, g.size-2); }
  }
  drawGrid(ctx, g);
  const me = rd.ents.find(e => e.id === viewer);
  if (me) { ctx.strokeStyle = C.accent; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(g.ox+(me.pos[0]+.5)*g.size, g.oy+(me.pos[1]+.5)*g.size, g.size*.5, 0, Math.PI*2); ctx.stroke(); }
  if (t && t.enemy_core) { const [x,y] = t.enemy_core; ctx.strokeStyle = C.theirs; ctx.lineWidth = 2.5; ctx.setLineDash([4,3]); ctx.strokeRect(g.ox+x*g.size+1, g.oy+y*g.size+1, 2*g.size-2, 2*g.size-2); ctx.setLineDash([]); }
  document.getElementById('mapSub').textContent = `${known} of ${W*H} tiles known · ${seen} seen · ${heard} heard · ${inferred} inferred`;
  return {known, seen, heard, inferred, wrong, terrainKnown};
}

function pill(text, cls) { return `<span class="pill ${cls||''}">${text}</span>`; }
function renderStatus(t, reck, m) {
  const el = document.getElementById('status');
  if (!t) { el.innerHTML = `<div><b>unit</b><span>no trace this round (not alive yet, or dead)</span></div>`; return; }
  let win = 'normal';
  if (t.resync === t.r) win = 'resync round — everyone writes its absolute position';
  else if (t.onboard_until !== null && t.resync !== null && t.r > t.resync && t.r <= t.onboard_until) win = `onboarding ${t.r - t.resync} / ${t.onboard_until - t.resync} — Core streams through turret slots`;
  el.innerHTML = `
    <div><b>unit</b><span>${t.kind} #${viewer} · slot ${t.slot ?? '—'} · at (${t.pos})</span></div>
    <div><b>round window</b><span>${win}</span></div>
    <div><b>symmetry</b><span>${t.symmetry === null || t.symmetry === undefined ? '<span class="pill dim">not yet known</span>' : SYM[t.symmetry] + (t.enemy_core ? ` → enemy Core at (${t.enemy_core})` : '')}</span></div>
    <div><b>core HP (latched)</b><span class="mono">${t.core_hp}</span></div>
    <div><b>wrote this round</b><span class="mono">${t.wrote === null ? '— (silent)' : t.wrote}</span></div>
    <div><b>map vs truth</b><span>${pill((m.known - m.wrong) + ' tiles right', 'ok')} ${m.wrong ? pill(m.wrong + ' wrong or stale', 'bad') : ''}</span></div>
    <div><b>reckoned positions</b><span>${pill(reck.ok+' exact','ok')} ${reck.bad ? pill(reck.bad+' off','bad') : ''} ${reck.unknown ? pill(reck.unknown+' unit not on board','dim') : ''}</span></div>`;
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
    if (d.events && d.events.length) for (const [k,a] of d.events) parts.push(`<b>${CTRL[k]||'ctrl'+k}</b>(${k===1 ? SYM[a[0]] : a.join(', ')})`);
    if (d.position) parts.push(`<b>pos</b> (${d.position})`);
    if (d.move) parts.push(`move <b>${MOVES[d.move]}</b>`);
    if (d.turn) parts.push(`turn <b>${d.turn===1?'CW':'CCW'}</b>`);
    if (d.aux) parts.push(`grants slot <b>${d.aux}</b>`);
    if (d.facts && d.facts.length) parts.push(d.facts.slice(0,4).map(([x,y,st]) => `(${x},${y})=<b>${stateName(st)}</b>`).join(' ') + (d.facts.length>4 ? ` +${d.facts.length-4}` : ''));
    const fmtCls = d.format.startsWith('undecodable') ? 'bad' : ['idle','stale','-','empty','unknown owner'].includes(d.format) ? 'dim' : '';
    const cls = [(t.slot===s?'me':''), (t.wrote!==null && t.slot===s ? 'wrote':'')].join(' ');
    html += `<tr class="${cls}"><td class="mono">${s}</td><td>${ownerTxt}</td><td class="raw ${d.changed?'changed':''}"><span class="dot ${d.changed?'on':''}"></span>${d.raw}</td><td>${pill(d.format, fmtCls)}</td><td class="decoded">${parts.join(' · ') || '—'}</td></tr>`;
  }
  tb.innerHTML = html;
}

function draw() {
  C = {floor:cssVar('--floor'), ore:cssVar('--ore'), wall:cssVar('--wall'), truth:cssVar('--truth'), ok:cssVar('--ok'), bad:cssVar('--bad'),
       enemy:cssVar('--enemy'), text:cssVar('--text'), accent:cssVar('--accent'), line:cssVar('--line'), panel:cssVar('--panel'),
       unknown:cssVar('--unknown'), ours:cssVar('--ours'), theirs:cssVar('--theirs'), muted:cssVar('--muted')};
  const t = R[round].traces[viewer];
  const reck = drawTruth();
  const m = drawInternal();
  renderStatus(t, reck, m);
  renderSlots(t);
}

// hover inspectors + click to select
function tileAt(cv, ev) { const g = geo(cv), rect = cv.getBoundingClientRect();
  const x = Math.floor(((ev.clientX-rect.left) * cv.width/rect.width - g.ox)/g.size), y = Math.floor(((ev.clientY-rect.top) * cv.height/rect.height - g.oy)/g.size);
  return (x>=0 && y>=0 && x<W && y<H) ? [x,y] : null; }
board.addEventListener('mousemove', ev => { const p = tileAt(board, ev); const el = document.getElementById('inspectTruth'); if (!p) return;
  const v = DATA.tiles[p[1]][p[0]], e = R[round].ents.find(e => e.pos[0]===p[0] && e.pos[1]===p[1]);
  el.innerHTML = `(${p}) <b>${v===1?'wall':v===2?'ore':'empty'}</b>` + (e ? ` · <b>${e.type}</b> #${e.id} team ${e.team} hp ${e.hp}/${e.maxhp}${slotOf[e.id]!==undefined?' · slot '+slotOf[e.id]:''}` : ''); });
board.addEventListener('click', ev => { const p = tileAt(board, ev); if (!p) return;
  const e = R[round].ents.find(e => e.team==="A" && e.pos[0]===p[0] && e.pos[1]===p[1] && kindOf[e.id]);
  const core = DATA.cores.find(c => c.owner===1 && p[0]>=c.pos[0] && p[0]<=c.pos[0]+1 && p[1]>=c.pos[1] && p[1]<=c.pos[1]+1);
  const id = e ? e.id : core ? viewers.find(v => kindOf[v]==="core") : null;
  if (id !== null && id !== undefined) { viewer = id; document.getElementById('viewer').value = id; draw(); } });
imap.addEventListener('mousemove', ev => { const p = tileAt(imap, ev); const el = document.getElementById('inspectMap'); if (!p) return;
  const tile = mapUpTo(viewer, round).get(p[0]+","+p[1]);
  if (!tile) { el.innerHTML = `(${p}) <b>never heard of</b>`; return; }
  const v = DATA.tiles[p[1]][p[0]];
  const desc = rec => `<b>${stateName(rec.st)}</b> (${SRC[rec.src]}, from round ${rec.rnd}, ${round-rec.rnd} old)`;
  el.innerHTML = `(${p}) ground: ${tile.t ? desc(tile.t) : '<b>unknown</b>'} · building: ${tile.b ? desc(tile.b) : '<b>unknown</b>'} · bot: ${tile.u ? desc(tile.u) : '<b>unknown</b>'} · truth ground: ${v===1?'wall':v===2?'ore':'empty'}`; });

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
    holder = []          # per round: slot -> unit id that claimed it that round
    for rd in rounds:
        h = {}
        for uid, t in rd["traces"].items():
            if t["slot"] is not None:
                slot_of[int(uid)] = t["slot"]
                h[t["slot"]] = int(uid)
            kind_of[int(uid)] = t["kind"]
        holder.append(h)
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
                uid = holder[r - 1].get(int(slot)) if r else None
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
            if name in ("WALL", "ORE"):          # EMPTY means "no occupant", not ground
                if (name, v) in (("WALL", 1), ("ORE", 2)):
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
    raw = json.dumps(data, separators=(",", ":")).encode()
    packed = base64.b64encode(gzip.compress(raw, 9)).decode()
    html = TEMPLATE.replace("__DATA__", packed)
    Path(sys.argv[2]).write_text(html)
    n_tr = sum(len(r["traces"]) for r in data["rounds"])
    print(f"{sys.argv[2]}: {data['w']}x{data['h']} map, {len(data['rounds'])} rounds, "
          f"{n_tr} trace lines, {len(html)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
