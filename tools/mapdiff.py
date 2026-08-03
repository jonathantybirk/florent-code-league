"""Per-map diff of two bots against the same opponent.

The engine is deterministic -- seeds 1..5 give bit-identical winner, win_condition and turn count --
so a sweep difference is never sampling noise. It is always a specific set of maps that flipped, and
those maps are nameable. This prints them.

Usage: python tools/mapdiff.py <botA> <botB> <opponent> [--unseen]
"""
import os, pathlib, sys
import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)


def resolve(b):
    p = ROOT / b
    return str(p / "main.py") if p.is_dir() else str(p)


def sweep(bot, opp, maps):
    res = {}
    for mp in maps:
        for side in ("A", "B"):
            x, y = (bot, opp) if side == "A" else (opp, bot)
            r = run_game(resolve(x), resolve(y), ENGINE, str(mp), os.devnull, 1, 0)
            won = (r["winner"] == "A") if side == "A" else (r["winner"] == "B")
            res[(mp.stem, side)] = (won, r["win_condition"], r["turns"])
    return res


def main():
    a, b, opp = sys.argv[1], sys.argv[2], sys.argv[3]
    unseen = "--unseen" in sys.argv
    d = ROOT / "maps" / "generated" if unseen else ROOT / "maps"
    maps = sorted(d.glob("*.map26"))
    ra, rb = sweep(a, opp, maps), sweep(b, opp, maps)
    wa = sum(1 for v in ra.values() if v[0])
    wb = sum(1 for v in rb.values() if v[0])
    print("\n%s %d-%d   vs   %s %d-%d   (opponent %s)"
          % (a, wa, len(ra) - wa, b, wb, len(rb) - wb, opp))
    print("\n%-34s %-26s %s" % ("map/side", a.split('/')[-1], b.split('/')[-1]))
    for k in sorted(ra):
        if ra[k][0] != rb[k][0]:
            f = lambda v: "%s %s t%d" % ("W" if v[0] else "L", v[1][:12], v[2])
            print("%-34s %-26s %s" % ("%s/%s" % k, f(ra[k]), f(rb[k])))


if __name__ == "__main__":
    main()
