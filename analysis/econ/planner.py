"""Offline optimal-ish opening planner, using only engine-verified mechanics.

Mechanics baked in (each measured in analysis/econ, not taken from docs):
  * builder travel 1 tile/round, 8-connected
  * build and move in the same round; build target within Chebyshev 1
  * harvester -> 10 Ti per 4 rounds = 2.5 Ti/round, from first delivery
  * conveyor line laid 1 tile/round from ore back to core; the first stack
    chases the builder, so connect_round = harvest_round + len(line) + 1
  * a conveyor line carries at most 1 stack/round = 10 Ti/round = 4 harvesters
  * the cap is per line, not per core; the core has 8 orthogonal feed tiles
"""
import sys
from collections import deque
sys.path.insert(0, 'analysis/econ')
from maplib import ORE, WALL, read_map
from mapstats import CORES, D4, D8, footprint

MAXR = 1000
DIRNAME = {(0, -1): "north", (1, 0): "east", (0, 1): "south", (-1, 0): "west"}
PER_LINE = 4          # harvesters one conveyor line can carry


def load(name):
    w, h, rows = read_map(f"maps/{name}.map26")
    ca, cb = CORES[name]
    return w, h, rows, footprint(ca), footprint(cb)


def bfs(w, h, rows, sources, steps, blocked, extra_block=frozenset()):
    dist, q = {s: 0 for s in sources}, deque(sources)
    while q:
        c = q.popleft()
        for dx, dy in steps:
            n = (c[0] + dx, c[1] + dy)
            if n in dist or not (0 <= n[0] < w and 0 <= n[1] < h):
                continue
            if rows[n[1]][n[0]] == WALL or n in blocked or n in extra_block:
                continue
            dist[n] = dist[c] + 1
            q.append(n)
    return dist


def route_to_core(w, h, rows, foot, ore, used, lines, harv, blocked):
    """4-connected conveyor route from `ore` back to the core.

    Ends early on an existing line that still has spare capacity (free join).
    Returns (tiles_needing_conveyor, joined_line_id or None) or None.
    """
    def joinable(t):
        lid = used.get(t)
        return lid is not None and harv[lid] < PER_LINE

    # Free connection: already orthogonally adjacent to a line with capacity.
    for dx, dy in D4:
        t = (ore[0] + dx, ore[1] + dy)
        if joinable(t):
            return [], used[t], [ore, t]

    prev, q = {ore: None}, deque([ore])
    goal = None
    while q and goal is None:
        c = q.popleft()
        for dx, dy in D4:
            n = (c[0] + dx, c[1] + dy)
            if n in prev or not (0 <= n[0] < w and 0 <= n[1] < h):
                continue
            if n in foot:
                prev[n] = c
                goal = n
                break
            if rows[n[1]][n[0]] == WALL or n in blocked:
                continue
            if n in used:
                if joinable(n):
                    prev[n] = c
                    goal = n
                    break
                continue                      # a full/foreign line is an obstacle
            prev[n] = c
            q.append(n)
    if goal is None:
        return None
    path, c = [], goal
    while c is not None:
        path.append(c)
        c = prev[c]
    path.reverse()
    if goal in foot:
        return path[1:-1], None, path         # all intermediate tiles get conveyors
    return path[1:-1], used[goal], path       # stop before the existing line tile


def plan(name, nbuilders, spawn_gap=1, own_side_only=False):
    w, h, rows, fa, fb = load(name)
    ores = [(x, y) for y in range(h) for x in range(w) if rows[y][x] == ORE]
    blocked = fa | fb
    spawn = [p for p in ((x + dx, y + dy) for (x, y) in fa for dx, dy in D8)
             if p not in fa and 0 <= p[0] < w and 0 <= p[1] < h and rows[p[1]][p[0]] != WALL]
    trav_all = bfs(w, h, rows, set(spawn), D8, blocked)
    if own_side_only:
        spb = [p for p in ((x + dx, y + dy) for (x, y) in fb for dx, dy in D8)
               if p not in fb and 0 <= p[0] < w and 0 <= p[1] < h and rows[p[1]][p[0]] != WALL]
        tb = bfs(w, h, rows, set(spb), D8, blocked)
        ores = [o for o in ores
                if min((trav_all.get(n, 9e9) for n in adj8(o, w, h)), default=9e9)
                <= min((tb.get(n, 9e9) for n in adj8(o, w, h)), default=9e9)]

    ore_block = set(ores)
    blocked = blocked | ore_block
    builders = [{"pos": None, "avail": None, "jobs": []} for _ in range(nbuilders)]
    for i, b in enumerate(builders):
        b["avail"] = i * spawn_gap + 1        # spawned at round i*gap, acts the round after
        b["pos"] = spawn[0]
    used, lines, harv = {}, 0, {}
    remaining = set(ores)
    events = []

    while remaining:
        best = None
        for bi, b in enumerate(builders):
            # travel may pass over not-yet-built ore, but not over built harvesters
            dist = bfs(w, h, rows, {b["pos"]}, D8, (blocked - remaining) | fa | fb)
            for o in remaining:
                t = min((dist.get(n, None) for n in adj8(o, w, h) if n in dist), default=None)
                if t is None:
                    continue
                r = route_to_core(w, h, rows, fa, o, used, lines, harv,
                                  blocked - {o})
                if r is None:
                    continue
                tiles, join, full = r
                finish = b["avail"] + t + 1 + len(tiles)
                connect = b["avail"] + t + 1 + len(tiles) + 1
                if best is None or finish < best[0]:
                    best = (finish, connect, bi, o, tiles, join, t, full)
        if best is None:
            break
        finish, connect, bi, o, tiles, join, t, full = best
        if connect >= MAXR:
            break
        b = builders[bi]
        if join is None:
            lines += 1
            lid = lines
            harv[lid] = 0
        else:
            lid = join
        for tt in tiles:
            used[tt] = lid
        harv[lid] += 1
        facings = []
        for i, tt in enumerate(tiles):
            nxt = tiles[i + 1] if i + 1 < len(tiles) else full[-1]
            facings.append([tt[0], tt[1], DIRNAME[(nxt[0] - tt[0], nxt[1] - tt[1])]])
        b["jobs"].append({"ore": list(o), "lay": facings, "lid": lid})
        b["avail"] = finish
        b["pos"] = tiles[-1] if tiles else o
        remaining.discard(o)
        events.append((connect, o, lid, len(tiles)))

    revenue = sum(2.5 * (MAXR - c) for c, _, _, _ in events)
    return {"map": name, "nb": nbuilders, "events": events, "revenue": revenue,
            "lines": lines, "connected": len(events), "total_ore": len(ores),
            "builders": builders}


def adj8(o, w, h):
    return [(o[0] + dx, o[1] + dy) for dx, dy in D8
            if 0 <= o[0] + dx < w and 0 <= o[1] + dy < h]


if __name__ == "__main__":
    maps = list(CORES)
    print(f"{'map':<11}" + "".join(f"{f'NB={n}':>10}" for n in range(1, 7)) + "   best")
    tot = {n: 0.0 for n in range(1, 7)}
    for m in maps:
        vals = []
        for n in range(1, 7):
            p = plan(m, n)
            # subtract the titanium spent on builders/harvesters/conveyors is
            # second-order here; revenue dominates. Report gross delivered.
            vals.append(p["revenue"])
            tot[n] += p["revenue"]
        best = 1 + max(range(6), key=lambda i: vals[i])
        print(f"{m:<11}" + "".join(f"{v:>10.0f}" for v in vals) + f"   {best}")
    print(f"{'TOTAL':<11}" + "".join(f"{tot[n]:>10.0f}" for n in range(1, 7)))
    b = tot[1]
    print(f"{'vs NB=1':<11}" + "".join(f"{100*tot[n]/b-100:>9.1f}%" for n in range(1, 7)))
