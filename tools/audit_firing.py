"""FIRING FRACTION on fcode 2.3.3, measured from the replay alone.

The 2.2.0 defect was that 61% of the Gunners we built on unseen maps never fired, because a
turret held its own magazine and the belt that was supposed to fill it never arrived. On 2.3.3
ammunition is a single team-wide pool filled only by `convert_ammo` at the Core (G52/G53), so the
same headline number can be produced by a completely different mechanism. This measures it again
and splits the non-firing Gunners by the only causes a replay can distinguish:

    died_young   destroyed within DEAD_SOON rounds of being built -- it was killed, not starved
    no_ammo_gm   NOBODY on our team fired all game -> the pool was empty, a team-wide failure
    idle         it lived, the team had ammo, and this turret still never pulled the trigger
                 (no target in its lane: a siting failure, not a supply failure)

Runs entirely inside e10/_iso so it cannot collide with the other agents live in the repo.

usage:  python ff.py <me> <opponent> <known|unseen> [nmaps] [sides]
"""
import os
import pathlib
import shutil
import sys
from collections import Counter

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

import fcode
from fcode.fcode_engine import run_game

from mapio import dump
from tl import Game

REPO = pathlib.Path(r"c:\Users\edlun\Desktop\lucky shots\Hackathons\florent-code-league")
HERE = pathlib.Path(__file__).resolve().parent
# Each parallel job gets its own copy of the sandbox, because run_game's importlib trial-load
# writes __pycache__ next to every main.py it touches (M04) and a scrub from a sibling job
# mid-load is exactly the G30 inert-bot failure.
ISO = HERE / os.environ.get("FF_ISO", "_iso")
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)

DEAD_SOON = 12          # rounds; a turret killed this fast never had a fair chance to shoot
_ANCHORS = {}


def scrub():
    """Scrub ONLY my own tree -- never the repo's, two other agents are running in it."""
    for pc in ISO.rglob("__pycache__"):
        shutil.rmtree(pc, ignore_errors=True)


def resolve(bot):
    p = ISO / bot
    if not p.exists():
        p = pathlib.Path(bot)
        if not p.is_absolute():
            p = REPO / bot
    return str(p / "main.py") if p.is_dir() else str(p)


def anchors(map_path):
    key = str(map_path)
    if key not in _ANCHORS:
        w, h, rows, cores = dump(key)
        out = {}
        for c in cores:
            out['A' if c['owner'] == 1 else 'B'] = (c['pos'].get(1, 0), c['pos'].get(2, 0))
        _ANCHORS[key] = out
    return _ANCHORS[key]


def foot(a):
    x, y = a
    return {(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)}


def measure(replay, map_path, side, tally):
    a = anchors(map_path)
    us = 'A' if side == 'a' else 'B'
    them = 'B' if us == 'A' else 'A'
    foe_core = foot(a[them])
    g = Game(str(replay))

    guns = {i: e for i, e in g.ent.items() if e['team'] == us and e['type'] == 'GUNNER'}
    # a Gunner is identified in the fire stream by the tile it fires FROM; buildings never move
    by_tile = {}
    for i, e in guns.items():
        by_tile.setdefault(e['pos'], []).append(i)

    fired = Counter()
    on = off = 0
    team_shots = 0
    for ri, p, q in g.fires:
        ids = by_tile.get(p)
        if not ids:
            continue
        team_shots += 1
        fired[ids[0]] += 1
        if q in foe_core:
            on += 1
        else:
            off += 1

    for i, e in guns.items():
        tally['guns'] += 1
        if fired.get(i):
            tally['fired'] += 1
            continue
        life = (e['died'] if e['died'] is not None else g.nrounds) - e['born']
        if life <= DEAD_SOON:
            tally['died_young'] += 1
        elif team_shots == 0:
            tally['no_ammo_gm'] += 1
        else:
            tally['idle'] += 1

    theirs = [i for i, e in g.ent.items() if e['team'] == them and e['type'] == 'GUNNER']
    tally['their_guns'] += len(theirs)
    tally['on_core'] += on
    tally['absorbed'] += off
    cond = g.cond.decode() if isinstance(g.cond, bytes) else g.cond
    return len(guns), len(fired), on, off, cond, g.nrounds


def main():
    me, foe = sys.argv[1], sys.argv[2]
    pool = sys.argv[3] if len(sys.argv) > 3 else "known"
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    sides = sys.argv[5].split(",") if len(sys.argv) > 5 else ["a", "b"]
    maps = sorted((REPO / "maps").glob("*.map26")) if pool == "known" \
        else sorted((REPO / "maps" / "generated").glob("*.map26"))
    if n:
        maps = maps[:n]

    dest = HERE / ("_ff_%d.replay26" % os.getpid())
    tally = Counter()
    rows = []
    print("=== FIRING FRACTION  %s vs %s  [%s]  %d maps x %d sides  (fcode %s) ==="
          % (me, foe, pool, len(maps), len(sides), fcode.__version__))
    print("%-24s%-3s%-3s%-17s%-6s%-5s%-5s%-7s%-6s"
          % ("map", "sd", "R", "cond", "rnds", "gun", "fir", "onCore", "abs"))
    for mp in maps:
        for side in sides:
            scrub()
            a, b = (me, foe) if side == "a" else (foe, me)
            res = run_game(resolve(a), resolve(b), ENGINE, str(mp), str(dest), 1, 0)
            scrub()
            won = (res["winner"] == "A") if side == "a" else (res["winner"] == "B")
            ng, nf, on, off, cond, rnd = measure(dest, mp, side, tally)
            tally['games'] += 1
            tally['wins'] += 1 if won else 0
            if won and cond == "core_destroyed":
                tally['kills'] += 1
            rows.append((won, cond))
            print("%-24s%-3s%-3s%-17s%-6s%-5d%-5d%-7d%-6d"
                  % (mp.stem[:23], side, "W" if won else "L", cond, rnd, ng, nf, on, off))
    if dest.exists():
        dest.unlink()

    gm = max(1, tally['games'])
    ng = max(1, tally['guns'])
    print("\n--- %d games:  record %d-%d,  %d core kills ---"
          % (tally['games'], tally['wins'], tally['games'] - tally['wins'], tally['kills']))
    print("  our gunners built      %5d   (%.2f/game)" % (tally['guns'], tally['guns'] / float(gm)))
    print("  ...that ever fired     %5d" % tally['fired'])
    print("  ...died within %2d rnds %5d" % (DEAD_SOON, tally['died_young']))
    print("  ...team had NO ammo    %5d" % tally['no_ammo_gm'])
    print("  ...idle (no target)    %5d" % tally['idle'])
    print("  shots on enemy core    %5d   (%.1f/game)"
          % (tally['on_core'], tally['on_core'] / float(gm)))
    print("  shots absorbed         %5d" % tally['absorbed'])
    print("  their gunners built    %5d" % tally['their_guns'])
    print("\n  FIRING FRACTION  %.1f%%   (%d of %d)"
          % (100.0 * tally['fired'] / ng, tally['fired'], tally['guns']))


if __name__ == "__main__":
    main()
