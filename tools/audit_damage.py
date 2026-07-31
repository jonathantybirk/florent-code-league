"""Is "any HP loss on one of our units PROVES the enemy has a fed turret" still true on 2.3.3?

On 2.2.0 it was a zero-false-positive detector, resting on two premises:
  (1) a Builder Bot cannot damage an adjacent tile at all      -- old G13
  (2) our own turrets never fire on our own team               -- never true, but harmless while
      turrets had no ammo and sat inert

Both are now dead. G13 is REVERSED (a builder hits orthogonally adjacent tiles for 2 dmg / 2 Ti,
G59) and G10/G11 are re-verified with teeth: turrets are team-blind AND now have a global pool to
shoot from, so our own Gunner grinds down our own buildings.

This attributes EVERY hit point our side loses, from the replay alone:

    ENEMY_TURRET   a fire event that round, from a tile holding an enemy Gunner/Sentinel
    SELF_FIRE      ...from a tile holding one of OUR OWN turrets      <- false positive (2)
    BUILDER_MELEE  no fire that round; an enemy Builder Bot orthogonally adjacent; -2 HP
                                                                     <- false positive (1)
    UNKNOWN        none of the above

and reports, per opponent, the games in which we take damage while the opponent has never built a
turret at all -- which is the false-positive rate of the detector, directly.

usage:  python fp.py <me> <opponent> <known|unseen> [nmaps]
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

from mapio import dump, fields

REPO = pathlib.Path(r"c:\Users\edlun\Desktop\lucky shots\Hackathons\florent-code-league")
HERE = pathlib.Path(__file__).resolve().parent
ISO = HERE / os.environ.get("FF_ISO", "_iso")
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)

TYPE = {10: 'BUILDER', 11: 'CONVEYOR', 12: 'SPLITTER', 13: 'BARRIER', 15: 'HARVESTER',
        21: 'GUNNER', 22: 'SENTINEL', 24: 'LAUNCHER', 18: 'BARRIER', 20: 'LAUNCHER'}
TURRETS = ('GUNNER', 'SENTINEL', 'LAUNCHER')


def scrub():
    for pc in ISO.rglob("__pycache__"):
        shutil.rmtree(pc, ignore_errors=True)


def resolve(bot):
    p = ISO / bot
    if not p.exists():
        p = REPO / bot
    return str(p / "main.py") if p.is_dir() else str(p)


def zz(v):
    return v - (1 << 64) if v >= (1 << 63) else v


def pos_of(v):
    d = {f: x for f, _, x in fields(v)}
    return (d.get(1, 0), d.get(2, 0))


def walk(path):
    """Replay the event stream keeping LIVE state, so damage can be attributed as it happens."""
    data = pathlib.Path(path).read_bytes()
    rounds = [v for fn, wt, v in fields(data) if fn == 3]
    ent = {}
    for ri, rv in enumerate(rounds):
        fires = []
        hits = []
        pending = []
        for f2, w2, v2 in fields(rv):
            if f2 != 1:
                continue
            for k, kw, kv in fields(v2):
                pending.append((k, kv))
        # fires first: within a round the shot and the hit-point delta are separate events
        for k, kv in pending:
            if k == 12:
                d = {f: x for f, _, x in fields(kv)}
                fires.append((pos_of(d[1]), pos_of(d[2])))
        for k, kv in pending:
            if k == 1:
                inner = fields(kv)
                if len(inner) == 1 and inner[0][0] == 1 and inner[0][1] == 2:
                    kv = inner[0][2]
                d = {}
                for f, w, x in fields(kv):
                    d.setdefault(f, []).append(x)
                if 1 not in d or 3 not in d or 5 not in d:
                    continue
                marker = [f for f in d if f not in (1, 2, 3, 4, 5)]
                ent[d[1][0]] = {'team': 'B' if 2 in d else 'A',
                                'type': TYPE.get(marker[0], '?') if marker else '?',
                                'pos': pos_of(d[3][0]), 'hp': d[4][0], 'alive': True}
            elif k == 2:
                d = {f: x for f, _, x in fields(kv)}
                e = ent.get(d.get(1))
                if e:
                    e['pos'] = pos_of(d[2])
            elif k == 3:
                d = {f: x for f, _, x in fields(kv)}
                e = ent.get(d.get(1))
                if e:
                    e['alive'] = False
            elif k == 5:
                d = {f: x for f, _, x in fields(kv)}
                e = ent.get(d.get(1))
                if e:
                    delta = zz(d.get(2, 0))
                    e['hp'] += delta
                    if delta < 0:
                        hits.append((d.get(1), -delta))
        yield ri, ent, fires, hits


def audit(replay, side, tally):
    us = 'A' if side == 'a' else 'B'
    them = 'B' if us == 'A' else 'A'
    foe_turret_ever = False
    our_dmg = 0
    causes = Counter()
    # EV_HURT latches on the FIRST hit point we lose and never un-latches, so the honesty of the
    # whole detector is the honesty of that one event. Record what caused it, and when the enemy
    # first had a turret at all / first actually fired one -- a bit that latches before either is
    # a bit that was wrong when it fired, whatever happens later.
    first_dmg = None
    first_cause = None
    first_foe_turret = None
    first_foe_fire = None
    for ri, ent, fires, hits in walk(replay):
        by_tile = {}
        for i, e in ent.items():
            if e['alive']:
                by_tile.setdefault(e['pos'], []).append(e)
        for i, e in ent.items():
            if e['team'] == them and e['type'] in TURRETS:
                foe_turret_ever = True
                if first_foe_turret is None:
                    first_foe_turret = ri
        if first_foe_fire is None:
            for src, dst in fires:
                for occ in by_tile.get(src, []):
                    if occ['team'] == them and occ['type'] in TURRETS:
                        first_foe_fire = ri
        for eid, amount in hits:
            e = ent.get(eid)
            if e is None or e['team'] != us:
                continue
            our_dmg += amount
            tile = e['pos']
            shooter = None
            for src, dst in fires:
                if dst == tile:
                    for occ in by_tile.get(src, []):
                        if occ['type'] in TURRETS:
                            shooter = occ
                            break
                    if shooter:
                        break
            if shooter is not None:
                cause = 'SELF_FIRE' if shooter['team'] == us else 'ENEMY_TURRET'
            else:
                adj = False
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    for occ in by_tile.get((tile[0] + dx, tile[1] + dy), []):
                        if occ['team'] == them and occ['type'] == 'BUILDER':
                            adj = True
                if adj and amount <= 2:
                    cause = 'BUILDER_MELEE'
                elif adj:
                    cause = 'BUILDER_ADJ_BIG'
                else:
                    cause = 'UNKNOWN'
            causes[cause] += amount
            if first_dmg is None:
                first_dmg, first_cause = ri, cause
    for k, v in causes.items():
        tally[k] += v
    tally['our_dmg'] += our_dmg
    tally['games'] += 1
    if foe_turret_ever:
        tally['games_foe_had_turret'] += 1
    verdict = "-"
    if first_dmg is not None:
        tally['games_we_took_damage'] += 1
        tally['latch_' + first_cause] += 1
        # The claim EV_HURT makes is "they have a fed turret". It is false at the moment of
        # latching if they had never built one, or had never fired one.
        if not foe_turret_ever:
            tally['FP_no_turret_all_game'] += 1
            verdict = "FP(no turret)"
        elif first_foe_fire is None or first_dmg < first_foe_fire:
            tally['FP_before_foe_fired'] += 1
            verdict = "FP(early r%s<%s)" % (first_dmg, first_foe_fire)
        else:
            verdict = "ok"
        if first_cause in ('BUILDER_MELEE', 'SELF_FIRE'):
            tally['FP_cause_not_a_turret'] += 1
    return our_dmg, foe_turret_ever, causes, first_dmg, first_cause, first_foe_fire, verdict


def main():
    me, foe = sys.argv[1], sys.argv[2]
    pool = sys.argv[3] if len(sys.argv) > 3 else "known"
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    maps = sorted((REPO / "maps").glob("*.map26")) if pool == "known" \
        else sorted((REPO / "maps" / "generated").glob("*.map26"))
    if n:
        maps = maps[:n]

    dest = HERE / ("_fp_%d.replay26" % os.getpid())
    tally = Counter()
    print("=== EV_HURT FALSE-POSITIVE AUDIT  %s vs %s [%s]  (fcode %s) ==="
          % (me, foe, pool, fcode.__version__))
    print("%-22s%-3s%-7s%-6s%-8s%-14s%-7s%-16s%s"
          % ("map", "sd", "ourDmg", "foeT", "1stDmg@", "latched by", "foeFir", "verdict",
             "attribution"))
    for mp in maps:
        for side in ("a", "b"):
            scrub()
            a, b = (me, foe) if side == "a" else (foe, me)
            run_game(resolve(a), resolve(b), ENGINE, str(mp), str(dest), 1, 0)
            scrub()
            dmg, ft, causes, fd, fc, ff, verdict = audit(dest, side, tally)
            print("%-22s%-3s%-7d%-6s%-8s%-14s%-7s%-16s%s"
                  % (mp.stem[:21], side, dmg, "yes" if ft else "NO",
                     "r%s" % fd if fd is not None else "-", fc or "-",
                     "r%s" % ff if ff is not None else "never", verdict,
                     " ".join("%s=%d" % (k, v) for k, v in sorted(causes.items()))))
    if dest.exists():
        dest.unlink()
    g = max(1, tally['games'])
    print("\n--- %d games ---" % tally['games'])
    print("  total HP we lost              %6d" % tally['our_dmg'])
    for k in ('ENEMY_TURRET', 'SELF_FIRE', 'BUILDER_MELEE', 'BUILDER_ADJ_BIG', 'UNKNOWN'):
        print("    %-18s %6d   (%4.1f%%)"
              % (k, tally[k], 100.0 * tally[k] / max(1, tally['our_dmg'])))
    print("  games we took damage          %6d / %d" % (tally['games_we_took_damage'], g))
    print("  games the foe HAD a turret    %6d / %d" % (tally['games_foe_had_turret'], g))
    d = max(1, tally['games_we_took_damage'])
    print("\n  what LATCHED EV_HURT (first hit point lost):")
    for k in ('ENEMY_TURRET', 'SELF_FIRE', 'BUILDER_MELEE', 'BUILDER_ADJ_BIG', 'UNKNOWN'):
        print("    %-18s %6d   (%4.1f%% of latches)"
              % (k, tally['latch_' + k], 100.0 * tally['latch_' + k] / d))
    fp = tally['FP_no_turret_all_game'] + tally['FP_before_foe_fired']
    print("\n  EV_HURT latched with NO enemy turret on the board   %4d"
          % tally['FP_no_turret_all_game'])
    print("  EV_HURT latched BEFORE any enemy turret fired      %4d"
          % tally['FP_before_foe_fired'])
    print("  EV_HURT latched on damage a turret did not do      %4d"
          % tally['FP_cause_not_a_turret'])
    print("\n  FALSE POSITIVE RATE  %d / %d games with damage  (%.1f%%)"
          % (fp, d, 100.0 * fp / d))


if __name__ == "__main__":
    main()
