"""Feedback loop for the idling/route-waste diagnosis.

One deterministic game, then a per-round trace of ONE unit: whether the engine ran its
code that round, what action was attributed to it, where it stood, and what it could
legally have done. Fast (~3 s), exact (the engine is deterministic), and sharp enough to
tell a real idle from a detector artefact.

The artefact matters, and is the first thing this has to rule out. `tools/diag/replay.py`
documents three things the replay does NOT carry: store-slot writes, `rotate()`, and the
attribution of `destroy()`. A unit doing any of those looks idle to the detector while
having spent its round productively. So "did it idle" and "does the replay show it idling"
are different questions, and only the second is directly observable.

Usage:
  python tools/diag/why_idle.py <bot> <opponent> <map> <side> [--unit N] [--rounds A-B]
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import fcode                                                       # noqa: E402
from fcode.fcode_engine import run_game                            # noqa: E402

from arena import mapfile, resolve_bot                             # noqa: E402
from diag.replay import Replay                                     # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)


def play(bot: str, opp: str, mp: str, side: str, out: str) -> dict:
    a, b = (bot, opp) if side == "A" else (opp, bot)
    return run_game(resolve_bot(a), resolve_bot(b), ENGINE, mapfile(mp), out, 1, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bot")
    ap.add_argument("opponent")
    ap.add_argument("map")
    ap.add_argument("side", choices=["A", "B"])
    ap.add_argument("--unit", type=int, default=None)
    ap.add_argument("--rounds", default=None, help="A-B")
    ap.add_argument("--top", type=int, default=3, help="worst N idlers to trace")
    a = ap.parse_args()

    out = str(ROOT / "replays" / "whyidle.replay26")
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    res = play(a.bot, a.opponent, a.map, a.side, out)
    team = "a" if a.side == "A" else "b"
    print(f"{a.bot} vs {a.opponent} on {a.map}/{a.side}: "
          f"{res['win_condition']} t{res['turns']} "
          f"Ti {res[f'{team}_titanium_collected']}/"
          f"{res[('b' if team=='a' else 'a')+'_titanium_collected']}")

    rep = Replay(open(out, "rb").read())

    # pass 1 -- who idles, and is anything at all attributed to them
    ran = {}
    acted = {}
    kinds = {}
    for t, state, ta in rep.iter_states():
        for uid in ta.ran:
            e = state.entities.get(uid)
            if e is None or e.team != team:
                continue
            kinds[uid] = e.kind
            ran[uid] = ran.get(uid, 0) + 1
            did = (uid in ta.moves or uid in ta.builds or uid in ta.attacks
                   or uid in ta.heals or any(f[0] == (e.x, e.y) for f in ta.fires))
            if did:
                acted[uid] = acted.get(uid, 0) + 1

    print(f"\n{'unit':<7}{'kind':<14}{'ran':<7}{'acted':<8}{'idle':<7}{'idle %'}")
    ranked = sorted(ran, key=lambda u: -(ran[u] - acted.get(u, 0)))
    for uid in ranked:
        idle = ran[uid] - acted.get(uid, 0)
        print(f"{uid:<7}{kinds.get(uid,'?'):<14}{ran[uid]:<7}{acted.get(uid,0):<8}"
              f"{idle:<7}{idle/max(ran[uid],1):.0%}")

    targets = [a.unit] if a.unit is not None else ranked[: a.top]
    lo, hi = (0, 10 ** 9)
    if a.rounds:
        lo, hi = (int(x) for x in a.rounds.split("-"))

    for uid in targets:
        if uid not in ran:
            continue
        print(f"\n--- unit {uid} ({kinds.get(uid,'?')}) per-round trace ---")
        print(f"{'rnd':<6}{'pos':<10}{'action':<34}{'us':<8}cooldowns(a/m)")
        last_pos = None
        streak = 0
        for t, state, ta in rep.iter_states():
            if not (lo <= t <= hi) or uid not in ta.ran:
                continue
            e = state.entities.get(uid)
            if e is None:
                continue
            pos = (e.x, e.y)
            act = []
            if uid in ta.moves:
                act.append(f"move->{ta.moves[uid]}")
            if uid in ta.builds:
                act.append(f"build{ta.build_kind.get(uid,('?',None))}@{ta.builds[uid]}")
            if uid in ta.attacks:
                act.append(f"attack{ta.attacks[uid]}")
            if uid in ta.heals:
                act.append(f"heal{ta.heals[uid]}")
            if any(f[0] == pos for f in ta.fires):
                act.append("fire")
            label = ", ".join(act) if act else "-- nothing --"
            if not act:
                streak += 1
            else:
                streak = 0
            info = ta.ran[uid]
            # only print transitions and long streaks, so the trace stays readable
            if act or streak in (1, 2, 5, 10, 20, 40) or pos != last_pos:
                print(f"{t:<6}{str(pos):<10}{label:<34}"
                      f"{info.get('execTimeUs', 0):<8}"
                      f"{getattr(e,'action_cooldown','?')}/{getattr(e,'move_cooldown','?')}")
            last_pos = pos


if __name__ == "__main__":
    main()
