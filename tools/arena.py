"""Evaluate a candidate against the Nash panel on the current map pool, with diagnostics.

The panel is the five entries with non-zero Nash probability in the team's latest tournament run --
the set a Nash-averaging ladder actually samples from. They are BLACK BOXES: their source is never
read to counter them.

Two things this reports that a win count does not:

  * DELIVERED TITANIUM DIFFERENTIAL. `titanium_collected` is the top rung of the tiebreak ladder,
    and ladder Elo consumes the FRACTIONAL series score, so margin is the metric, not just wins.
  * DIAGNOSTICS COUNTS. A change can leave the score flat while making behaviour worse; idle rounds
    and silent turrets surface that before it compounds.

The engine is deterministic -- seeds give bit-identical results -- so every game is played once and
a difference between two runs is always a nameable set of flipped maps, never noise.

Usage:
  python tools/arena.py <candidate> [--panel a,b] [--maps pool|generated] [--diag] [--replays DIR]
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor

import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)

PANEL = ["steward", "vigil", "heimdall", "odin", "prospect_rushonly"]

# The 15-map competition pool as synced on 2026-08-04. Kept explicit rather than globbed so a stale
# map left in maps/ cannot silently join the evaluation.
POOL = ["antler", "archipelago", "atoll", "drumlin", "eider", "fjordgate", "heart", "hive",
        "jackpot", "lighthouse", "meander", "moonrise", "nordkap", "saga", "snowflake"]


def resolve_bot(name: str) -> str:
    p = pathlib.Path(name)
    if p.is_dir():
        return str(p / "main.py")
    if p.is_file():
        return str(p)
    for base in ("bots/nash", "bots/cand", "bots/rivals", "bots/elias/unfair", "bots"):
        d = ROOT / base / name
        if (d / "main.py").is_file():
            return str(d / "main.py")
    raise SystemExit(f"bot not found: {name}")


def mapfile(name: str) -> str:
    p = ROOT / "maps" / f"{name}.map26"
    if p.is_file():
        return str(p)
    g = ROOT / "maps" / "generated" / f"{name}.map26"
    if g.is_file():
        return str(g)
    raise SystemExit(f"map not found: {name}")


def play(job):
    cand, opp, mp, side, replay_dir = job
    x, y = (cand, opp) if side == "A" else (opp, cand)
    out = os.devnull
    if replay_dir:
        tag = f"{pathlib.Path(cand).parent.name}_vs_{pathlib.Path(opp).parent.name}_{mp}_{side}"
        out = str(pathlib.Path(replay_dir) / f"{tag}.replay26")
    try:
        r = run_game(x, y, ENGINE, mapfile(mp), out, 1, 0)
    except Exception as exc:
        return {"map": mp, "side": side, "opp": opp, "error": str(exc)[:80]}
    me, them = ("a", "b") if side == "A" else ("b", "a")
    return {
        "map": mp, "side": side, "opp": opp, "replay": out if replay_dir else None,
        "won": (r["winner"] == "A") if side == "A" else (r["winner"] == "B"),
        "cond": r["win_condition"], "turns": r["turns"],
        "mine": r[f"{me}_titanium_collected"], "theirs": r[f"{them}_titanium_collected"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("--panel", default=",".join(PANEL))
    ap.add_argument("--maps", default="pool")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--diag", action="store_true", help="run behaviour detectors on every game")
    ap.add_argument("--replays", default=None, help="directory to keep replays in")
    a = ap.parse_args()

    cand = resolve_bot(a.candidate)
    panel = [(n, resolve_bot(n)) for n in a.panel.split(",") if n]
    maps = POOL if a.maps == "pool" else sorted(
        p.stem for p in (ROOT / "maps" / "generated").glob("*.map26"))

    replay_dir = a.replays or (str(ROOT / "replays" / "arena") if a.diag else None)
    if replay_dir:
        pathlib.Path(replay_dir).mkdir(parents=True, exist_ok=True)

    jobs = [(cand, path, m, s, replay_dir)
            for _n, path in panel for m in maps for s in ("A", "B")]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        rows = list(pool.map(play, jobs, chunksize=2))

    by_opp: dict[str, list] = {}
    for r in rows:
        by_opp.setdefault(pathlib.Path(r["opp"]).parent.name, []).append(r)

    print(f"\n{a.candidate}  vs the Nash panel   ({len(maps)} maps x 2 sides)\n")
    print(f"{'opponent':<20}{'record':<10}{'core kills':<12}{'Ti delivered (us/them)':<26}margin")
    tw = tl = 0
    for name, rs in by_opp.items():
        w = sum(1 for r in rs if r.get("won"))
        k = sum(1 for r in rs if r.get("won") and r.get("cond") == "core_destroyed")
        mine = sum(r.get("mine", 0) for r in rs)
        theirs = sum(r.get("theirs", 0) for r in rs)
        tw += w
        tl += len(rs) - w
        print(f"{name:<20}{f'{w}-{len(rs)-w}':<10}{k:<12}{f'{mine}/{theirs}':<26}{mine-theirs:+}")
    print(f"\n{'TOTAL':<20}{f'{tw}-{tl}':<10}{tw/(tw+tl):.1%}")

    losses = [r for r in rows if not r.get("won")]
    if losses:
        print(f"\n--- LOSSES ({len(losses)}) ---")
        for r in sorted(losses, key=lambda r: (r["opp"], r["map"])):
            print(f"  {pathlib.Path(r['opp']).parent.name:<20}{r['map']:<13}{r['side']}  "
                  f"{r.get('cond','?'):<20}t{r.get('turns','?'):<5}"
                  f"Ti {r.get('mine','?')}/{r.get('theirs','?')}")

    if a.diag:
        from diag.detect import analyse
        print("\n--- DIAGNOSTICS ---")
        totals: dict[str, int] = {}
        for r in rows:
            if not r.get("replay"):
                continue
            team = "a" if r["side"] == "A" else "b"
            try:
                rep = analyse(r["replay"], team)
            except Exception as exc:
                print(f"  {r['map']}/{r['side']}: decode failed {type(exc).__name__}: {exc}")
                continue
            for k, v in rep.counts.items():
                totals[k] = totals.get(k, 0) + v
        if totals:
            for k, v in sorted(totals.items(), key=lambda kv: -kv[1]):
                print(f"  {k:<18}{v}")
        else:
            print("  no findings")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    main()
