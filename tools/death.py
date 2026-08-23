"""WHY we lose the games we lose: a build timeline for both teams, per losing game.

The panel says 15 of our remaining 18 losses are the opponent destroying our Core between round
26 and round 226, and that we die holding 150-356 titanium. That is a symptom, not a cause. The
question this answers is whether we are losing a RACE -- their ring lands before ours -- or being
beaten by something our rush has no answer to at all.

Per game it prints, for each team, the round each combat building went up and the round our own
Builder died, so "we lost the race by 9 rounds" and "they never built a turret and killed us with
bodies" stop looking the same.

Usage: python tools/death.py <bot> <opponent> <map> <seat A|B>
       python tools/death.py --losses <bot>      (walks the panel's loss list)
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
COMBAT = ("sentinel", "gunner", "launcher")

# every Core-kill loss on the 222/240 panel
LOSSES = [
    ("bots/zoo/adgato", "skald", "B"), ("bots/zoo/adgato", "auroraveil", "A"),
    ("bots/zoo/adgato", "auroraveil", "B"), ("bots/nash/flagship", "fimbulwinter", "B"),
    ("bots/nash/flagship", "auroraveil", "A"), ("bots/nash/flagship", "valkyrie", "A"),
    ("bots/nash/flagship", "yggdrasil", "B"), ("bots/nash/flagship", "midgard", "B"),
    ("bots/rivals/vanguard", "valkyrie", "A"), ("bots/rivals/vanguard", "bifrost", "A"),
    ("bots/rivals/vanguard", "paths", "A"), ("bots/rivals/vigil", "paths", "B"),
    ("bots/rivals/vanguard", "skald", "A"), ("bots/rivals/vigil", "longhouse", "B"),
    ("bots/rivals/vanguard", "holmgang", "B"),
]


def one(bot, opp, m, seat, out):
    us = "a" if seat == "A" else "b"
    x, y = (bot, opp) if seat == "A" else (opp, bot)
    r = run_game(str(ROOT / x / "main.py"), str(ROOT / y / "main.py"), ENGINE,
                 str(ROOT / "maps" / (m + ".map26")), str(out), 1, 0)
    rep = load_replay(str(out))
    ours, theirs, alive = [], [], {}
    our_builder_died = None
    for t, _st, ta in rep.iter_states():
        for e in ta.placed:
            alive[e.id] = (e.team, e.kind)
            if e.kind in COMBAT:
                (ours if e.team == us else theirs).append((t, e.kind))
        for uid in ta.removed:
            who = alive.pop(uid, None)
            if who and who[0] == us and who[1] == "builder_bot" and our_builder_died is None:
                our_builder_died = t

    def fmt(rows):
        if not rows:
            return "none"
        return " ".join("%s@%d" % (k[:4], t) for t, k in rows[:6])

    print("  %-22s %-13s seat %s  ended r%-5s %s" % (opp, m, seat, r["turns"], r["winner"]))
    print("       ours   %s" % fmt(ours))
    print("       theirs %s" % fmt(theirs))
    print("       our first Builder died: %s" % (our_builder_died or "-"))
    return ours, theirs


def main():
    bot = sys.argv[2] if sys.argv[1] == "--losses" else sys.argv[1]
    out = ROOT / "replays" / "death.replay26"
    out.parent.mkdir(parents=True, exist_ok=True)
    print("DEATH TIMELINE  %s" % bot)
    races, routs = 0, 0
    for opp, m, seat in LOSSES:
        try:
            ours, theirs = one(bot, opp, m, seat, out)
        except Exception as exc:
            print("  %-22s %-13s ERROR %s" % (opp, m, str(exc)[:50]))
            continue
        if len(ours) >= 4 and theirs and theirs[0][0] < ours[3][0]:
            races += 1
        elif not ours:
            routs += 1
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" not in pc.parts:
            shutil.rmtree(pc, ignore_errors=True)
    print()
    print("lost the race (their first turret beat our fourth): %d" % races)
    print("never built a turret at all: %d" % routs)


main()
