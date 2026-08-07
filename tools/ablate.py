"""One change at a time, scored against the opponents a competitive ladder actually samples.

The failure this exists to prevent: a change is measured only against the bot it was
derived from, wins, and ships. That number is nearly worthless on its own -- a mirror
match rewards anything that exploits the baseline's own habits, which is precisely what
will not transfer.

WHY NASH-WEIGHTED AND NOT "MUST NOT REGRESS ANYWHERE"
-----------------------------------------------------
The first version of this gate rejected any variant that lost a single game to any panel
bot. That is the wrong objective: it selects for a bot that is better than ALL, when what
wins a ladder is a bot that is better than MOST, against the opponents that actually get
played.

The internal tournament already answers "which strategies does a rational opponent field"
-- that is exactly what a Nash equilibrium over the payoff matrix is. Measured over 3360
games per bot, the support is:

    steward 0.523   vigil 0.199   heimdall 0.193   odin 0.085   prospect_rushonly 0.000

So beating steward matters roughly five times as much as beating odin, and
prospect_rushonly -- a pure rusher outside the equilibrium -- barely matters at all. Two
of the four ablations in the first sweep gained 5-7 games against vigil and lost 2-3 to
prospect_rushonly, and the unweighted gate rejected both. Under the weighting the ladder
actually uses, those are clear wins.

Weights are `(1 - ALPHA) * nash + ALPHA * uniform`. The uniform floor is deliberate and
small: a strategy outside the current equilibrium is not worthless evidence, because the
equilibrium moves when opponents adapt and a bot that collapses to a pure rush has a real
hole. It just should not hold a veto.

There is still a hard guard, because "competitive on average" must not mean "fragile":
any single opponent falling by more than CLIFF games fails regardless of the weighted
score. That catches trading a catastrophe for an average.

The engine is deterministic, so a difference between two runs is never noise -- it is
always a nameable set of flipped maps, which `--per-map` prints.

Usage:
  python tools/ablate.py --variants bots/cand/wary_cost,bots/cand/ore_deny_preempt
  python tools/ablate.py --variants ... --per-map
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from arena import POOL, ROOT, play, resolve_bot  # noqa: E402

# The panel: the Nash support, plus one strong bot outside it so a hole against a pure
# rush still shows up.
PANEL = ["steward", "vigil", "heimdall", "odin", "prospect_rushonly"]

# How much uniform smoothing to mix into the Nash weights. 0.0 trusts the equilibrium
# completely and lets a variant ignore anything outside it; 1.0 is the old flat gate.
ALPHA = 0.25

# A single opponent may not fall by more than this many games however good the weighted
# score is. Average competitiveness must not be bought with a collapse.
CLIFF = 5

NASH_CSV = ROOT / "tournament" / "nash-weights.csv"


def nash_weights(panel: list[str]) -> dict[str, float]:
    """Nash probability per panel bot, smoothed toward uniform and normalised.

    Read from the tournament export rather than hardcoded, so a fresh run changes the
    gate without a code edit. Falls back to uniform if the export is missing, which is
    the safe direction: it degrades to the old flat gate rather than silently weighting
    on stale numbers.
    """
    raw = {name: 0.0 for name in panel}
    try:
        for row in csv.DictReader(NASH_CSV.open()):
            if row["name"] in raw:
                raw[row["name"]] += float(row["nash_prob"])
    except (OSError, KeyError, ValueError):
        return {name: 1.0 / len(panel) for name in panel}

    total = sum(raw.values())
    if total <= 0:
        return {name: 1.0 / len(panel) for name in panel}
    uniform = 1.0 / len(panel)
    return {name: (1 - ALPHA) * (raw[name] / total) + ALPHA * uniform for name in panel}


def run(cand: str, opp: str, maps: list[str], pool) -> list[dict]:
    jobs = [(cand, opp, m, s, None) for m in maps for s in ("A", "B")]
    return list(pool.map(play, jobs, chunksize=2))


def summarise(rows: list[dict]) -> tuple[int, int, int]:
    w = sum(1 for r in rows if r.get("won"))
    mine = sum(r.get("mine", 0) for r in rows)
    theirs = sum(r.get("theirs", 0) for r in rows)
    return w, len(rows) - w, mine - theirs


def weighted_score(records: dict[str, tuple[int, int, int]], w: dict[str, float]) -> float:
    """Nash-weighted win rate across the panel."""
    total = sum(w.get(name, 0.0) for name in records)
    if total <= 0:
        return 0.0
    return sum(w.get(name, 0.0) * (won / max(won + lost, 1))
               for name, (won, lost, _m) in records.items()) / total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="bots/nash/steward")
    ap.add_argument("--variants", required=True, help="comma-separated bot dirs or names")
    ap.add_argument("--panel", default=",".join(PANEL))
    ap.add_argument("--maps", default="pool")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--per-map", action="store_true", help="name the maps that flipped")
    a = ap.parse_args()

    base = resolve_bot(a.base)
    panel = [(n, resolve_bot(n)) for n in a.panel.split(",") if n]
    variants = [(v, resolve_bot(v)) for v in a.variants.split(",") if v]
    maps = POOL if a.maps == "pool" else sorted(
        p.stem for p in (ROOT / "maps" / "generated").glob("*.map26"))
    w = nash_weights([n for n, _ in panel])

    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        base_ref: dict[str, tuple[int, int, int]] = {}
        for name, path in panel:
            # The base against itself is the mirror; a bot beats its own copy ~50% and
            # that is the right reference for "did the change help".
            base_ref[name] = summarise(run(base, path, maps, pool))
        base_score = weighted_score(base_ref, w)

        print(f"\nbase: {a.base}   ({len(maps)} maps x 2 sides = {len(maps)*2} per cell)")
        print(f"{'opponent':<22}{'weight':<9}{'baseline':<11}{'Ti margin'}")
        for name, _p in panel:
            won, lost, m = base_ref[name]
            print(f"  {name:<20}{w.get(name, 0):<9.3f}{f'{won}-{lost}':<11}{m:+}")
        print(f"  {'NASH-WEIGHTED':<20}{'':<9}{base_score:.3f}")

        for vname, vpath in variants:
            print(f"\n{'='*78}\n{vname}\n{'='*78}")
            rec: dict[str, tuple[int, int, int]] = {}
            worst_name, worst_delta = None, 0
            for name, path in panel:
                rec[name] = summarise(run(vpath, path, maps, pool))
                won, lost, m = rec[name]
                bw = base_ref[name][0]
                d = won - bw
                if d < worst_delta:
                    worst_name, worst_delta = name, d
                flag = "  <- CLIFF" if d <= -CLIFF else ""
                print(f"  {name:<20}{w.get(name, 0):<9.3f}{f'{won}-{lost}':<11}"
                      f"{m:+8}   {d:+d} vs base{flag}")
            score = weighted_score(rec, w)
            gain = score - base_score
            cliff = worst_delta <= -CLIFF
            ok = gain > 0 and not cliff
            print(f"  {'NASH-WEIGHTED':<20}{'':<9}{score:.3f}      {gain:+.3f} vs base")
            reason = ""
            if not ok:
                reason = (f"  (cliff: {worst_name} {worst_delta:+d})" if cliff
                          else "  (no weighted gain)")
            print(f"  -> {'SHIPPABLE' if ok else 'REJECTED'}{reason}")

            if a.per_map:
                bwin = {(r["map"], r["side"]) for r in run(base, base, maps, pool) if r.get("won")}
                mrows = run(vpath, base, maps, pool)
                flips = [r for r in mrows if r.get("won") != ((r["map"], r["side"]) in bwin)]
                for r in sorted(flips, key=lambda r: r["map"]):
                    print(f"    {r['map']:<13}{r['side']}  {'W' if r.get('won') else 'L'}  "
                          f"{r.get('cond','?'):<18}t{r.get('turns','?')}")


if __name__ == "__main__":
    main()
