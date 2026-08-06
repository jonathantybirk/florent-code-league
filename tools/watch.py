"""Generate replays against the Nash panel and print the commands to watch them.

The review loop this supports: make a change, measure it with `tools/arena.py`, then WATCH the games
it changed. Numbers say whether a change won; only the visualiser says whether it won for the reason
you intended. Indicator overlays drawn by the bot (`ct.draw_indicator_dot` / `draw_indicator_line`)
render inside these replays, so a worker's state and objective are visible frame by frame.

Usage:
  python tools/watch.py <candidate> [--panel steward,vigil] [--maps atoll,hive] [--diag]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from arena import PANEL, POOL, ROOT, mapfile, play, resolve_bot  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("--panel", default=",".join(PANEL))
    ap.add_argument("--maps", default=",".join(POOL[:3]))
    ap.add_argument("--sides", default="A,B")
    ap.add_argument("--diag", action="store_true")
    ap.add_argument("--outdir", default=str(ROOT / "replays" / "watch"))
    a = ap.parse_args()

    cand = resolve_bot(a.candidate)
    out = pathlib.Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for name in a.panel.split(","):
        if not name:
            continue
        opp = resolve_bot(name)
        for m in a.maps.split(","):
            for s in a.sides.split(","):
                rows.append(play((cand, opp, m, s, str(out))))

    print(f"\n{'opponent':<20}{'map':<13}{'side':<6}{'result':<8}{'condition':<20}{'turns':<7}Ti us/them")
    for r in rows:
        if r.get("error"):
            print(f"  ERROR {r['map']}/{r['side']}: {r['error']}")
            continue
        opp = pathlib.Path(r["opp"]).parent.name
        print(f"{opp:<20}{r['map']:<13}{r['side']:<6}"
              f"{'WIN' if r['won'] else 'LOSS':<8}{r['cond']:<20}{r['turns']:<7}"
              f"{r['mine']}/{r['theirs']}")

    if a.diag:
        from diag.detect import analyse, route_audit
        print("\n--- per-game diagnostics ---")
        for r in rows:
            if not r.get("replay"):
                continue
            team = "a" if r["side"] == "A" else "b"
            rep = analyse(r["replay"], team)
            print(f"\n{pathlib.Path(r['opp']).parent.name} / {r['map']} / {r['side']}: "
                  f"{rep.summary_line()}")
            for f in rep.findings[:6]:
                print(f"    {f}")
            for f in route_audit(r["replay"], team)[:4]:
                print(f"    {f}")

    print("\n--- watch these ---")
    for r in rows:
        if r.get("replay"):
            print(f'  .venv/Scripts/fcode.exe watch "{r["replay"]}"')


if __name__ == "__main__":
    main()
