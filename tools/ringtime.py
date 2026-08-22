"""How fast does the ring go up? The one number these races turn on.

Measured against the faithful clone, our wins and losses are separated by one or two volleys:
helheim lost at turn 35 with their Core on 26 HP, longhouse won with theirs on 2. So the question
is not whether the plan is right, it is how many rounds pass between the first turret and the
fourth. A Sentinel placed is 9 HP/round that was not firing before.

Placing four turrets should cost four rounds -- build, build, build, build -- if the Builder stands
where all four neighbours can shoot the Core. Every round beyond that is a step it had to take
because the anchor it chose only had one or two usable sides.

Usage: python tools/ringtime.py [bot] [opponent]
"""

import os
import pathlib
import shutil
import sys

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import fcode                                    # noqa: E402
from fcode.fcode_engine import run_game         # noqa: E402
from diag.replay import load_replay             # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
MAPS = sorted(p.stem for p in (ROOT / "maps").glob("*.map26"))


def scrub():
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" not in pc.parts:
            shutil.rmtree(pc, ignore_errors=True)


def main():
    bot = sys.argv[1] if len(sys.argv) > 1 else "bots/elias/rush"
    foe = sys.argv[2] if len(sys.argv) > 2 else "bots/zoo/idle"
    scrub()
    out = ROOT / "replays" / "ringtime.replay26"
    out.parent.mkdir(parents=True, exist_ok=True)
    spans, firsts, lasts, wins = [], [], [], 0
    print("%-14s %6s %6s %6s %6s  %s" % ("map", "first", "last", "span", "turns", "result"))
    for m in MAPS:
        res = run_game(str(ROOT / bot / "main.py"), str(ROOT / foe / "main.py"), ENGINE,
                       str(ROOT / "maps" / (m + ".map26")), str(out), 1, 0)
        r = load_replay(str(out))
        ring = []
        for t, st, ta in r.iter_states():
            for e in ta.placed:
                if e.team == "a" and e.kind == "sentinel":
                    ring.append(t)
        won = res["winner"] == "A"
        wins += won
        # Only games that actually completed a ring are comparable. Taking ring[min(3, len-1)]
        # called the LAST turret the fourth, so paths -- which built two -- reported "span 3" and
        # sat at the top of the table as the best row in it. A partial ring is not a fast ring.
        if len(ring) >= 4:
            span = ring[3] - ring[0]
            spans.append(span)
            firsts.append(ring[0])
            lasts.append(ring[3])
        else:
            span = None
        print("%-14s %6s %6s %6s %6s  %s (%d turrets)%s" % (
            m, ring[0] if ring else "-", ring[3] if len(ring) >= 4 else "-",
            span if span is not None else "-", res["turns"],
            "WIN" if won else "loss", len(ring),
            "" if len(ring) >= 4 else "  <- PARTIAL, excluded"))
    scrub()
    if spans:
        spans.sort()
        print()
        print("first turret : mean %.1f" % (sum(firsts) / len(firsts)))
        print("ring done    : mean %.1f" % (sum(lasts) / len(lasts)))
        print("SPAN 1st->4th: mean %.2f  median %d  worst %d   MEASURED %d/%d games"
              % (sum(spans) / len(spans), spans[len(spans) // 2], spans[-1], len(spans), len(MAPS)))
        print("               (4 builds and no steps would be 3; games with <4 turrets excluded)")
    print("wins %d/%d" % (wins, len(MAPS)))


main()
