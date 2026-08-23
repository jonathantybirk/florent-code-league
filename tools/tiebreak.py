"""What actually decides our 1000-round games?

`a_titanium_collected` is the documented PRIMARY tiebreak, and in fcode 2.3.9 it reads 0 for every
bot on every map -- including an economy bot that finishes with 39 buildings and six Builders. A key
that is always zero cannot break a tie, so the decision falls to the next key down. This prints the
engine's own `win_condition` for each game so the real order is observed rather than assumed.

Usage: python tools/tiebreak.py [bot] [opponent...]
"""
import os, pathlib, shutil, sys, collections
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fcode                                     # noqa: E402
from fcode.fcode_engine import run_game          # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
MAPS = sorted(p.stem for p in (ROOT / "maps").glob("*.map26"))

bot = sys.argv[1] if len(sys.argv) > 1 else "bots/elias/rush"
foes = sys.argv[2:] or ["bots/zoo/miner", "bots/zoo/adgato"]

print("TIEBREAK CENSUS  %s" % bot)
print("%-13s %-14s %-6s %5s %-12s %7s %7s" % ("map", "opponent", "res", "turn", "won_by", "our_Ti", "their"))
tally = collections.Counter()
for foe in foes:
    for m in MAPS:
        for seat in (0, 1):
            a = bot if seat == 0 else foe
            b = foe if seat == 0 else bot
            r = run_game(str(ROOT / a / "main.py"), str(ROOT / b / "main.py"), ENGINE,
                         str(ROOT / "maps" / (m + ".map26")), os.devnull, 1, 0)
            we_won = (r["winner"] == "A") == (seat == 0)
            ours = r["a_titanium"] if seat == 0 else r["b_titanium"]
            theirs = r["b_titanium"] if seat == 0 else r["a_titanium"]
            cond = r.get("win_condition") or "-"
            tally[(cond, we_won)] += 1
            if r["turns"] >= 1000:
                print("%-13s %-14s %-6s %5d %-12s %7s %7s" % (
                    m, foe.split("/")[-1], "WIN" if we_won else "loss",
                    r["turns"], cond, ours, theirs))
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" not in pc.parts:
            shutil.rmtree(pc, ignore_errors=True)

print()
print("HOW GAMES WERE DECIDED")
for (cond, won), n in sorted(tally.items(), key=lambda kv: -kv[1]):
    print("  %-14s %-5s %3d" % (cond, "win" if won else "loss", n))
w = sum(n for (c, won), n in tally.items() if won)
print("TOTAL %d/%d" % (w, sum(tally.values())))
