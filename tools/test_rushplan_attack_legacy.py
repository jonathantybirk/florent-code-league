#!/usr/bin/env python
"""Independent static re-check of bot/rushplan.py against bot/atlas.py.

Deliberately does NOT reuse tools/build_rushplan.py's helpers -- it re-derives the geometry so a
bug in the generator does not validate itself. The authoritative evidence is still the live
30-match sweep, but this catches a bad regeneration in a second.

Run:  .\\.venv\\Scripts\\python.exe tools\\test_rushplan.py
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bot"))

import atlas      # noqa: E402
import rushplan   # noqa: E402

VEC = {"NORTH": (0, -1), "NORTHEAST": (1, -1), "EAST": (1, 0), "SOUTHEAST": (1, 1),
       "SOUTH": (0, 1), "SOUTHWEST": (-1, 1), "WEST": (-1, 0), "NORTHWEST": (-1, -1)}
CARD = ((0, -1), (1, 0), (0, 1), (-1, 0))

fails = []


def bad(key, msg):
    fails.append("%s/%s: %s" % (key[0], key[1], msg))


def main():
    assert len(rushplan.PLANS) == 30, "expected 30 (map, team) entries"
    assert set(rushplan.PLANS) == set(rushplan.RECOMMENDATION)

    zero_pairs = 0
    zero_maps = set()

    for key in sorted(rushplan.PLANS):
        name, team = key
        p = rushplan.PLANS[key]
        rec = atlas.by_name(name, team)
        if rec is None:
            bad(key, "no atlas record")
            continue
        w, h = rec["width"], rec["height"]
        walls, ore = rec["walls"], set(rec["ore"])
        own, enemy = set(rec["own_core_tiles"]), set(rec["enemy_core_tiles"])
        cores = own | enemy

        def open_tile(q):
            return 0 <= q[0] < w and 0 <= q[1] < h and q not in walls and q not in cores

        # --- 1. the ray genuinely bears on the enemy Core, unobstructed
        g, d = p["gunner"], VEC[p["facing"]]
        built = []
        k = 1
        while (k * d[0]) ** 2 + (k * d[1]) ** 2 <= 13:
            built.append((g[0] + k * d[0], g[1] + k * d[1]))
            k += 1
        hit = None
        for i, t in enumerate(built):
            if not (0 <= t[0] < w and 0 <= t[1] < h):
                break
            if t in enemy:
                hit = i + 1
                break
            if t in walls or t in cores:
                break
        if hit is None:
            bad(key, "ray from %r facing %s never reaches the enemy Core" % (g, p["facing"]))
            continue
        if hit != p["range"] or tuple(built[:hit]) != tuple(p["ray"]):
            bad(key, "stored ray %r != derived %r" % (p["ray"], tuple(built[:hit])))
        if not open_tile(g):
            bad(key, "gunner tile %r is not buildable" % (g,))

        # --- 2. the harvester is on real ore and never blocks the shot
        if p["ore"] not in ore:
            bad(key, "harvester tile %r is not ORE_TITANIUM" % (p["ore"],))
        blockers = set(p["ray"])
        if p["ore"] in blockers:
            bad(key, "harvester sits in its own gunner's ray")
        for c, _f in p["conveyors"]:
            if c in blockers:
                bad(key, "conveyor %r sits in the ray" % (c,))

        # --- 3. zero_conveyor is honest
        adjacent = abs(p["ore"][0] - g[0]) + abs(p["ore"][1] - g[1]) == 1
        if p["zero_conveyor"] != (len(p["conveyors"]) == 0):
            bad(key, "zero_conveyor flag disagrees with the conveyor list")
        if p["zero_conveyor"] and not adjacent:
            bad(key, "zero_conveyor but the ore is not orthogonally adjacent to the gunner")
        if p["zero_conveyor"]:
            zero_pairs += 1
            zero_maps.add(name)

        # --- 4. the chain is contiguous and actually points at the gunner
        if p["conveyors"]:
            chain = [c for c, _ in reversed(p["conveyors"])]   # ore side -> gunner side
            seq = [p["ore"]] + chain + [g]
            for a, b in zip(seq, seq[1:]):
                if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1:
                    bad(key, "chain hop %r -> %r is not orthogonal" % (a, b))
            for c, f in p["conveyors"]:
                nxt = (c[0] + VEC[f][0], c[1] + VEC[f][1])
                if nxt not in seq[seq.index(c) + 1:]:
                    bad(key, "conveyor %r facing %s does not point down the chain" % (c, f))

        # --- 5. the route is walkable and the arithmetic adds up
        route = p["route"]
        tiles = [g] + [c for c, _ in p["conveyors"]] + [p["ore"]]
        if [r[1] for r in route] != tiles:
            bad(key, "route build order %r != gunner/conveyors/ore %r"
                % ([r[1] for r in route], tiles))
        ring = set()
        for (cx, cy) in own:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = (cx + dx, cy + dy)
                    if q not in own and open_tile(q):
                        ring.add(q)
        t = None
        cur = None
        placed = set()
        for i, (kind, tile, _f, stand) in enumerate(route):
            if abs(stand[0] - tile[0]) + abs(stand[1] - tile[1]) != 1:
                bad(key, "stand %r is not orthogonally adjacent to %r" % (stand, tile))
            if stand in blockers or stand in placed or not open_tile(stand):
                bad(key, "stand %r is blocked" % (stand,))
            blocked = frozenset() if i == 0 else (blockers | placed)
            src = ring if i == 0 else {cur}
            dist = bfs(src, open_tile, blocked)
            if stand not in dist:
                bad(key, "stand %r unreachable at step %d" % (stand, i))
                break
            t = dist[stand] + 1 if t is None else t + dist[stand] + 1
            if i == 0 and dist[stand] != p["walk"]:
                bad(key, "walk %d != BFS %d" % (p["walk"], dist[stand]))
            cur = stand
            placed.add(tile)
        else:
            if t != p["t_harvester"]:
                bad(key, "t_harvester %d != simulated %d" % (p["t_harvester"], t))
            shot = p["t_harvester"] + len(p["conveyors"]) + 1
            if shot != p["first_shot"]:
                bad(key, "first_shot %d != %d" % (p["first_shot"], shot))
            if p["kill_turn"] != p["first_shot"] + 50:
                bad(key, "kill_turn %d != first_shot + 50" % p["kill_turn"])

        # --- 6. cost with global scaling
        scale, total = 1.0, 0
        for base, bump in [(30, 0.20), (10, 0.10)] + \
                          [(3, 0.01)] * len(p["conveyors"]) + [(20, 0.05)]:
            total += int(scale * base + 1e-9)
            scale += bump
        if total != p["cost"]:
            bad(key, "cost %d != %d" % (p["cost"], total))

        v = rushplan.RECOMMENDATION[key]
        want = "RUSH" if p["kill_turn"] <= 70 else ("HYBRID" if p["kill_turn"] <= 85 else "ECON")
        if v != want:
            bad(key, "recommendation %s != %s for kill_turn %d" % (v, want, p["kill_turn"]))

    print("zero-conveyor pairs %d/30, distinct maps %d/15 -> %s"
          % (zero_pairs, len(zero_maps), sorted(set(atlas.MAP_NAMES) - zero_maps)))
    if fails:
        print("FAIL (%d)" % len(fails))
        for f in fails:
            print("  " + f)
        return 1
    print("PASS  all 30 plans re-derive from the atlas")
    return 0


def bfs(sources, open_tile, blocked):
    dist = {}
    q = deque()
    for s in sources:
        if open_tile(s) and s not in blocked:
            dist[s] = 0
            q.append(s)
    while q:
        c = q.popleft()
        for d in CARD:
            n = (c[0] + d[0], c[1] + d[1])
            if n in dist or not open_tile(n) or n in blocked:
                continue
            dist[n] = dist[c] + 1
            q.append(n)
    return dist


if __name__ == "__main__":
    sys.exit(main())
