"""In the games where we build NO Gunner at all, are we broke or are we blocked?

The 2.2.0 defect was "we build the turret and it never shoots" (firing fraction). On 2.3.3 the
firing fraction is ~100% and the defect has MOVED: in half our games we never build a turret at
all. That has two very different causes and they want opposite fixes --

    BROKE    we never had the titanium, so the answer is economy or a cheaper opening
    BLOCKED  we sat on a full treasury and the siege planner never returned a site,
             so the answer is siting

The replay's per-round team-state event carries each team's titanium, so this can be read off
without instrumenting the bot: report peak treasury in the games where no Gunner is ever built.
A Gunner costs 10 x scale; anything above ~200 banked is not an economy problem.

usage:  python nogun.py <me> <opponent> <known|unseen> [nmaps]
"""
import os
import pathlib
import sys
from collections import Counter

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

import fcode
from fcode.fcode_engine import run_game
from mapio import fields

import audit_damage as fp
from parity import unwrap, varints

REPO = fp.REPO
HERE = fp.HERE
ENGINE = fp.ENGINE


def treasury(path):
    """(team -> [titanium each snapshot]) straight out of the team-state event."""
    data = pathlib.Path(path).read_bytes()
    out = {}
    for fn, wt, v in fields(data):
        if fn != 3:
            continue
        for f2, w2, v2 in fields(v):
            if f2 != 1:
                continue
            for k, kw, kv in fields(v2):
                if k != 6:
                    continue
                for team, tw, tv in unwrap(kv):
                    if not isinstance(tv, bytes):
                        continue
                    for f4, w4, v4 in fields(tv):
                        if f4 == 1:
                            out.setdefault(team, []).append(v4)
    return out


def census(path, side):
    us = 'A' if side == 'a' else 'B'
    guns = harv = conv = 0
    for ri, ent, fires, hits in fp.walk(path):
        pass
    for i, e in ent.items():
        if e['team'] != us:
            continue
        if e['type'] == 'GUNNER':
            guns += 1
        elif e['type'] == 'HARVESTER':
            harv += 1
        elif e['type'] == 'CONVEYOR':
            conv += 1
    return guns, harv, conv


def main():
    me, foe = sys.argv[1], sys.argv[2]
    pool = sys.argv[3] if len(sys.argv) > 3 else "known"
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    maps = sorted((REPO / "maps").glob("*.map26")) if pool == "known" \
        else sorted((REPO / "maps" / "generated").glob("*.map26"))
    if n:
        maps = maps[:n]
    dest = HERE / ("_ng_%d.replay26" % os.getpid())
    tally = Counter()
    print("=== NO-GUNNER DIAGNOSIS  %s vs %s [%s] ===" % (me, foe, pool))
    print("%-24s%-3s%-6s%-6s%-6s%-9s%-9s%s"
          % ("map", "sd", "guns", "harv", "conv", "peakTi", "endTi", "verdict"))
    for mp in maps:
        for side in ("a", "b"):
            fp.scrub()
            a, b = (me, foe) if side == "a" else (foe, me)
            run_game(fp.resolve(a), fp.resolve(b), ENGINE, str(mp), str(dest), 1, 0)
            fp.scrub()
            g, h, c = census(str(dest), side)
            tre = treasury(str(dest))
            ours = tre.get(1 if side == "a" else 2, [0])
            peak, end = max(ours), ours[-1]
            verdict = "-"
            if g == 0:
                tally['nogun'] += 1
                if peak >= 200:
                    verdict = "BLOCKED (rich)"
                    tally['blocked'] += 1
                else:
                    verdict = "broke"
                    tally['broke'] += 1
            tally['games'] += 1
            tally['peak_nogun'] += peak if g == 0 else 0
            print("%-24s%-3s%-6d%-6d%-6d%-9d%-9d%s"
                  % (mp.stem[:23], side, g, h, c, peak, end, verdict))
    if dest.exists():
        dest.unlink()
    ng = max(1, tally['nogun'])
    print("\n--- %d games, %d with NO gunner ---" % (tally['games'], tally['nogun']))
    print("  of those:  BLOCKED (peak treasury >= 200 Ti)  %d  (%.0f%%)"
          % (tally['blocked'], 100.0 * tally['blocked'] / ng))
    print("             broke   (never had the money)      %d" % tally['broke'])
    print("  mean peak treasury in a no-gunner game: %d Ti" % (tally['peak_nogun'] // ng))


if __name__ == "__main__":
    main()
