"""Play the baked rush plan against `idle` on every map, both sides, and compare the engine's
reported turn-of-death against the model's predicted kill_turn.

This is the falsification test for G16. A match that ends `core_destroyed` on exactly the predicted
turn confirms the timeline; anything else refutes it.
"""

import os
import pathlib
import shutil
import sys

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
ENGINE_ROOT = str(pathlib.Path(fcode.__file__).resolve().parent)

from _predicted import PREDICTED  # noqa: E402

RUSH = str(ROOT / "bots" / "probe_rush" / "main.py")
IDLE = str(ROOT / "bots" / "zoo" / "idle" / "main.py")


def scrub():
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" in pc.parts:
            continue
        shutil.rmtree(pc, ignore_errors=True)


def main():
    maps = sorted(p.stem for p in (ROOT / "maps").glob("*.map26"))
    only = sys.argv[1:] or maps
    scrub()
    print("%-10s %-2s %6s %6s %-16s %s" % ("map", "tm", "pred", "actual", "win_condition", "ok"))
    ok = bad = 0
    rows = []
    for name in only:
        for team in ("a", "b"):
            a, b = (RUSH, IDLE) if team == "a" else (IDLE, RUSH)
            res = run_game(a, b, ENGINE_ROOT, str(ROOT / "maps" / (name + ".map26")),
                           os.devnull, 1, 0)
            pred = PREDICTED.get((name, team))
            want_winner = "A" if team == "a" else "B"
            good = (res["win_condition"] == "core_destroyed"
                    and res["winner"] == want_winner and res["turns"] == pred)
            ok += good
            bad += not good
            rows.append((name, team, pred, res["turns"], res["win_condition"], good))
            print("%-10s %-2s %6s %6d %-16s %s"
                  % (name, team, pred, res["turns"], res["win_condition"], "OK" if good else "MISMATCH"))
    scrub()
    print("\nexact matches: %d / %d" % (ok, ok + bad))
    if bad:
        print("MISMATCHES:")
        for r in rows:
            if not r[5]:
                print("  %s/%s predicted %s got %s (%s)" % (r[0], r[1], r[2], r[3], r[4]))


main()
