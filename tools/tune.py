"""Sequential-Halving parameter search over the bot's LIVE constants.

WHY SEQUENTIAL HALVING AND NOT CMA-ES OR HILL CLIMBING
------------------------------------------------------
Fitness here is EXACT, not noisy: the engine is fully deterministic (seeds 1-5 and 999 give
bit-identical winner, turns and titanium), so re-running a candidate can never tell you anything
new. What varies is not the measurement but the INSTANCE SET -- which opponents on which maps.

The pilot measured what that costs. Over 20 candidates, train-to-holdout correlation is r = +0.725
overall but **r = +0.034 once you restrict to |train delta| <= 5 games**, i.e. the apparent
correlation is carried entirely by candidates that broke a subsystem outright. And combining the
four best training knobs -- exactly what greedy coordinate ascent does -- scored -2/264, WORSE than
the baseline it started from.

So the right tool is not a smarter optimiser over a small instance set. It is spending the budget on
INSTANCES: start every candidate on a cheap set, and give the survivors more games rather than
giving everyone more games. That is Sequential Halving (Karnin et al. 2013) with the arms being
parameter vectors and the "pulls" being instances.

Two rules the pilot bought and this encodes:
  * `--rollouts 1` equivalent: never replay an instance, it is deterministic (Rares' TORCS team
    proved the same thing independently -- 16/16 laps at 0.000s spread).
  * The HOLDOUT is the selection criterion, not a post-hoc report. Opponents and maps are split, and
    the final round scores on ground the search never optimised against.

Usage:
  python tools/tune.py --candidates 64 --seed 1 --workers 8 [--quick]
"""

import argparse
import itertools
import os
import pathlib
import random
import re
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
CAND = ROOT / "bots" / "cand"

# The 14 constants the screen proved LIVE -- the other 22 provably never move the win count on a
# decided game, because the median game is 66 turns and most of the policy never executes.
# (file, name, low, high) inclusive integer ranges.
SPACE = [
    ("siege", "STANDOFF_PENALTY", 0, 6),
    ("siege", "EXPOSURE_PENALTY", 0, 4),
    ("siege", "MAX_BATTERY", 2, 8),
    ("main", "VAULT_MIN_GAP", 3, 9),
    ("main", "VAULT_GAIN", 2, 7),
    ("main", "VAULT_MAX", 1, 5),
    ("main", "VAULT_PATIENCE", 1, 6),
    ("main", "ATTACKERS", 2, 4),
    ("main", "BUILDERS", 2, 5),
    ("main", "AMMO_TARGET", 60, 200),
    ("main", "ALARM_PERCENT", 70, 96),
    ("main", "BATTERY_EVERY", 1, 6),
    ("main", "BATTERY_RESERVE", 0, 60),
    ("main", "REPLAN_TILES", 8, 48),
]

INCUMBENT = {
    "STANDOFF_PENALTY": 0, "EXPOSURE_PENALTY": 1, "MAX_BATTERY": 6,
    "VAULT_MIN_GAP": 5, "VAULT_GAIN": 4, "VAULT_MAX": 3, "VAULT_PATIENCE": 3,
    "ATTACKERS": 3, "BUILDERS": 3, "AMMO_TARGET": 120, "ALARM_PERCENT": 88,
    "BATTERY_EVERY": 3, "BATTERY_RESERVE": 20, "REPLAN_TILES": 24,
}

# Opponents and maps are SPLIT. The search only ever sees the TRAIN side; the final round scores on
# HOLD, which it has never optimised against. Six of nine opponents unseen in selection was what
# made the pilot's +50 credible, so it is enforced here rather than hoped for.
TRAIN_OPP = ["vanguard", "tempest_fast", "mistral"]
HOLD_OPP = ["undertow", "jonbot", "mistral_fast", "tempest_ferry", "frontier", "luc1"]

ALL_KNOWN = sorted(p.stem for p in (ROOT / "maps").glob("*.map26"))
ALL_GEN = sorted(p.stem for p in (ROOT / "maps" / "generated").glob("*.map26"))
TRAIN_MAPS = ALL_KNOWN[::2]                       # every other published map
HOLD_MAPS = [m for m in ALL_KNOWN if m not in TRAIN_MAPS] + ALL_GEN


def mapfile(name):
    p = ROOT / "maps" / f"{name}.map26"
    return p if p.is_file() else ROOT / "maps" / "generated" / f"{name}.map26"


def instances(opps, maps):
    return [(o, m, s) for o, m, s in itertools.product(opps, maps, ("A", "B"))]


def write_candidate(vec, tag):
    """Materialise a bot directory with `vec` substituted for the live constants."""
    d = CAND / tag
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for f in ("main.py", "siege.py", "atlas.py"):
        shutil.copy(ROOT / "bot" / f, d / f)
    for which, name, _lo, _hi in SPACE:
        f = d / ("siege.py" if which == "siege" else "main.py")
        t = f.read_text(encoding="utf8")
        new, n = re.subn(r"^%s = -?\d+" % re.escape(name), "%s = %d" % (name, vec[name]),
                         t, count=1, flags=re.M)
        if n != 1:
            raise SystemExit("could not substitute %s in %s" % (name, f))
        f.write_text(new, encoding="utf8")
    return d


def play(args):
    botdir, opp, mp, side = args
    a = str(botdir / "main.py")
    b = str(ROOT / "bots" / "rivals" / opp / "main.py")
    x, y = (a, b) if side == "A" else (b, a)
    try:
        r = run_game(x, y, ENGINE, str(mapfile(mp)), os.devnull, 1, 0)
    except Exception:
        return 0
    return int((r["winner"] == "A") if side == "A" else (r["winner"] == "B"))


def score(botdir, inst, pool):
    jobs = [(botdir, o, m, s) for o, m, s in inst]
    return sum(pool.map(play, jobs, chunksize=4))


def sample(rng):
    return {name: rng.randint(lo, hi) for _which, name, lo, hi in SPACE}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", type=int, default=64)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    # The incumbent is always arm 0. A search that cannot beat the thing it started from should say
    # so out loud rather than return its own best random draw.
    vecs = [dict(INCUMBENT)] + [sample(rng) for _ in range(a.candidates - 1)]
    tags = ["t%03d" % i for i in range(len(vecs))]
    dirs = [write_candidate(v, t) for v, t in zip(vecs, tags)]

    tmaps = TRAIN_MAPS[:4] if a.quick else TRAIN_MAPS
    rounds = []
    n = len(vecs)
    opps = 1
    while n > 1:
        rounds.append((n, min(opps, len(TRAIN_OPP))))
        n = (n + 1) // 2
        opps += 1

    alive = list(range(len(vecs)))
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for rnd, (keep_from, nopp) in enumerate(rounds):
            inst = instances(TRAIN_OPP[:nopp], tmaps)
            scores = []
            for i in alive:
                s = score(dirs[i], inst, pool)
                scores.append((s, i))
            scores.sort(reverse=True)
            keep = max(1, len(alive) // 2)
            print("round %d: %d arms x %d games   best=%d/%d (arm %s)   %.0fs"
                  % (rnd, len(alive), len(inst), scores[0][0], len(inst),
                     tags[scores[0][1]], time.time() - t0), flush=True)
            for s, i in scores[:5]:
                print("    %-6s %3d/%-3d %s" % (tags[i], s, len(inst),
                      " ".join("%s=%d" % (k, vecs[i][k]) for k in sorted(vecs[i]))), flush=True)
            alive = [i for _s, i in scores[:keep]]

        win = alive[0]
        hold = instances(HOLD_OPP, HOLD_MAPS)
        print("\nHOLDOUT: %d games, %d opponents x %d maps -- never used in selection"
              % (len(hold), len(HOLD_OPP), len(HOLD_MAPS)), flush=True)
        hw = score(dirs[win], hold, pool)
        bw = score(dirs[0], hold, pool)
        print("  incumbent %d/%d" % (bw, len(hold)), flush=True)
        print("  winner    %d/%d   %s" % (hw, len(hold), tags[win]), flush=True)
        print("  delta     %+d" % (hw - bw), flush=True)
        print("  params    %s" % " ".join("%s=%d" % (k, vecs[win][k])
                                          for k in sorted(vecs[win])), flush=True)


if __name__ == "__main__":
    main()


# RESULT OF THE FIRST FULL CAMPAIGN (64 candidates, seed 7, 2026-08-03)
# ---------------------------------------------------------------------
#   round 0: 64 arms x 22 games   best 20/22   (incumbent TIED for first)
#   round 1: 32 arms x 44 games   best 39/44   (incumbent)
#   round 2: 16 arms x 66 games   best 58/66   (incumbent)
#   round 3:  8 arms x 66 games   best 58/66   (incumbent)
#   round 4:  4 arms x 66 games   best 58/66   (incumbent)
#   round 5:  2 arms x 66 games   best 58/66   (incumbent)
#   HOLDOUT 408 games, 6 opponents x 34 maps never used in selection:
#       incumbent 337/408    winner 337/408    delta +0
#
# THE INCUMBENT WON OUTRIGHT. It led from round 1 and was never displaced, and 63 random draws
# across the full 14-dimensional live space produced nothing better over ~5,600 games.
#
# That is the pre-registered stopping signal. The evolutionary pilot named its own falsification
# condition -- "an 8-hour campaign over the 14 live dimensions returning less than +10/810 beyond
# SP0+VMG5" -- and this returns +0. Constant tuning is DONE; the two big wins (STANDOFF_PENALTY 6->0,
# VAULT_MIN_GAP 9->5) were the headroom, and there is no more of it at this granularity.
#
# Do not re-run this with a different seed hoping for a better draw. The remaining headroom is not in
# the VALUES of siege.rank's coefficients, it is in the FORM of its scoring function -- currently
# three terms, `approach + STANDOFF_PENALTY*(k-1) + EXPOSURE_PENALTY*exp`, two of whose coefficients
# this search has now confirmed optimal. Widening that to 6-10 features is the next lever.
#
# Useful by-product: 337/408 = 82.6% is a clean unbiased strength estimate on ground never used for
# any tuning decision.
