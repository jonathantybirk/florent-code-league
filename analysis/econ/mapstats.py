"""Offline analysis of the 15 shipped maps from team A's perspective."""
import sys
from collections import deque
sys.path.insert(0, 'analysis/econ')
from maplib import EMPTY, ORE, WALL, read_map

CORES = {  # measured from the engine, team A -> team B (NW corner of 2x2 footprint)
    "atoll": ((2, 14), (14, 2)), "aurora": ((3, 22), (21, 2)),
    "crossfire": ((2, 11), (12, 3)), "duel": ((1, 8), (9, 2)),
    "fjord": ((2, 15), (16, 3)), "hive": ((2, 20), (21, 3)),
    "longship": ((2, 8), (24, 8)), "pinch": ((2, 2), (2, 14)),
    "quarry": ((2, 2), (20, 20)), "runestone": ((2, 11), (20, 11)),
    "skerry": ((2, 17), (18, 3)), "sprint": ((1, 1), (7, 7)),
    "strait": ((2, 2), (2, 22)), "twins": ((2, 2), (2, 17)),
    "vault": ((2, 19), (20, 3)),
}
D8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
D4 = [(0, -1), (1, 0), (0, 1), (-1, 0)]


def footprint(c):
    return {(c[0] + dx, c[1] + dy) for dx in (0, 1) for dy in (0, 1)}


def bfs(rows, w, h, sources, steps, blocked):
    """Multi-source BFS over passable tiles."""
    dist = {}
    q = deque()
    for s in sources:
        dist[s] = 0
        q.append(s)
    while q:
        x, y = q.popleft()
        for dx, dy in steps:
            n = (x + dx, y + dy)
            if not (0 <= n[0] < w and 0 <= n[1] < h) or n in dist:
                continue
            if rows[n[1]][n[0]] == WALL or n in blocked:
                continue
            dist[n] = dist[(x, y)] + 1
            q.append(n)
    return dist


def analyse(name):
    w, h, rows = read_map(f"maps/{name}.map26")
    ca, cb = CORES[name]
    fa, fb = footprint(ca), footprint(cb)
    ores = [(x, y) for y in range(h) for x in range(w) if rows[y][x] == ORE]

    # Travel: 8-connected, from the ring around our footprint (spawn tiles).
    spawn = {(x + dx, y + dy) for (x, y) in fa for dx, dy in D8
             if (x + dx, y + dy) not in fa and 0 <= x + dx < w and 0 <= y + dy < h}
    spawn = {p for p in spawn if rows[p[1]][p[0]] != WALL}
    trav = bfs(rows, w, h, spawn, D8, fa | fb)
    # Conveyor route: 4-connected, from tiles orthogonally adjacent to our footprint.
    adj4 = {(x + dx, y + dy) for (x, y) in fa for dx, dy in D4
            if (x + dx, y + dy) not in fa and 0 <= x + dx < w and 0 <= y + dy < h}
    adj4 = {p for p in adj4 if rows[p[1]][p[0]] != WALL}
    conv = bfs(rows, w, h, adj4, D4, fa | fb)
    trav_b = bfs(rows, w, h, {(x + dx, y + dy) for (x, y) in fb for dx, dy in D8
                              if (x + dx, y + dy) not in fb and 0 <= x + dx < w
                              and 0 <= y + dy < h and rows[y + dy][x + dx] != WALL},
                 D8, fa | fb)

    out = []
    for o in ores:
        # Stand/route from a tile adjacent to the ore (ore tile itself gets the harvester).
        t = min((trav[n] for n in [(o[0] + dx, o[1] + dy) for dx, dy in D8] if n in trav),
                default=None)
        c = min((conv[n] for n in [(o[0] + dx, o[1] + dy) for dx, dy in D4] if n in conv),
                default=None)
        tb = min((trav_b[n] for n in [(o[0] + dx, o[1] + dy) for dx, dy in D8] if n in trav_b),
                 default=None)
        if t is None or c is None:
            continue
        out.append({"ore": o, "travel": t + 1, "conveyors": c + 1,
                    "mine": tb is None or t <= tb})
    out.sort(key=lambda r: r["travel"])
    return w, h, ores, out


if __name__ == "__main__":
    print(f"{'map':<11}{'size':>8}{'ore':>5}{'mine':>5}  travel-to-ore (mine only)      conveyors")
    tot = []
    for name in CORES:
        w, h, ores, rs = analyse(name)
        mine = [r for r in rs if r["mine"]]
        tot.append((name, mine))
        print(f"{name:<11}{f'{w}x{h}':>8}{len(ores):>5}{len(mine):>5}  "
              f"{str([r['travel'] for r in mine]):<30} {[r['conveyors'] for r in mine]}")
    print()
    ns = [len(m) for _, m in tot]
    print(f"deposits on my side: min={min(ns)} median={sorted(ns)[len(ns)//2]} max={max(ns)}")
