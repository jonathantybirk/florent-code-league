"""Win count over the 8-opponent panel, both seats, 15 maps -- 240 games.

The engine is deterministic and we pass turn_timeout_ms=0, so this is a CENSUS, not a sample: two
runs of the same pair of bots differ only by a nameable set of flipped maps. A total that moves by
less than about 4 is cascade shuffle rather than skill, so a candidate has to clear that to ship.

Also prints how each game was DECIDED. Most of our losses are not fights -- they are round-1000
tiebreaks resolved on titanium_collected > harvesters > titanium_stored, and a bot that converts
its whole treasury into ammunition forfeits the last of those keys by construction.

Usage: python tools/panel.py <bot> [--opps a,b,c]
"""
import collections
import os
import pathlib
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

OPPS = ["bots/zoo/miner", "bots/zoo/adgato", "bots/nash/flagship", "bots/rivals/vigil",
        "bots/rivals/vanguard", "bots/zoo/starter_fixed", "bots/zoo/turtle", "bots/zoo/idle"]
POOL = ["auroraveil", "bifrost", "fimbulwinter", "glacierkeep", "helheim", "holmgang", "icefloe",
        "jotunheim", "longhouse", "midgard", "paths", "skald", "stavkirke", "valkyrie",
        "yggdrasil"]


def job(a):
    bot, opp, m, seat, mapdir = a
    import fcode
    from fcode.fcode_engine import run_game
    engine = str(pathlib.Path(fcode.__file__).resolve().parent)
    x, y = (bot, opp) if seat == 0 else (opp, bot)
    try:
        r = run_game(str(ROOT / x / "main.py"), str(ROOT / y / "main.py"), engine,
                     str(ROOT / mapdir / (m + ".map26")), os.devnull, 1, 0)
    except Exception as exc:
        return (opp, m, seat, False, "error:" + str(exc)[:40], 0, 0, 0)
    won = (r["winner"] == "A") == (seat == 0)
    ours = r["a_titanium"] if seat == 0 else r["b_titanium"]
    coll = r["a_titanium_collected"] if seat == 0 else r["b_titanium_collected"]
    return (opp, m, seat, won, r.get("win_condition") or "-", ours, coll, r["turns"])


def main():
    bot = sys.argv[1]
    opps = OPPS
    if "--opps" in sys.argv:
        opps = sys.argv[sys.argv.index("--opps") + 1].split(",")
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" not in pc.parts:
            shutil.rmtree(pc, ignore_errors=True)
    mapdir = "maps"
    pool = POOL
    if "--maps" in sys.argv:
        mapdir = sys.argv[sys.argv.index("--maps") + 1]
        # Out-of-sample terrain: `terrain.py` bundles only the live pool, so a map from here
        # exercises the discovered-terrain path the ladder would use after a rotation.
        pool = sorted(q.stem for q in (ROOT / mapdir).glob("*.map26"))
    jobs = [(bot, o, m, s, mapdir) for o in opps for m in pool for s in (0, 1)]
    with ProcessPoolExecutor(max_workers=10) as ex:
        rows = list(ex.map(job, jobs, chunksize=1))
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" not in pc.parts:
            shutil.rmtree(pc, ignore_errors=True)

    print("PANEL  %s" % bot)
    per = collections.Counter()
    tot_ti = collections.Counter()
    tot_coll = collections.Counter()
    how = collections.Counter()
    for opp, m, seat, won, cond, ti, coll, _t in rows:
        per[opp] += 1 if won else 0
        tot_ti[opp] += ti
        tot_coll[opp] += coll
        how[(cond, won)] += 1
    n = len(pool) * 2
    for o in opps:
        print("  %-22s wins %2d/%d   mean stored %5d   mean delivered %5d"
              % (o, per[o], n, tot_ti[o] / n, tot_coll[o] / n))
    print("  TOTAL %d/%d" % (sum(per.values()), len(rows)))
    print()
    print("  decided by:")
    for (c, w), k in sorted(how.items(), key=lambda kv: -kv[1]):
        print("    %-20s %-5s %3d" % (c, "win" if w else "loss", k))
    print()
    print("  LOSSES (the only rows worth reading twice):")
    for opp, m, seat, won, cond, ti, coll, turns in sorted(rows, key=lambda r: (r[4], r[7])):
        if not won:
            print("    %-22s %-13s seat %s  %-16s died r%-5d stored %5d"
                  % (opp, m, "AB"[seat], cond, turns, ti))


if __name__ == "__main__":
    main()
