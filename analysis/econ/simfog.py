"""Tick-level simulation of the opening under fog, for N builders.

Bot-independent: it uses only engine-verified mechanics and a competent generic
policy (build the nearest routable known deposit, otherwise walk to the nearest
unseen tile). It answers the question the planner cannot: how much of a
builder's value is scouting rather than construction?
"""
import sys
from collections import deque
sys.path.insert(0, 'analysis/econ')
from maplib import ORE, WALL, read_map
from mapstats import CORES, D8, footprint
from planner import PER_LINE, route_to_core

MAXR = 1000
BOT_VIS, CORE_VIS = 20, 36
VIS_OFF = [(dx, dy) for dx in range(-5, 6) for dy in range(-5, 6)
           if dx * dx + dy * dy <= BOT_VIS]
CORE_OFF = [(dx, dy) for dx in range(-7, 8) for dy in range(-7, 8)
            if dx * dx + dy * dy <= CORE_VIS]


def bfs_step(w, h, rows, src, goals, blocked):
    """First step and distance of a shortest 8-connected path to any goal tile."""
    if src in goals:
        return None, 0
    prev, q = {src: None}, deque([src])
    found = None
    while q:
        c = q.popleft()
        if c in goals and c != src:
            found = c
            break
        for dx, dy in D8:
            n = (c[0] + dx, c[1] + dy)
            if n in prev or not (0 <= n[0] < w and 0 <= n[1] < h):
                continue
            if rows[n[1]][n[0]] == WALL or n in blocked:
                continue
            prev[n] = c
            q.append(n)
    if found is None:
        return None, None
    path, c = [], found
    while c is not None:
        path.append(c)
        c = prev[c]
    path.reverse()
    return path[1], len(path) - 1


def simulate(name, nb, spawn_gap=1):
    w, h, rows = read_map(f"maps/{name}.map26")
    ca, cb = CORES[name]
    fa, fb = footprint(ca), footprint(cb)
    ores = {(x, y) for y in range(h) for x in range(w) if rows[y][x] == ORE}
    static_block = fa | fb

    seen = set()
    for (cx, cy) in fa:                       # the core's own vision, from round 0
        for dx, dy in CORE_OFF:
            p = (cx + dx, cy + dy)
            if 0 <= p[0] < w and 0 <= p[1] < h:
                seen.add(p)

    spawn = [p for p in ((x + dx, y + dy) for (x, y) in fa for dx, dy in D8)
             if p not in fa and 0 <= p[0] < w and 0 <= p[1] < h and rows[p[1]][p[0]] != WALL]
    bots = []
    used, harv, nlines = {}, {}, 0
    built, connected = set(), []

    for r in range(MAXR):
        if len(bots) < nb and r % spawn_gap == 0 and r // spawn_gap == len(bots):
            bots.append({"pos": spawn[0], "job": None, "born": r})
        for b in bots:
            if b["born"] >= r:
                continue
            for dx, dy in VIS_OFF:            # reveal from the current position
                p = (b["pos"][0] + dx, b["pos"][1] + dy)
                if 0 <= p[0] < w and 0 <= p[1] < h:
                    seen.add(p)
        occupied = {b["pos"] for b in bots}
        for b in bots:
            if b["born"] >= r:
                continue
            blocked = static_block | built | (occupied - {b["pos"]})
            if b["job"] is None:
                known = [o for o in (ores & seen) - built
                         if not any(j and j["ore"] == o for j in
                                    (x["job"] for x in bots))]
                best = None
                for o in known:
                    res = route_to_core(w, h, rows, fa, o, used, nlines, harv,
                                        static_block | (ores - {o}))
                    if res is None:
                        continue
                    tiles, join, full = res
                    _, d = bfs_step(w, h, rows, b["pos"],
                                    {(o[0] + dx, o[1] + dy) for dx, dy in D8
                                     if 0 <= o[0] + dx < w and 0 <= o[1] + dy < h},
                                    blocked)
                    if d is None:
                        continue
                    if best is None or d + len(tiles) < best[0]:
                        best = (d + len(tiles), o, tiles, join)
                if best is not None:
                    _, o, tiles, join = best
                    if join is None:
                        nlines += 1
                        lid = nlines
                        harv[lid] = 0
                    else:
                        lid = join
                    harv[lid] += 1
                    for t in tiles:
                        used[t] = lid
                    b["job"] = {"ore": o, "tiles": tiles, "stage": "goto", "i": 0}
                    built.add(o)
                else:                          # explore toward the nearest unseen tile
                    unseen = {(x, y) for y in range(h) for x in range(w)
                              if (x, y) not in seen and rows[y][x] != WALL}
                    if unseen:
                        s, _ = bfs_step(w, h, rows, b["pos"], unseen, blocked)
                        if s:
                            b["pos"] = s
                    continue
            j = b["job"]
            if j["stage"] == "goto":
                goals = {(j["ore"][0] + dx, j["ore"][1] + dy) for dx, dy in D8
                         if 0 <= j["ore"][0] + dx < w and 0 <= j["ore"][1] + dy < h}
                if b["pos"] in goals:
                    j["stage"] = "lay"          # harvester built this round
                    j["built_at"] = r
                    if not j["tiles"]:
                        connected.append((r + 1, j["ore"]))
                        b["job"] = None
                    continue
                s, _ = bfs_step(w, h, rows, b["pos"], goals, blocked)
                if s:
                    b["pos"] = s
            elif j["stage"] == "lay":
                tgt = j["tiles"][j["i"]]
                if b["pos"] == tgt:
                    j["i"] += 1                 # conveyor built, then step on
                    if j["i"] >= len(j["tiles"]):
                        connected.append((j["built_at"] + len(j["tiles"]) + 1, j["ore"]))
                        b["job"] = None
                        continue
                    tgt = j["tiles"][j["i"]]
                s, _ = bfs_step(w, h, rows, b["pos"], {tgt}, blocked)
                if s:
                    b["pos"] = s
    revenue = sum(2.5 * (MAXR - c) for c, _ in connected if c < MAXR)
    return revenue, len(connected), len(ores), sorted(connected)


if __name__ == "__main__":
    nbs = [1, 2, 3, 4]
    print(f"{'map':<11}" + "".join(f"{f'NB={n}':>10}" for n in nbs) + "    ore")
    tot = {n: 0.0 for n in nbs}
    for m in CORES:
        vs = []
        for n in nbs:
            rev, c, t, _ = simulate(m, n)
            vs.append(rev)
            tot[n] += rev
        print(f"{m:<11}" + "".join(f"{v:>10.0f}" for v in vs) + f"    {t}")
    print(f"{'TOTAL':<11}" + "".join(f"{tot[n]:>10.0f}" for n in nbs))
    print(f"{'vs NB=1':<11}" + "".join(f"{100*tot[n]/tot[1]-100:>9.1f}%" for n in nbs))
