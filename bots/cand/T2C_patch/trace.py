"""Trace ONE game: the rusher's walk, the published firing tile, and the map around it.

usage: python trace.py <me> <opp> <map.map26> <a|b>
"""
import os
import pathlib
import shutil
import sys
from collections import Counter

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

REPO = pathlib.Path(r"c:\Users\edlun\Desktop\lucky shots\Hackathons\florent-code-league")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "tools"))

import fcode                                    # noqa: E402
from fcode.fcode_engine import run_game         # noqa: E402
from mapio import dump                          # noqa: E402
from tl import Game                             # noqa: E402
from audit import team_state, unpack, DELTA8, REACH8   # noqa: E402

ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
NAMES8 = ("N", "E", "S", "W", "NE", "SE", "SW", "NW")


def main():
    me, opp, mapname, side = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    mp = REPO / "maps" / (mapname + ".map26")
    if not mp.exists():
        mp = REPO / "maps" / "generated" / (mapname + ".map26")
    dest = HERE / "_trace.replay26"
    for pc in (REPO / "bots").rglob("__pycache__"):
        shutil.rmtree(pc, ignore_errors=True)
    a, b = (me, opp) if side == "a" else (opp, me)
    res = run_game(str(REPO / a / "main.py"), str(REPO / b / "main.py"), ENGINE,
                   str(mp), str(dest), 1, 0)
    print(res["winner"], res["win_condition"], res["turns"])

    w, h, rows, cores = dump(str(mp))
    anch = {}
    for c in cores:
        anch['A' if c['owner'] == 1 else 'B'] = (c['pos'].get(1, 0), c['pos'].get(2, 0))
    us = 'A' if side == 'a' else 'B'
    them = 'B' if us == 'A' else 'A'
    print("map %dx%d  our core %s  their core %s" % (w, h, anch[us], anch[them]))
    for y, r in enumerate(rows):
        print("   %2d %s" % (y, "".join(".#o"[bb] if bb < 3 else "?" for bb in r)))

    team_idx = 1 if us == 'A' else 2
    seq = []
    for ri, team, ti, slots, _am in team_state(dest):
        if team != team_idx or len(slots) < 16:
            continue
        seq.append((ri, ti, slots[14], slots[15], slots[13], slots[10], slots[12]))
    print("\nstore timeline (round, ti, RAY, ACTIVE, DONE, ENEMYCORE, RUSHER):")
    last = None
    for ri, ti, ray, act, done, ec, rush in seq:
        key = (ray, act, done, ec, rush)
        if key != last:
            g = unpack(ray & 0xFFFF)
            idx = (ray >> 17) & 7
            print("   r%-5d ti=%-6d ray=%s facing=%s active=%s done=%s enemy=%s rusher=%s"
                  % (ri, ti, g, NAMES8[idx] if ray else "-", act, done,
                     unpack(ec & 0xFFFF), rush - 1 if rush else None))
            last = key

    g = Game(str(dest))
    rusher = None
    for ri, team, ti, slots, _am in team_state(dest):
        if team == team_idx and len(slots) >= 16 and slots[12]:
            rusher = slots[12] - 1
            break
    print("\nrusher id %s" % rusher)
    # replay the move stream for that entity
    from mapio import fields
    data = pathlib.Path(dest).read_bytes()
    ri = -1
    track = []
    for fn, wt, v in fields(data):
        if fn != 3:
            continue
        ri += 1
        for f2, w2, v2 in fields(v):
            if f2 != 1:
                continue
            for k, kw, kv in fields(v2):
                d = {f: x for f, ww, x in fields(kv)}
                if k == 2 and d.get(1) == rusher:
                    p = {f: x for f, ww, x in fields(d[2])}
                    track.append((ri, (p.get(1, 0), p.get(2, 0))))
                elif k == 3 and d.get(1) == rusher:
                    track.append((ri, "DIED"))
    print("rusher track (%d moves):" % len(track))
    print("   " + "  ".join("r%d%s" % (r, p) for r, p in track[:120]))
    if len(track) > 120:
        print("   ... last: " + "  ".join("r%d%s" % (r, p) for r, p in track[-20:]))
    c = Counter(p for _, p in track)
    print("most-visited tiles:", c.most_common(8))
    print("\nour buildings:", sorted(((e['born'], e['type'], e['pos'])
                                      for i, e in g.ent.items()
                                      if e['team'] == us and e['type'] != 'BUILDER'))[:40])
    stall = c.most_common(1)[0][0] if c else (0, 0)
    print("\nEVERY entity ever within 4 tiles of the stall tile %s:" % (stall,))
    for i, e in sorted(g.ent.items(), key=lambda kv: kv[1]['born']):
        p = e['pos']
        if abs(p[0] - stall[0]) + abs(p[1] - stall[1]) <= 4:
            print("   id%-4d %-2s %-10s born r%-5d died %-6s pos %s"
                  % (i, e['team'], e['type'], e['born'], e['died'], p))


if __name__ == "__main__":
    main()
