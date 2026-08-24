"""Render census.json into a single self-contained overview page."""

from __future__ import annotations

import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    data = json.load(open(HERE / "census.json"))
    days = data["days"]
    league = data["league_by_day"]

    # Trim the payload the page actually needs; the full census.json keeps everything.
    teams = [
        {
            "n": t["name"], "rk": t["rank"], "rt": t["rating"], "m": t["matches"],
            "rm": t["rated_matches"], "w": t["win_rate"], "v": t["versions_seen"],
            "ad": t["active_days"], "f": t["first_match"][:10], "l": t["last_match"][:10],
            "reg": t["region"], "st": t["student"], "mem": t["members"], "ol": t["on_ladder"],
            "pk": t["rating_peak"], "lo": t["rating_low"], "s0": t["rating_start"],
            "vmax": t["version_max"], "wn": t["wins"], "ls": t["losses"],
            "so": t["sparring_ordered"], "sr": t["sparring_replayed"],
            "ot": t["ordered_targets"],
            "ob": [t["ordered_by_day"].get(d, 0) for d in days],
            "d": [t["matches_by_day"].get(d, 0) for d in days],
            "u": [t["new_versions_by_day"].get(d, 0) for d in days],
            "vd": [t["version_by_day"].get(d) for d in days],
            "tr": t["rating_track"],
            "op": t["opponents"][:14],
        }
        for t in data["teams"]
    ]
    payload = {
        "days": days,
        "league": [league[d] for d in days],
        "teams": teams,
        "totals": {
            "matches": data["matches_total"],
            "teams": data["teams_total"],
            "versions": sum(t["v"] for t in teams),
            "unrated": data["unrated_total"],
            "attributed": data["unrated_attributed"],
        },
    }

    body = TEMPLATE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
    out = HERE / "overview.html"
    out.write_text(body)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    return 0


TEMPLATE = r"""<title>Ladder Census</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Chivo:wght@700;900&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{
  --ground:#F0F4F4; --surface:#FFFFFF; --sunk:#E6ECEC;
  --ink:#111A1C; --body:#2C3A3C; --muted:#65787A;
  --line:#D3DDDD; --line-soft:#E3EAEA;
  --accent:#0B6E77; --accent-soft:#0B6E7726; --accent-ink:#0B6E77;
  --alt:#A6491A; --alt-soft:#A6491A22;
  --good:#2C6E4B; --warn:#8A6410;
  --shadow:0 1px 2px #111a1c0d, 0 8px 24px #111a1c0a;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#0D1315; --surface:#141C1E; --sunk:#101819;
    --ink:#EAF1F1; --body:#C2D0D1; --muted:#8A9C9D;
    --line:#263335; --line-soft:#1D292B;
    --accent:#4FBFC6; --accent-soft:#4FBFC626; --accent-ink:#7FD6DB;
    --alt:#E08A54; --alt-soft:#E08A5422;
    --good:#6FC08F; --warn:#D2A64A;
    --shadow:0 1px 2px #0006, 0 8px 24px #0004;
  }
}
:root[data-theme="dark"]{
  --ground:#0D1315; --surface:#141C1E; --sunk:#101819;
  --ink:#EAF1F1; --body:#C2D0D1; --muted:#8A9C9D;
  --line:#263335; --line-soft:#1D292B;
  --accent:#4FBFC6; --accent-soft:#4FBFC626; --accent-ink:#7FD6DB;
  --alt:#E08A54; --alt-soft:#E08A5422;
  --good:#6FC08F; --warn:#D2A64A;
  --shadow:0 1px 2px #0006, 0 8px 24px #0004;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--body);
  font-family:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1140px; margin:0 auto; padding:48px 24px 96px; display:flex; flex-direction:column; gap:44px}
h1,h2,h3{font-family:Chivo,"IBM Plex Sans",sans-serif; color:var(--ink); margin:0; text-wrap:balance}
h1{font-size:clamp(34px,5.5vw,52px); font-weight:900; letter-spacing:-.022em; line-height:1.02}
h2{font-size:20px; font-weight:700; letter-spacing:-.008em}
.eyebrow{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:11.5px; font-weight:500;
  letter-spacing:.16em; text-transform:uppercase; color:var(--accent-ink);
}
.lede{max-width:64ch; font-size:16.5px; color:var(--body)}
.sub{font-size:13.5px; color:var(--muted); max-width:70ch}
header{display:flex; flex-direction:column; gap:14px; border-bottom:1px solid var(--line); padding-bottom:34px}
.tiles{display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:1px; background:var(--line-soft);
  border:1px solid var(--line-soft); border-radius:10px; overflow:hidden; margin-top:8px}
.tile{background:var(--surface); padding:16px 18px; display:flex; flex-direction:column; gap:3px}
.tile b{font-family:Chivo,sans-serif; font-size:27px; font-weight:700; color:var(--ink);
  font-variant-numeric:tabular-nums; letter-spacing:-.02em; line-height:1.1}
.tile span{font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.1em;
  text-transform:uppercase; color:var(--muted)}
section{display:flex; flex-direction:column; gap:18px}
.sec-head{display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between; gap:12px}
.card{background:var(--surface); border:1px solid var(--line); border-radius:12px; box-shadow:var(--shadow)}
.chart{padding:22px 20px 14px}
.legend{display:flex; gap:18px; flex-wrap:wrap; font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--muted)}
.key{display:inline-flex; align-items:center; gap:7px}
.swatch{width:11px; height:11px; border-radius:2px; display:inline-block}
.scroll{overflow-x:auto}
table{border-collapse:collapse; width:100%; min-width:940px; font-size:13.5px}
thead th{
  position:sticky; top:0; z-index:2; background:var(--surface);
  font-family:"IBM Plex Mono",monospace; font-size:10.5px; font-weight:600; letter-spacing:.09em;
  text-transform:uppercase; color:var(--muted); text-align:right; padding:12px 10px;
  border-bottom:1px solid var(--line); white-space:nowrap; cursor:pointer; user-select:none;
}
thead th:first-child,thead th.left{text-align:left}
thead th:hover{color:var(--accent-ink)}
thead th[aria-sort]{color:var(--accent-ink)}
thead th .ind{opacity:.55; font-size:9px}
tbody td{padding:10px; border-bottom:1px solid var(--line-soft); text-align:right;
  font-variant-numeric:tabular-nums; white-space:nowrap}
tbody td.left{text-align:left; white-space:normal}
tbody tr:hover{background:var(--sunk)}
.rank{font-family:"IBM Plex Mono",monospace; color:var(--muted); width:44px}
.name{font-weight:600; color:var(--ink); font-size:14px}
.who{font-size:11.5px; color:var(--muted); font-family:"IBM Plex Mono",monospace}
.pill{display:inline-block; padding:1px 7px; border-radius:99px; font-family:"IBM Plex Mono",monospace;
  font-size:10px; letter-spacing:.06em; text-transform:uppercase; border:1px solid var(--line)}
.pill.live{color:var(--good); border-color:currentColor}
.pill.gone{color:var(--muted)}
.num{font-family:"IBM Plex Mono",monospace}
.bar-cell{width:170px}
.controls{display:flex; gap:10px; flex-wrap:wrap; align-items:center}
th.quiet,td.quiet{color:var(--muted); font-size:12px}
tbody tr{cursor:pointer}
tbody tr:focus-visible{outline:2px solid var(--accent); outline-offset:-2px}
.chev{color:var(--muted); font-size:11px; padding-left:4px}
tbody tr:hover .chev{color:var(--accent-ink)}

dialog#detail{
  border:1px solid var(--line); border-radius:14px; background:var(--surface); color:var(--body);
  padding:0; max-width:min(920px,94vw); width:920px; box-shadow:0 24px 70px #111a1c33;
}
dialog#detail::backdrop{background:#0b1213b3; backdrop-filter:blur(2px)}
.dlg{display:flex; flex-direction:column; gap:26px; padding:28px 30px 30px}
.dlg-head{display:flex; justify-content:space-between; align-items:flex-start; gap:16px;
  border-bottom:1px solid var(--line); padding-bottom:18px}
.dlg-head h3{font-size:27px; font-weight:900; letter-spacing:-.02em; line-height:1.1}
.dlg-head .who{margin-top:5px}
.tags{display:flex; gap:6px; flex-wrap:wrap; margin-top:9px}
.close{background:none; border:1px solid var(--line); color:var(--muted); border-radius:8px;
  font-family:"IBM Plex Mono",monospace; font-size:12px; padding:5px 11px; cursor:pointer; flex:none}
.close:hover{color:var(--ink); border-color:var(--muted)}
.stats{display:grid; grid-template-columns:repeat(auto-fit,minmax(104px,1fr)); gap:1px;
  background:var(--line-soft); border:1px solid var(--line-soft); border-radius:9px; overflow:hidden}
.stats div{background:var(--surface); padding:11px 13px; display:flex; flex-direction:column; gap:2px}
.stats b{font-family:Chivo,sans-serif; font-size:20px; color:var(--ink);
  font-variant-numeric:tabular-nums; letter-spacing:-.015em}
.stats span{font-family:"IBM Plex Mono",monospace; font-size:9.5px; letter-spacing:.09em;
  text-transform:uppercase; color:var(--muted)}
.panel{display:flex; flex-direction:column; gap:9px}
.panel h4{margin:0; font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.13em;
  text-transform:uppercase; color:var(--muted); font-weight:600}
.opps{display:grid; grid-template-columns:repeat(auto-fill,minmax(232px,1fr)); gap:7px 20px}
.opp{display:grid; grid-template-columns:1fr 62px 46px; gap:9px; align-items:center; font-size:12.5px;
  padding:4px 0; border-bottom:1px solid var(--line-soft)}
.opp .on{color:var(--ink); overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.opp .om{font-family:"IBM Plex Mono",monospace; color:var(--muted); font-size:11.5px;
  font-variant-numeric:tabular-nums; text-align:right}
.opp .ow{font-family:"IBM Plex Mono",monospace; font-variant-numeric:tabular-nums; text-align:right;
  font-weight:600}
.win-hi{color:var(--good)} .win-lo{color:var(--alt)}
@media (max-width:640px){.dlg{padding:20px 16px 24px}.dlg-head h3{font-size:22px}}
input[type=search]{
  font-family:"IBM Plex Mono",monospace; font-size:13px; padding:8px 12px; border-radius:8px;
  border:1px solid var(--line); background:var(--surface); color:var(--ink); min-width:220px;
}
input[type=search]:focus-visible,th:focus-visible,button:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
.note{font-size:12.5px; color:var(--muted); font-family:"IBM Plex Mono",monospace; line-height:1.7}
footer{border-top:1px solid var(--line); padding-top:22px; display:flex; flex-direction:column; gap:8px}
code{font-family:"IBM Plex Mono",monospace; font-size:.92em; background:var(--sunk); padding:1px 5px; border-radius:4px}
@media (max-width:640px){.wrap{padding:32px 14px 64px; gap:34px}}
</style>

<div class="wrap">
<header>
  <div class="eyebrow">Florent Code League &middot; complete match log</div>
  <h1>Ladder Census</h1>
  <p class="lede">What every team shipped and when. Ranked by rating, measured by release
  cadence &mdash; matches played is a pairing artifact and is left out entirely.</p>
  <div class="tiles" id="tiles"></div>
  <p class="sub" id="stamp"></p>
</header>

<section>
  <div class="sec-head">
    <h2>Releases, day by day</h2>
    <div class="legend">
      <span class="key"><i class="swatch" style="background:var(--alt)"></i>new versions uploaded</span>
      <span class="key"><i class="swatch" style="background:var(--accent)"></i>sparring ordered</span>
      <span class="key"><i class="swatch" style="background:var(--muted)"></i>teams shipping</span>
    </div>
  </div>
  <div class="card chart"><div id="league"></div></div>
  <p class="note" id="leaguenote"></p>
</section>

<section>
  <div class="sec-head">
    <h2>Who orders the sparring</h2>
    <span class="note" id="attnote"></span>
  </div>
  <div class="card chart"><div id="initiators"></div></div>
  <p class="note" id="attmethod"></p>
</section>

<section>
  <div class="sec-head">
    <h2>Every team</h2>
    <div class="controls">
      <input type="search" id="q" placeholder="filter team or member" aria-label="Filter teams">
      <span class="note" id="count"></span>
    </div>
  </div>
  <div class="card scroll">
    <table id="tbl">
      <thead><tr>
        <th class="left" data-k="rk">#</th>
        <th class="left" data-k="n">Team</th>
        <th data-k="rt">Rating</th>
        <th data-k="pk">Peak</th>
        <th data-k="w">Win&nbsp;%</th>
        <th data-k="v">Versions</th>
        <th data-k="vr">Per&nbsp;day</th>
        <th data-k="sd">Ship&nbsp;days</th>
        <th data-k="so">Sparring&nbsp;ordered</th>
        <th class="left" data-k="f">Rating &amp; releases &middot; Aug 1&ndash;22</th>
        <th class="left" data-k="l">Last seen</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>
  <p class="note">Each row's strip is that team's rating through the log, with copper ticks marking
  days it shipped a version the ladder had never seen. Click any row for the full history.</p>
</section>

<dialog id="detail" aria-label="Team detail"><div class="dlg" id="dlgbody"></div></dialog>

<footer>
  <p class="note" id="prov"></p>
  <p class="note">Rebuild: <code>uv run python tools/league_census/scrape.py</code> then
  <code>overview.py</code> and <code>render.py</code>.</p>
</footer>
</div>

<script>
const D = __DATA__;
const NS = "http://www.w3.org/2000/svg";
const el = (t, a = {}) => { const n = document.createElementNS(NS, t);
  for (const k in a) n.setAttribute(k, a[k]); return n; };
const fmt = n => n.toLocaleString("en-US");
const shortDay = d => { const [, m, dd] = d.split("-"); return (+dd) + "/" + (+m); };

/* ---- headline tiles ---- */

const totalUploads = D.league.reduce((a, v) => a + v.new_versions, 0);
const peakUp = D.days[D.league.map(v => v.new_versions).indexOf(Math.max(...D.league.map(v => v.new_versions)))];
document.getElementById("tiles").innerHTML = [
  [fmt(D.totals.versions), "versions shipped"],
  [fmt(Math.round(totalUploads / D.days.length)), "uploads per day"],
  [fmt(D.totals.teams), "teams tracked"],
  [fmt(D.league.at(-1).new_versions), "uploads, latest day"],
].map(([b, s]) => `<div class="tile"><b>${b}</b><span>${s}</span></div>`).join("");
document.getElementById("stamp").textContent =
  `Log runs ${D.days[0]} to ${D.days.at(-1)} — the platform keeps nothing older. `
  + `Heaviest release day: ${peakUp}, ${Math.max(...D.league.map(v => v.new_versions))} new versions.`;

/* ---- league chart: match bars, upload line, team-count line ---- */
function leagueChart() {
  const W = 1060, H = 300, ml = 52, mr = 46, mt = 16, mb = 44;
  const iw = W - ml - mr, ih = H - mt - mb;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%",
    style: "display:block;height:auto;overflow:visible", role: "img",
    "aria-label": "Matches, uploads and active teams per day" });
  const maxM = Math.max(...D.league.map(v => v.new_versions)) * 1.08;
  const maxU = Math.max(...D.league.map(v => v.sparring_ordered)) * 1.2;
  const x = i => ml + (i + 0.5) * (iw / D.days.length);
  const yM = v => mt + ih - (v / maxM) * ih;
  const yU = v => mt + ih - (v / maxU) * ih;

  for (let g = 0; g <= 4; g++) {
    const v = (maxM / 4) * g, y = yM(v);
    svg.appendChild(el("line", { x1: ml, x2: ml + iw, y1: y, y2: y,
      stroke: "var(--line-soft)", "stroke-width": 1 }));
    const t = el("text", { x: ml - 10, y: y + 4, "text-anchor": "end", fill: "var(--muted)",
      "font-size": 10.5, "font-family": "IBM Plex Mono, monospace" });
    t.textContent = Math.round(v); svg.appendChild(t);
  }
  const bw = Math.max(6, iw / D.days.length - 7);
  D.league.forEach((v, i) => {
    const y = yM(v.new_versions);
    svg.appendChild(el("rect", { x: x(i) - bw / 2, y, width: bw, height: mt + ih - y,
      rx: 2, fill: "var(--alt)", opacity: .85 }));
    const lab = el("text", { x: x(i), y: mt + ih + 17, "text-anchor": "middle",
      fill: "var(--muted)", "font-size": 10, "font-family": "IBM Plex Mono, monospace" });
    lab.textContent = shortDay(D.days[i]); svg.appendChild(lab);
    const hit = el("rect", { x: x(i) - bw / 2 - 3, y: mt, width: bw + 6, height: ih, fill: "transparent" });
    const tt = el("title");
    tt.textContent = `${D.days[i]} — ${v.new_versions} new versions from ${v.teams_shipping} teams`
      + ` · ${fmt(v.sparring_ordered)} sparring matches ordered`;
    hit.appendChild(tt); svg.appendChild(hit);
  });
  const line = (vals, y, color, dash) => {
    const d = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    svg.appendChild(el("path", { d, fill: "none", stroke: color, "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round",
      ...(dash ? { "stroke-dasharray": dash } : {}) }));
    vals.forEach((v, i) => svg.appendChild(el("circle", { cx: x(i), cy: y(v), r: 2.6, fill: color })));
  };
  line(D.league.map(v => v.sparring_ordered), yU, "var(--accent)");
  const maxT = Math.max(...D.league.map(v => v.teams_shipping)) * 1.5;
  line(D.league.map(v => v.teams_shipping), v => mt + ih - (v / maxT) * ih, "var(--muted)", "3 4");
  for (let g = 0; g <= 2; g++) {
    const v = (maxU / 2) * g;
    const t = el("text", { x: ml + iw + 10, y: yU(v) + 4, fill: "var(--accent-ink)", "font-size": 10.5,
      "font-family": "IBM Plex Mono, monospace" });
    t.textContent = Math.round(v); svg.appendChild(t);
  }
  document.getElementById("league").appendChild(svg);
}
leagueChart();

document.getElementById("leaguenote").textContent =
  `Left axis (copper bars): new versions uploaded — ${fmt(totalUploads)} across the log, about `
  + `${Math.round(totalUploads / D.days.length)} a day. Right axis (teal): unrated matches someone `
  + `deliberately ordered, which has grown from single digits to ~900 a day. Dashed: how many `
  + `distinct teams shipped anything that day, which has stayed near 40 throughout.`;

/* ---- derived per-team fields ---- */
D.teams.forEach(t => {
  t.sd = t.u.filter(Boolean).length;          // days it shipped at least one version
  t.vr = t.v / Math.max(t.ad, 1);             // versions per active day
});

/* ---- who orders the sparring ---- */
function initiatorsChart() {
  const ranked = D.teams.filter(t => t.so > 0).sort((a, b) => b.so - a.so).slice(0, 14);
  const rowH = 26, W = 1060, ml = 210, mr = 60, mt = 6;
  const H = mt + ranked.length * rowH + 8, iw = W - ml - mr;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%",
    style: "display:block;height:auto;overflow:visible", role: "img",
    "aria-label": "Teams by unrated matches ordered" });
  const max = Math.max(...ranked.map(t => t.so));
  ranked.forEach((t, i) => {
    const y = mt + i * rowH;
    const name = el("text", { x: ml - 12, y: y + rowH / 2 + 4, "text-anchor": "end",
      fill: "var(--ink)", "font-size": 12.5, "font-family": '"IBM Plex Sans",sans-serif' });
    name.textContent = t.n.length > 26 ? t.n.slice(0, 25) + "…" : t.n;
    svg.appendChild(name);
    const w = (t.so / max) * iw;
    svg.appendChild(el("rect", { x: ml, y: y + 5, width: Math.max(w, 1.5), height: rowH - 12,
      rx: 2, fill: "var(--accent)", opacity: .85 }));
    const val = el("text", { x: ml + w + 9, y: y + rowH / 2 + 4, fill: "var(--muted)",
      "font-size": 11.5, "font-family": "IBM Plex Mono, monospace" });
    val.textContent = fmt(t.so); svg.appendChild(val);
    const tip = el("title");
    tip.textContent = `${t.n} ordered ${fmt(t.so)} unrated matches, and was itself replayed in `
      + `${fmt(t.sr)}`;
    svg.appendChild(tip);
  });
  return svg;
}
document.getElementById("initiators").appendChild(initiatorsChart());
const orderers = D.teams.filter(t => t.so > 0).length;
document.getElementById("attnote").textContent =
  `${fmt(D.totals.attributed)} of ${fmt(D.totals.unrated)} unrated matches attributed · `
  + `${orderers} teams ever ordered one`;
document.getElementById("attmethod").textContent =
  "Ordering a test fires several matches at once, so unrated matches created within seconds of "
  + "each other that all share one team were ordered by that team. A fifth also carry a link back "
  + "to an earlier ladder match of one side — the side being replayed — which independently names "
  + "the other side as the orderer. Where both signals speak they agree 98% of the time. Matches "
  + "ordered one at a time, with no link, cannot be attributed and are not counted.";

/* ---- per-team row strip: rating line, release ticks ---- */
function strip(t) {
  const W = 168, H = 32, bh = 21, n = D.days.length, cw = W / n;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H,
    style: "display:block", role: "img", "aria-label": `${t.n} rating and releases` });
  const track = t.tr || [];
  if (track.length > 1) {
    const vals = track.map(r => r[1]);
    const lo = Math.min(...vals), hi = Math.max(...vals), span = Math.max(hi - lo, 40);
    const px = i => (i / (track.length - 1)) * (W - 2) + 1;
    const py = v => bh - 2 - ((v - lo) / span) * (bh - 6);
    const d = track.map((r, i) => `${i ? "L" : "M"}${px(i).toFixed(1)},${py(r[1]).toFixed(1)}`).join("");
    svg.appendChild(el("path", {
      d: `${d}L${px(track.length - 1).toFixed(1)},${bh}L1,${bh}Z`,
      fill: "var(--accent-soft)", stroke: "none" }));
    svg.appendChild(el("path", { d, fill: "none", stroke: "var(--accent)", "stroke-width": 1.6,
      "stroke-linejoin": "round", "stroke-linecap": "round" }));
    svg.appendChild(el("circle", { cx: px(track.length - 1), cy: py(vals.at(-1)), r: 2.4,
      fill: "var(--accent)" }));
  }
  t.u.forEach((v, i) => {
    if (v) svg.appendChild(el("rect", { x: i * cw + .6, y: bh + 4, width: Math.max(1.4, cw - 1.2),
      height: Math.min(6, 1.6 + v * .35), fill: "var(--alt)", rx: 1 }));
  });
  svg.appendChild(el("line", { x1: 0, x2: W, y1: bh + 1.5, y2: bh + 1.5,
    stroke: "var(--line)", "stroke-width": 1 }));
  const tip = el("title");
  tip.textContent = `${t.s0 ? Math.round(t.s0) : "?"} → ${t.rt ? Math.round(t.rt) : "?"}`
    + ` · peak ${t.pk ? Math.round(t.pk) : "?"} · ${t.v} versions`;
  svg.appendChild(tip);
  return svg;
}

/* ---- table ---- */
const tbody = document.querySelector("#tbl tbody");
let sortKey = "rk", desc = false, query = "";
const lastDay = D.days.at(-1);

function render() {
  const q = query.trim().toLowerCase();
  const rows = D.teams.filter(t => !q
    || (t.n || "").toLowerCase().includes(q)
    || (t.mem || []).some(m => (m || "").toLowerCase().includes(q)));
  rows.sort((a, b) => {
    let x = a[sortKey], y = b[sortKey];
    if (x === null || x === undefined) return 1;
    if (y === null || y === undefined) return -1;
    if (typeof x === "string") return desc ? y.localeCompare(x) : x.localeCompare(y);
    return desc ? y - x : x - y;
  });
  tbody.replaceChildren(...rows.map(t => {
    const tr = document.createElement("tr");
    const live = t.l === lastDay;
    tr.tabIndex = 0;
    tr.innerHTML = `
      <td class="left rank">${t.rk ?? "—"}</td>
      <td class="left"><div class="name">${escapeHtml(t.n || "unnamed")}<span class="chev">›</span></div>
        <div class="who">${escapeHtml((t.mem || []).join(", ")) || "—"}</div></td>
      <td class="num">${t.rt ? Math.round(t.rt) : "—"}</td>
      <td class="num">${t.pk ? Math.round(t.pk) : "—"}</td>
      <td class="num">${t.w === null ? "—" : (t.w * 100).toFixed(1)}</td>
      <td class="num">${t.v}</td>
      <td class="num">${t.vr.toFixed(1)}</td>
      <td class="num">${t.sd}<span class="quiet">/${t.ad}</span></td>
      <td class="num ${t.so ? "" : "quiet"}">${t.so ? fmt(t.so) : "—"}</td>
      <td class="left bar-cell"></td>
      <td class="left"><span class="pill ${live ? "live" : "gone"}">${live ? "today" : t.l.slice(5)}</span></td>`;
    tr.children[8].appendChild(strip(t));
    tr.addEventListener("click", () => openDetail(t));
    tr.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openDetail(t); }
    });
    return tr;
  }));
  document.getElementById("count").textContent =
    `${rows.length} of ${D.teams.length} teams`;
  document.querySelectorAll("#tbl thead th").forEach(th => {
    if (th.dataset.k === sortKey) {
      th.setAttribute("aria-sort", desc ? "descending" : "ascending");
      th.querySelector(".ind")?.remove();
      const s = document.createElement("span");
      s.className = "ind"; s.textContent = desc ? " ▼" : " ▲";
      th.appendChild(s);
    } else { th.removeAttribute("aria-sort"); th.querySelector(".ind")?.remove(); }
  });
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
document.querySelectorAll("#tbl thead th").forEach(th => {
  th.tabIndex = 0;
  const go = () => {
    const k = th.dataset.k;
    if (k === sortKey) desc = !desc; else { sortKey = k; desc = !["n", "f", "l", "rk"].includes(k); }
    render();
  };
  th.addEventListener("click", go);
  th.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
});
document.getElementById("q").addEventListener("input", e => { query = e.target.value; render(); });
render();


/* ---- team detail ---- */
const dlg = document.getElementById("detail");
const dlgBody = document.getElementById("dlgbody");

function bigChart(t) {
  const W = 840, H = 250, ml = 46, mr = 46, mt = 14, mb = 34;
  const iw = W - ml - mr, ih = H - mt - mb;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%",
    style: "display:block;height:auto;overflow:visible", role: "img",
    "aria-label": `${t.n} rating and version history` });
  const track = t.tr || [];
  if (track.length < 2) {
    const txt = el("text", { x: W / 2, y: H / 2, "text-anchor": "middle", fill: "var(--muted)",
      "font-family": "IBM Plex Mono, monospace", "font-size": 13 });
    txt.textContent = "not enough rated history to plot";
    svg.appendChild(txt); return svg;
  }
  const vals = track.map(r => r[1]);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = Math.max((hi - lo) * 0.12, 25);
  const y0 = lo - pad, y1 = hi + pad;
  const t0 = Date.parse(track[0][0] + ":00:00Z"), t1 = Date.parse(track.at(-1)[0] + ":00:00Z");
  const px = b => ml + ((Date.parse(b + ":00:00Z") - t0) / Math.max(t1 - t0, 1)) * iw;
  const py = v => mt + ih - ((v - y0) / (y1 - y0)) * ih;

  for (let g = 0; g <= 4; g++) {
    const v = y0 + ((y1 - y0) / 4) * g, y = py(v);
    svg.appendChild(el("line", { x1: ml, x2: ml + iw, y1: y, y2: y,
      stroke: "var(--line-soft)", "stroke-width": 1 }));
    const lab = el("text", { x: ml - 9, y: y + 4, "text-anchor": "end", fill: "var(--muted)",
      "font-size": 10.5, "font-family": "IBM Plex Mono, monospace" });
    lab.textContent = Math.round(v); svg.appendChild(lab);
  }
  // day gridlines + labels, every other day
  D.days.forEach((day, i) => {
    if (i % 3) return;
    const x = px(day + "T00");
    if (x < ml - 1 || x > ml + iw + 1) return;
    const lab = el("text", { x, y: mt + ih + 17, "text-anchor": "middle", fill: "var(--muted)",
      "font-size": 10, "font-family": "IBM Plex Mono, monospace" });
    lab.textContent = shortDay(day); svg.appendChild(lab);
  });
  // release ticks along the baseline
  D.days.forEach((day, i) => {
    if (!t.u[i]) return;
    const x = px(day + "T12");
    if (x < ml - 1 || x > ml + iw + 1) return;
    svg.appendChild(el("line", { x1: x, x2: x, y1: mt, y2: mt + ih, stroke: "var(--alt-soft)",
      "stroke-width": Math.min(6, 1.5 + t.u[i] * 0.4) }));
    svg.appendChild(el("rect", { x: x - 1.2, y: mt + ih + 2, width: 2.4,
      height: Math.min(8, 2 + t.u[i] * 0.4), fill: "var(--alt)", rx: 1 }));
  });
  const d = track.map((r, i) => `${i ? "L" : "M"}${px(r[0]).toFixed(1)},${py(r[1]).toFixed(1)}`).join("");
  svg.appendChild(el("path", {
    d: `${d}L${px(track.at(-1)[0]).toFixed(1)},${mt + ih}L${px(track[0][0]).toFixed(1)},${mt + ih}Z`,
    fill: "var(--accent-soft)" }));
  svg.appendChild(el("path", { d, fill: "none", stroke: "var(--accent)", "stroke-width": 2,
    "stroke-linejoin": "round", "stroke-linecap": "round" }));
  const peakIdx = vals.indexOf(hi);
  svg.appendChild(el("circle", { cx: px(track[peakIdx][0]), cy: py(hi), r: 3.2,
    fill: "var(--surface)", stroke: "var(--accent)", "stroke-width": 2 }));
  svg.appendChild(el("circle", { cx: px(track.at(-1)[0]), cy: py(vals.at(-1)), r: 3.6,
    fill: "var(--accent)" }));
  const now = el("text", { x: px(track.at(-1)[0]) + 8, y: py(vals.at(-1)) + 4, fill: "var(--accent-ink)",
    "font-size": 11.5, "font-family": "IBM Plex Mono, monospace", "font-weight": 600 });
  now.textContent = Math.round(vals.at(-1)); svg.appendChild(now);
  return svg;
}

function dayBars(t, series, color, label, rightLine) {
  const W = 840, H = 132, ml = 46, mr = 46, mt = 12, mb = 26;
  const iw = W - ml - mr, ih = H - mt - mb;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%",
    style: "display:block;height:auto;overflow:visible", role: "img",
    "aria-label": `${t.n} ${label} per day` });
  const max = Math.max(...series, 1);
  const cw = iw / D.days.length;
  const y = v => mt + ih - (v / (max * 1.1)) * ih;
  for (let g = 0; g <= 2; g++) {
    const v = (max * 1.1 / 2) * g;
    svg.appendChild(el("line", { x1: ml, x2: ml + iw, y1: y(v), y2: y(v),
      stroke: "var(--line-soft)", "stroke-width": 1 }));
    const lab = el("text", { x: ml - 9, y: y(v) + 4, "text-anchor": "end", fill: "var(--muted)",
      "font-size": 10, "font-family": "IBM Plex Mono, monospace" });
    lab.textContent = Math.round(v); svg.appendChild(lab);
  }
  series.forEach((v, i) => {
    const x = ml + i * cw;
    if (v) {
      svg.appendChild(el("rect", { x: x + 1.5, y: y(v), width: Math.max(cw - 3, 2),
        height: mt + ih - y(v), rx: 2, fill: color, opacity: .88 }));
      const val = el("text", { x: x + cw / 2, y: y(v) - 4, "text-anchor": "middle",
        fill: "var(--muted)", "font-size": 9, "font-family": "IBM Plex Mono, monospace" });
      val.textContent = v; svg.appendChild(val);
    }
    if (i % 3 === 0) {
      const lab = el("text", { x: x + cw / 2, y: mt + ih + 15, "text-anchor": "middle",
        fill: "var(--muted)", "font-size": 9.5, "font-family": "IBM Plex Mono, monospace" });
      lab.textContent = shortDay(D.days[i]); svg.appendChild(lab);
    }
    const hit = el("rect", { x, y: mt, width: cw, height: ih, fill: "transparent" });
    const tip = el("title");
    tip.textContent = `${D.days[i]} — ${v} ${label}`;
    hit.appendChild(tip); svg.appendChild(hit);
  });
  svg.appendChild(el("line", { x1: ml, x2: ml + iw, y1: mt + ih, y2: mt + ih,
    stroke: "var(--line)", "stroke-width": 1 }));

  if (rightLine) {
    const pts = D.days.map((d, i) => [i, t.vd[i]]).filter(q => q[1] !== null && q[1] !== undefined);
    if (pts.length > 1) {
      const maxV = Math.max(...pts.map(q => q[1]));
      const ry = v => mt + ih - (v / Math.max(maxV, 1)) * ih;
      const d = pts.map((q, i) => `${i ? "L" : "M"}${(ml + q[0] * cw + cw / 2).toFixed(1)},${ry(q[1]).toFixed(1)}`).join("");
      svg.appendChild(el("path", { d, fill: "none", stroke: "var(--muted)", "stroke-width": 1.6,
        "stroke-dasharray": "3 4", "stroke-linejoin": "round" }));
      const lab = el("text", { x: ml + iw + 9, y: ry(maxV) + 4, fill: "var(--muted)",
        "font-size": 10, "font-family": "IBM Plex Mono, monospace" });
      lab.textContent = "v" + maxV; svg.appendChild(lab);
    }
  }
  return svg;
}

function openDetail(t) {
  const live = t.l === D.days.at(-1);
  const drift = (t.rt && t.s0) ? Math.round(t.rt - t.s0) : null;
  const shipDays = t.sd;
  dlgBody.replaceChildren();

  const head = document.createElement("div");
  head.className = "dlg-head";
  head.innerHTML = `<div>
      <h3>${escapeHtml(t.n || "unnamed")}</h3>
      <div class="who">${escapeHtml((t.mem || []).join(" · ")) || "no members listed"}</div>
      <div class="tags">
        <span class="pill">${t.rk ? "rank " + t.rk : "unranked"}</span>
        ${t.reg ? `<span class="pill">${escapeHtml(t.reg)}</span>` : ""}
        ${t.st ? `<span class="pill">${escapeHtml(t.st)}</span>` : ""}
        <span class="pill ${live ? "live" : "gone"}">${live ? "played today" : "last seen " + t.l}</span>
      </div></div>
    <button class="close" type="button" autofocus>Close ✕</button>`;
  head.querySelector(".close").addEventListener("click", () => dlg.close());
  dlgBody.appendChild(head);

  const stats = document.createElement("div");
  stats.className = "stats";
  stats.innerHTML = [
    [t.rt ? Math.round(t.rt) : "—", "rating now"],
    [t.pk ? Math.round(t.pk) : "—", "peak"],
    [drift === null ? "—" : (drift > 0 ? "+" : "") + drift, "since first match"],
    [t.v, "versions shipped"],
    [t.vr.toFixed(1), "versions per day"],
    [shipDays + "/" + t.ad, "days shipped"],
    [t.vmax ?? "—", "highest version"],
    [t.w === null ? "—" : (t.w * 100).toFixed(1) + "%", "win rate"],
  ].map(([b, s]) => `<div><b>${b}</b><span>${s}</span></div>`).join("");
  dlgBody.appendChild(stats);

  const p1 = document.createElement("div");
  p1.className = "panel";
  p1.innerHTML = `<h4>Rating through the log &middot; copper bands mark release days</h4>`;
  p1.appendChild(bigChart(t));
  dlgBody.appendChild(p1);

  const p2 = document.createElement("div");
  p2.className = "panel";
  p2.innerHTML = `<h4>Version changes per day &middot; dashed line is the version number reached</h4>`;
  p2.appendChild(dayBars(t, t.u, "var(--alt)", "new versions", true));
  const cadence = document.createElement("p");
  cadence.className = "note";
  cadence.textContent = t.v > 1
    ? `${t.v} distinct versions over ${t.ad} active days — about `
      + `${(t.v / Math.max(t.ad, 1)).toFixed(1)} a day, shipped on ${shipDays} of them.`
    : "Only one version ever seen on the ladder.";
  p2.appendChild(cadence);
  dlgBody.appendChild(p2);

  if (t.so || t.sr) {
    const ps = document.createElement("div");
    ps.className = "panel";
    ps.innerHTML = `<h4>Sparring it ordered</h4>`;
    const line = document.createElement("p");
    line.className = "note";
    line.textContent = t.so
      ? `Ordered ${fmt(t.so)} unrated matches; was itself pulled into ${fmt(t.sr)} ordered by others.`
      : `Never ordered an attributable unrated match; was pulled into ${fmt(t.sr)} ordered by others.`;
    ps.appendChild(line);
    if (t.so) ps.appendChild(dayBars(t, t.ob, "var(--accent)", "matches ordered", false));
    if ((t.ot || []).length) {
      const g = document.createElement("div");
      g.className = "opps";
      g.innerHTML = t.ot.map(o => `<div class="opp">
        <span class="on" title="${escapeHtml(o.name)}">${escapeHtml(o.name)}</span>
        <span class="om">${fmt(o.games)}</span><span class="ow"></span></div>`).join("");
      ps.appendChild(g);
    }
    dlgBody.appendChild(ps);
  }

  const p3 = document.createElement("div");
  p3.className = "panel";
  p3.innerHTML = `<h4>Opponents met most</h4>`;
  const grid = document.createElement("div");
  grid.className = "opps";
  grid.innerHTML = (t.op || []).map(o => {
    const decided = o.wins + o.losses;
    const rate = decided ? o.wins / decided : null;
    const cls = rate === null ? "" : rate >= 0.55 ? "win-hi" : rate <= 0.45 ? "win-lo" : "";
    return `<div class="opp">
      <span class="on" title="${escapeHtml(o.name)}">${escapeHtml(o.name)}</span>
      <span class="om">${o.wins}–${o.losses}</span>
      <span class="ow ${cls}">${rate === null ? "—" : (rate * 100).toFixed(0) + "%"}</span>
    </div>`;
  }).join("") || `<span class="note">no opponents recorded</span>`;
  p3.appendChild(grid);
  dlgBody.appendChild(p3);

  dlg.showModal();
}
dlg.addEventListener("click", e => { if (e.target === dlg) dlg.close(); });

document.getElementById("prov").textContent =
  `Source: the platform's unfiltered /api/matches log, walked to its end — `
  + `${fmt(D.totals.matches)} complete matches, of which ${fmt(D.totals.unrated)} were unrated. `
  + `Versions come from the version each side ran in each match, the only league-wide record of `
  + `what teams shipped, so a version nobody ever played is invisible here.`;
</script>
"""

if __name__ == "__main__":
    raise SystemExit(main())
