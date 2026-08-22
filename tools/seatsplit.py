"""Same sweep as rushtest, but reported per SEAT.

Team A's Core is spawned first and every unit acts in spawn order, so in a race that both sides
would finish on the same round, A fires first and wins. For a rush that is not a detail.
"""
import os, pathlib, shutil, sys
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
MAPS = sorted(p.stem for p in (ROOT / "maps").glob("*.map26"))


def scrub():
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" not in pc.parts:
            shutil.rmtree(pc, ignore_errors=True)


def path(bot):
    p = ROOT / bot
    return str(p / "main.py") if p.is_dir() else str(p)


def main():
    us, foe = sys.argv[1], sys.argv[2]
    scrub()
    win = {0: 0, 1: 0}
    turns = {0: [], 1: []}
    for m in MAPS:
        for seat in (0, 1):
            a, b = (us, foe) if seat == 0 else (foe, us)
            r = run_game(path(a), path(b), ENGINE, str(ROOT / "maps" / (m + ".map26")),
                         os.devnull, 1, 0)
            ours = "A" if seat == 0 else "B"
            if r["winner"] == ours:
                win[seat] += 1
                turns[seat].append(r["turns"])
    scrub()
    n = len(MAPS)
    print("%s  vs  %s" % (us, foe))
    for seat, name in ((0, "as A (acts first)"), (1, "as B (acts second)")):
        t = sorted(turns[seat])
        med = t[len(t) // 2] if t else 0
        print("  %-20s %2d/%2d  (%.0f%%)   median win at round %s" % (
            name, win[seat], n, 100.0 * win[seat] / n, med or "-"))
    print("  %-20s %2d/%2d  (%.0f%%)" % ("total", win[0] + win[1], 2 * n,
                                         100.0 * (win[0] + win[1]) / (2 * n)))


main()
