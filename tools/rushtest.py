"""Run the rusher across the pool, both seats, and report kill round."""
import os, pathlib, sys, shutil
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
MAPS = sorted(p.stem for p in (ROOT / "maps").glob("*.map26"))

def scrub():
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" in pc.parts:
            continue
        shutil.rmtree(pc, ignore_errors=True)

def path(bot):
    p = ROOT / bot
    return str(p / "main.py") if p.is_dir() else str(p)

def main():
    bot = sys.argv[1] if len(sys.argv) > 1 else "bots/elias/rush"
    foe = sys.argv[2] if len(sys.argv) > 2 else "bots/zoo/idle"
    only = sys.argv[3] if len(sys.argv) > 3 else None
    maps = [only] if only else MAPS
    scrub()
    wins = 0
    rounds = []
    print("%-14s %-6s %-9s %6s   %-6s %-9s %6s" % ("map", "A", "cond", "turns", "B", "cond", "turns"))
    for m in maps:
        row = [m]
        for seat in (0, 1):
            a, b = (bot, foe) if seat == 0 else (foe, bot)
            r = run_game(path(a), path(b), ENGINE, str(ROOT / "maps" / (m + ".map26")),
                         os.devnull, 1, 0)
            us = "A" if seat == 0 else "B"
            won = r["winner"] == us
            wins += won
            if won and r["win_condition"] == "core_destroyed":
                rounds.append(r["turns"])
            row += ["WIN" if won else "loss", str(r["win_condition"])[:9], r["turns"]]
        print("%-14s %-6s %-9s %6s   %-6s %-9s %6s" % tuple(row))
    scrub()
    n = len(maps) * 2
    print()
    print("wins %d/%d" % (wins, n))
    if rounds:
        rounds.sort()
        print("core kills: %d, rounds min=%d median=%d max=%d" % (
            len(rounds), rounds[0], rounds[len(rounds) // 2], rounds[-1]))

main()
