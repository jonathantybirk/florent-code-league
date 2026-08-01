"""TASK-2 MECHANISM AUDIT -- why do we build no Gunner, and why do some never fire?

Reads everything out of the .replay26, with NO instrumentation in the bot, because the replay
already carries a per-round snapshot of both teams' 16 store slots (event kind 6) and our bot
publishes its whole siege state through them:

    slot 10  S_ENEMY_CORE   packed inferred anchor | bit16 SIGHTED
    slot 12  S_RUSHER       rusher builder id + 1
    slot 14  S_RUSH_RAY     packed gunner tile | facing -- WRITTEN ONLY WHEN A PLAN IS FOUND
    slot 15  S_RUSH_ACTIVE  1 once a rusher exists
    slot 13  S_RUSH_DONE    1 once the route is finished

So a game with no Gunner splits cleanly:
    NO-PLAN      slot 14 never becomes non-zero -> siege.plan() never returned a site
    PLAN-NOBUILD slot 14 set but no Gunner -> could not reach / could not pay / rusher died
and the rusher's fate is read off the entity table by its id.

usage:  python audit.py <me> <opp> <known|unseen> [nmaps] [jobs]
        python audit.py <me> <opp> <known|unseen> [nmaps] [jobs] --worker <k> <out.jsonl>
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
from collections import Counter

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

REPO = pathlib.Path(r"c:\Users\edlun\Desktop\lucky shots\Hackathons\florent-code-league")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "tools"))

import fcode                                    # noqa: E402
from fcode.fcode_engine import run_game         # noqa: E402
from mapio import dump, fields                  # noqa: E402
from tl import Game                             # noqa: E402

ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
DEAD_SOON = 12
S_ENEMY_CORE, S_RUSH_DONE, S_RUSH_RAY, S_RUSH_ACTIVE, S_RUSHER = 10, 13, 14, 15, 12
REACH8 = (3, 3, 3, 3, 2, 2, 2, 2)
DELTA8 = ((0, -1), (1, 0), (0, 1), (-1, 0), (1, -1), (1, 1), (-1, 1), (-1, -1))


def varints(blob):
    out, cur, sh = [], 0, 0
    for byte in blob:
        cur |= (byte & 0x7F) << sh
        if byte & 0x80:
            sh += 7
        else:
            out.append(cur)
            cur, sh = 0, 0
    return out


def unwrap(v):
    while True:
        fs = fields(v)
        if len(fs) == 1 and fs[0][0] == 1 and fs[0][1] == 2:
            v = fs[0][2]
            continue
        return fs


def team_state(path):
    """[(round, team, titanium, [16 slots])] straight out of event kind 6."""
    data = pathlib.Path(path).read_bytes()
    out = []
    ri = -1
    for fn, wt, v in fields(data):
        if fn != 3:
            continue
        ri += 1
        for f2, w2, v2 in fields(v):
            if f2 != 1:
                continue
            for k, kw, kv in fields(v2):
                if k != 6:
                    continue
                for team, tw, tv in unwrap(kv):
                    if not isinstance(tv, bytes):
                        continue
                    ti, slots, ammo = 0, [], 0
                    for f4, w4, v4 in fields(tv):
                        if f4 == 1:
                            ti = v4
                        elif f4 == 7:
                            ammo = v4          # global ammo pool (field 7 of the team state)
                        elif f4 == 6 and isinstance(v4, bytes):
                            slots = varints(v4)
                    out.append((ri, team, ti, slots, ammo))
    return out


_MAPS = {}


def mapinfo(path):
    key = str(path)
    if key not in _MAPS:
        w, h, rows, cores = dump(key)
        anch = {}
        for c in cores:
            anch['A' if c['owner'] == 1 else 'B'] = (c['pos'].get(1, 0), c['pos'].get(2, 0))
        walls = set()
        for y, r in enumerate(rows):
            for x, b in enumerate(r):
                if b == 1:
                    walls.add((x, y))
        _MAPS[key] = (w, h, walls, anch)
    return _MAPS[key]


def foot(a):
    x, y = a
    return {(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)}


def unpack(val):
    if val <= 0:
        return None
    return ((val >> 8) - 1, (val & 0xFF) - 1)


def classify_idle(g, gun, us, walls, foe_core, born):
    """Why did this Gunner never fire? Reconstruct its lane from the replay.

    Buildings never move, so the occupancy of a ray tile over the turret's life is exactly the set
    of buildings alive there. Reports, for the best-bearing facing:
        OUT_OF_REACH  no facing from that tile reaches a Core footprint tile at all
        WALL          terrain blocks every bearing
        OURS          the first thing in every bearing ray is one of OUR buildings (a G11 jam)
        THEIRS        the first thing is one of THEIRS (clearable, but our policy holds)
        CLEAR         nothing in the lane -- the turret should have fired
    """
    gp = gun['pos']
    # buildings alive at some point during the turret's life, by tile
    occ = {}
    for i, e in g.ent.items():
        if e['type'] == 'BUILDER':
            continue
        if e['died'] is not None and e['died'] < born:
            continue
        if e['born'] > (gun['died'] if gun['died'] is not None else g.nrounds):
            continue
        occ.setdefault(e['pos'], []).append(e)
    verdicts = []
    for di in range(8):
        d = DELTA8[di]
        first = None
        hit_core = False
        for k in range(1, REACH8[di] + 1):
            t = (gp[0] + k * d[0], gp[1] + k * d[1])
            if t in walls:
                first = 'WALL'
                break
            if t in foe_core:
                hit_core = True
                break
            here = [e for e in occ.get(t, []) if e['type'] != 'CORE']
            if here:
                first = 'OURS' if any(e['team'] == us for e in here) else 'THEIRS'
                break
        if not hit_core and first is None:
            continue                    # this bearing never reaches the Core: not a candidate
        if hit_core and first is None:
            return 'CLEAR'
        if hit_core or first is not None:
            verdicts.append(first if first is not None else 'CLEAR')
    if not verdicts:
        return 'OUT_OF_REACH'
    for want in ('CLEAR', 'THEIRS', 'OURS', 'WALL'):
        if want in verdicts:
            return want
    return 'OUT_OF_REACH'


def measure(replay, mp, side, res):
    w, h, walls, anch = mapinfo(mp)
    us = 'A' if side == 'a' else 'B'
    them = 'B' if us == 'A' else 'A'
    foe_core = foot(anch[them])
    my_team_idx = 1 if us == 'A' else 2
    g = Game(str(replay))

    guns = {i: e for i, e in g.ent.items() if e['team'] == us and e['type'] == 'GUNNER'}
    by_tile = {}
    for i, e in guns.items():
        by_tile.setdefault(e['pos'], []).append(i)
    fired = Counter()
    on = off = 0
    for ri, p, q in g.fires:
        ids = by_tile.get(p)
        if not ids:
            continue
        fired[ids[0]] += 1
        if q in foe_core:
            on += 1
        else:
            off += 1

    ray_at = active_at = done_at = None
    peak_ti = 0
    anchor_guess = None
    sighted = False
    rusher = None
    ammo_by_round = {}
    for ri, team, ti, slots, ammo in team_state(replay):
        if team != my_team_idx:
            continue
        ammo_by_round[ri] = ammo
        peak_ti = max(peak_ti, ti)
        if len(slots) < 16:
            continue
        if ray_at is None and slots[S_RUSH_RAY]:
            ray_at = ri
        if active_at is None and slots[S_RUSH_ACTIVE] == 1:
            active_at = ri
        if done_at is None and slots[S_RUSH_DONE] == 1:
            done_at = ri
        if slots[S_ENEMY_CORE]:
            anchor_guess = unpack(slots[S_ENEMY_CORE] & 0xFFFF)
            sighted = bool(slots[S_ENEMY_CORE] & (1 << 16))
        if slots[S_RUSHER]:
            rusher = slots[S_RUSHER] - 1

    rusher_died = None
    if rusher is not None and rusher in g.ent:
        rusher_died = g.ent[rusher]['died']

    # Now the per-Gunner verdict, with the ammo pool in hand: a turret that lived its whole life
    # on an empty team pool was STARVED, not badly sited.
    idle_why = []
    n_fired = n_dead_young = n_idle = 0
    for i, e in guns.items():
        if fired.get(i):
            n_fired += 1
            continue
        end = e['died'] if e['died'] is not None else g.nrounds
        life = end - e['born']
        if life <= DEAD_SOON:
            n_dead_young += 1
            continue
        n_idle += 1
        rich = sum(1 for r in range(e['born'], end) if ammo_by_round.get(r, 0) >= 2)
        if rich * 5 < life:            # armed for under a fifth of its life
            idle_why.append('STARVED')
        else:
            idle_why.append(classify_idle(g, e, us, walls, foe_core, e['born']))

    born_rounds = sorted(e['born'] for e in guns.values())
    won = (res["winner"] == "A") if side == 'a' else (res["winner"] == "B")
    return dict(map=pathlib.Path(mp).stem, side=side, won=bool(won),
                cond=res["win_condition"], turns=res["turns"],
                guns=len(guns), fired=n_fired, idle=n_idle, dead_young=n_dead_young,
                idle_why=idle_why, first_gun=born_rounds[0] if born_rounds else None,
                on_core=on, absorbed=off, peak_ti=peak_ti, end_ti=res["a_titanium"]
                if side == 'a' else res["b_titanium"],
                ray_at=ray_at, active_at=active_at, done_at=done_at,
                anchor=anchor_guess, true_anchor=anch[them], sighted=sighted,
                rusher_died=rusher_died,
                their_guns=len([1 for e in g.ent.values()
                                if e['team'] == them and e['type'] == 'GUNNER']))


def jobs(pool, n):
    maps = sorted((REPO / "maps").glob("*.map26")) if pool == "known" \
        else sorted((REPO / "maps" / "generated").glob("*.map26"))
    if n:
        maps = maps[:n]
    return [(str(m), s) for m in maps for s in ("a", "b")]


def iso_for(k, me, opp):
    # PID-unique: two audits running at once used to share bots/cand/_j0..; the second one's
    # rmtree deleted the first one's sandbox mid-match and every remaining game in that worker
    # measured as a bot that failed to load.
    d = REPO / "bots" / "cand" / ("_j%d_%d" % (os.getppid(), k))
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for b in (me, opp):
        src = REPO / b
        dst = d / pathlib.Path(b).name
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        out.append(str(dst / "main.py"))
    return d, out[0], out[1]


def worker(k, njobs, me, opp, pool, n, outpath):
    d, mep, oppp = iso_for(k, me, opp)
    dest = d / "r.replay26"
    rows = []
    for idx, (mp, side) in enumerate(jobs(pool, n)):
        if idx % njobs != k:
            continue
        for pc in d.rglob("__pycache__"):
            shutil.rmtree(pc, ignore_errors=True)
        a, b = (mep, oppp) if side == "a" else (oppp, mep)
        res = run_game(a, b, ENGINE, mp, str(dest), 1, 0)
        rows.append(measure(dest, mp, side, res))
    pathlib.Path(outpath).write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    shutil.rmtree(d, ignore_errors=True)


def report(rows, title):
    t = Counter()
    idle_why = Counter()
    firsts = []
    nogun_rows = []
    for r in rows:
        t['games'] += 1
        t['wins'] += 1 if r['won'] else 0
        t['kills'] += 1 if (r['won'] and r['cond'] == 'core_destroyed') else 0
        t['guns'] += r['guns']
        t['fired'] += r['fired']
        t['idle'] += r['idle']
        t['dead_young'] += r['dead_young']
        t['on_core'] += r['on_core']
        t['absorbed'] += r['absorbed']
        t['their_guns'] += r['their_guns']
        for wv in r['idle_why']:
            idle_why[wv] += 1
        if r['first_gun'] is not None:
            firsts.append(r['first_gun'])
        if r['guns'] == 0:
            t['nogun'] += 1
            nogun_rows.append(r)
            if r['ray_at'] is None:
                t['nogun_noplan'] += 1
            elif r['rusher_died'] is not None:
                t['nogun_rusher_died'] += 1
            else:
                t['nogun_planned_nobuild'] += 1
            if r['peak_ti'] >= 200:
                t['nogun_rich'] += 1
        if r['anchor'] is not None and tuple(r['anchor']) != tuple(r['true_anchor']):
            t['wrong_anchor'] += 1
    firsts.sort()
    med = firsts[len(firsts) // 2] if firsts else None
    gm = max(1, t['games'])
    print("\n===== %s =====" % title)
    print("  record %d-%d   core kills %d" % (t['wins'], t['games'] - t['wins'], t['kills']))
    print("  games with ZERO gunners      %3d / %3d  (%.0f%%)"
          % (t['nogun'], t['games'], 100.0 * t['nogun'] / gm))
    print("      ...of which NO PLAN EVER (slot14 never set)  %d" % t['nogun_noplan'])
    print("      ...planned, rusher DIED                      %d" % t['nogun_rusher_died'])
    print("      ...planned, alive, never built               %d" % t['nogun_planned_nobuild'])
    print("      ...peak treasury >= 200 Ti (rich)            %d" % t['nogun_rich'])
    print("  gunners built  %4d  (%.2f/game)   theirs %d"
          % (t['guns'], t['guns'] / float(gm), t['their_guns']))
    print("      ever fired %4d    idle %d    died<=%d rnds %d"
          % (t['fired'], t['idle'], DEAD_SOON, t['dead_young']))
    if idle_why:
        print("      idle cause: %s" % dict(idle_why))
    print("  median first-gunner round    %s" % med)
    print("  shots ON enemy core %d (%.1f/game)   absorbed %d"
          % (t['on_core'], t['on_core'] / float(gm), t['absorbed']))
    print("  games with a WRONG inferred anchor  %d" % t['wrong_anchor'])
    if nogun_rows:
        print("  no-gunner games:")
        for r in nogun_rows:
            print("      %-26s %s  %-16s peakTi=%-6d ray@%-6s active@%-6s rusher_died=%s anchor=%s%s"
                  % (r['map'][:25], r['side'], r['cond'], r['peak_ti'], r['ray_at'],
                     r['active_at'], r['rusher_died'], r['anchor'],
                     "" if r['anchor'] is None or tuple(r['anchor']) == tuple(r['true_anchor'])
                     else " WRONG(true %s)" % (r['true_anchor'],)))
    return t


def main():
    me, opp, pool = sys.argv[1], sys.argv[2], sys.argv[3]
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    njobs = int(sys.argv[5]) if len(sys.argv) > 5 else 6
    if "--worker" in sys.argv:
        i = sys.argv.index("--worker")
        worker(int(sys.argv[i + 1]), njobs, me, opp, pool, n, sys.argv[i + 2])
        return
    tmp = HERE / ("_out_%s_%s_%s" % (pathlib.Path(me).name, pathlib.Path(opp).name, pool))
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    procs = []
    for k in range(njobs):
        out = tmp / ("w%d.jsonl" % k)
        procs.append(subprocess.Popen(
            [sys.executable, str(HERE / "audit.py"), me, opp, pool, str(n), str(njobs),
             "--worker", str(k), str(out)],
            cwd=str(REPO), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE))
    rows = []
    for k, p in enumerate(procs):
        _, err = p.communicate()
        if p.returncode != 0:
            print("worker %d FAILED rc=%d\n%s" % (k, p.returncode, err.decode()[-2000:]))
        f = tmp / ("w%d.jsonl" % k)
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
    report(rows, "%s vs %s [%s]  %d games" % (me, opp, pool, len(rows)))


if __name__ == "__main__":
    main()
