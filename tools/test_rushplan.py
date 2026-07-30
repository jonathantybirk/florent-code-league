#!/usr/bin/env python
"""Verify ``bot/rushplan.py`` against ``bot/atlas.py`` -- both halves, attack and defend.

The geometry here is re-derived from scratch: a test that calls the same helper the table was built
with proves nothing. Everything below recomputes rays, spawn rings, reachability and the cost ladder
independently and checks the shipped literals against them.

The authoritative evidence for the ATTACK half is still the live sweep in ``tools/verify_rush.py``
(30/30 map/team pairs ended ``core_destroyed`` on exactly the predicted turn) and for the DEFEND
half the live ``can_fire_from`` flip in ``bots/probe_barrier``. This file is the fast regression
check that catches a bad regeneration in a second.

Run:  .\\.venv\\Scripts\\python.exe tools\\test_rushplan.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOT = ROOT / "bot"
sys.path.insert(0, str(BOT))

import atlas       # noqa: E402
import rushplan    # noqa: E402

GUNNER_R2 = 13
CARD = {"NORTH": (0, -1), "EAST": (1, 0), "SOUTH": (0, 1), "WEST": (-1, 0)}
VEC = dict(CARD, NORTHEAST=(1, -1), SOUTHEAST=(1, 1), SOUTHWEST=(-1, 1), NORTHWEST=(-1, -1))
CDELTA = ((0, -1), (1, 0), (0, 1), (-1, 0))
DIAG = ((1, -1), (1, 1), (-1, 1), (-1, -1))

FAILS = []
CHECKS = [0]


def check(cond, msg):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(msg)
    return bool(cond)


# --- independently re-derived geometry --------------------------------------------------------

def passable(rec, p):
    return (0 <= p[0] < rec["width"] and 0 <= p[1] < rec["height"]
            and p not in rec["walls"]
            and p not in set(rec["own_core_tiles"])
            and p not in set(rec["enemy_core_tiles"]))


def spawn_ring(rec, core_tiles):
    """The 12 tiles at Chebyshev distance 1 from the 2x2 footprint (live-probed via can_spawn)."""
    ct = set(core_tiles)
    out = set()
    for (cx, cy) in ct:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                q = (cx + dx, cy + dy)
                if q not in ct and passable(rec, q):
                    out.add(q)
    return out


def bfs(rec, sources, blocked=frozenset()):
    dist, q = {}, deque()
    for s in sources:
        if passable(rec, s) and s not in blocked:
            dist[s] = 0
            q.append(s)
    while q:
        c = q.popleft()
        for d in CDELTA:
            n = (c[0] + d[0], c[1] + d[1])
            if n not in dist and passable(rec, n) and n not in blocked:
                dist[n] = dist[c] + 1
                q.append(n)
    return dist


def trace_ray(rec, g, d, reach):
    """Tiles the shot crosses and the tile it lands on (or None).

    A Gunner's shot stops at the first targetable tile. On an empty board the only targetable things
    are the two Cores; walls end the ray without being hit; the board edge ends it too.
    """
    cores = set(rec["own_core_tiles"]) | set(rec["enemy_core_tiles"])
    tiles = []
    for k in range(1, reach + 1):
        t = (g[0] + k * d[0], g[1] + k * d[1])
        if not (0 <= t[0] < rec["width"] and 0 <= t[1] < rec["height"]):
            return tuple(tiles), None
        if t in rec["walls"]:
            return tuple(tiles), None
        tiles.append(t)
        if t in cores:
            return tuple(tiles), t
    return tuple(tiles), None


def can_threaten(rec, g, target_tiles):
    """Could a Gunner at g hit ``target_tiles`` in ANY legal facing? Cardinal reach 3, diagonal 2."""
    for d in CDELTA:
        if trace_ray(rec, g, d, 3)[1] in target_tiles:
            return True
    for d in DIAG:
        if trace_ray(rec, g, d, 2)[1] in target_tiles:
            return True
    return False


def ladder_cost(n_conveyors):
    """G07: one global scale, cost = floor(scale * base), bump applied after each purchase."""
    scale, total = 1.0, 0
    for base, bump in [(30, 0.20), (10, 0.10)] + [(3, 0.01)] * n_conveyors + [(20, 0.05)]:
        total += int(scale * base + 1e-9)
        scale += bump
    return total


# --- tests ------------------------------------------------------------------------------------

def test_every_map_resolves():
    check(len(atlas.MAP_NAMES) == 15, "expected 15 maps, got %d" % len(atlas.MAP_NAMES))
    for name in atlas.MAP_NAMES:
        for team in ("a", "b"):
            tag = "%s/%s" % (name, team)
            p = rushplan.attack_plan(name, team)
            check(p is not None, "attack_plan(%s) is None" % tag)
            check(rushplan.recommendation(name, team) in ("RUSH", "HYBRID", "ECON"),
                  "recommendation(%s) invalid" % tag)
            check(isinstance(rushplan.deny_tiles(name, team), tuple),
                  "deny_tiles(%s) is not a tuple" % tag)


def test_attack_ray_bears_on_enemy_core():
    for name in atlas.MAP_NAMES:
        for team in ("a", "b"):
            rec = atlas.by_name(name, team)
            p = rushplan.attack_plan(name, team)
            tag = "%s/%s" % (name, team)
            if p is None:
                continue
            g, enemy = p["fire_pos"], set(rec["enemy_core_tiles"])

            check(p["facing"] in CARD, "%s facing %r is not cardinal" % (tag, p["facing"]))
            check(passable(rec, g), "%s fire_pos %r is not a legal building site" % (tag, g))
            if p["facing"] not in CARD:
                continue

            tiles, hit = trace_ray(rec, g, CARD[p["facing"]], 3)
            check(hit is not None and hit in enemy,
                  "%s ray from %r facing %s lands on %r, not the enemy Core"
                  % (tag, g, p["facing"], hit))
            if hit is None:
                continue
            r2 = (hit[0] - g[0]) ** 2 + (hit[1] - g[1]) ** 2
            check(r2 <= GUNNER_R2, "%s hits %r at r2=%d > %d" % (tag, hit, r2, GUNNER_R2))
            check(all(t not in rec["walls"] for t in tiles), "%s ray crosses a wall" % tag)
            check(all(t not in set(rec["own_core_tiles"]) for t in tiles),
                  "%s ray crosses our own Core" % tag)
            # every tile short of the target must be empty ground, or the shot stops there
            for t in tiles[:-1]:
                check(t not in enemy, "%s ray reaches the Core earlier than reported" % tag)


def test_attack_supply_and_arithmetic():
    for name in atlas.MAP_NAMES:
        for team in ("a", "b"):
            rec = atlas.by_name(name, team)
            p, full = rushplan.attack_plan(name, team), rushplan.plan(name, team)
            tag = "%s/%s" % (name, team)
            if p is None or full is None:
                continue
            g, o = p["fire_pos"], p["ore"]
            ray = set(full["ray"])

            check(o in set(rec["ore"]), "%s ore %r is not an ORE_TITANIUM tile" % (tag, o))
            check(o not in ray, "%s the harvester sits in its own gunner's lane" % tag)
            check(g not in set(rec["ore"]), "%s the turret sits on ore" % tag)
            check(p["zero_conveyor"] == (len(full["conveyors"]) == 0),
                  "%s zero_conveyor disagrees with the conveyor list" % tag)
            if p["zero_conveyor"]:
                check(abs(o[0] - g[0]) + abs(o[1] - g[1]) == 1,
                      "%s zero_conveyor but ore %r is not orthogonally adjacent to %r"
                      % (tag, o, g))
            for c, _f in full["conveyors"]:
                check(c not in ray, "%s conveyor %r sits in the lane" % (tag, c))

            # conveyor chain contiguous and pointing at the turret
            if full["conveyors"]:
                seq = [o] + [c for c, _ in reversed(full["conveyors"])] + [g]
                for a, b in zip(seq, seq[1:]):
                    check(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1,
                          "%s chain hop %r -> %r is not orthogonal" % (tag, a, b))
                for c, f in full["conveyors"]:
                    nxt = (c[0] + VEC[f][0], c[1] + VEC[f][1])
                    check(nxt in seq[seq.index(c) + 1:],
                          "%s conveyor %r facing %s does not point down the chain" % (tag, c, f))

            check(p["ti_cost"] == ladder_cost(len(full["conveyors"])),
                  "%s ti_cost %d != scaled ladder %d"
                  % (tag, p["ti_cost"], ladder_cost(len(full["conveyors"]))))
            check(p["kill_turn"] == full["first_shot"] + 50,
                  "%s kill_turn %d != first_shot + 50" % (tag, p["kill_turn"]))
            check(full["first_shot"] == full["t_harvester"] + len(full["conveyors"]) + 1,
                  "%s first_shot does not follow the harvester + transit" % tag)


def test_attack_route_is_walkable():
    """Re-simulate the build schedule. Only the Gunner blocks movement and only the FINAL stand
    must be out of the lane -- before the Harvester exists the turret has no ammo, so a body in the
    lane blocks nothing."""
    for name in atlas.MAP_NAMES:
        for team in ("a", "b"):
            rec = atlas.by_name(name, team)
            full = rushplan.plan(name, team)
            tag = "%s/%s" % (name, team)
            if full is None:
                continue
            ring = spawn_ring(rec, rec["own_core_tiles"])
            check(len(ring) == 12, "%s spawn ring has %d tiles, expected 12" % (tag, len(ring)))
            route, ray = full["route"], set(full["ray"])
            tiles = [full["gunner"]] + [c for c, _ in full["conveyors"]] + [full["ore"]]
            check([r[1] for r in route] == tiles, "%s route order != gunner/conveyors/ore" % tag)

            t, cur, placed = None, None, set()
            ok = True
            for i, (_kind, tile, _f, stand) in enumerate(route):
                check(abs(stand[0] - tile[0]) + abs(stand[1] - tile[1]) == 1,
                      "%s stand %r not orthogonally adjacent to %r" % (tag, stand, tile))
                check(passable(rec, stand) and stand not in placed,
                      "%s stand %r is occupied or impassable" % (tag, stand))
                blocked = frozenset() if i == 0 else frozenset([full["gunner"]]) - {stand}
                d = bfs(rec, ring if i == 0 else {cur}, blocked)
                if stand not in d:
                    check(False, "%s stand %r unreachable at step %d" % (tag, stand, i))
                    ok = False
                    break
                t = d[stand] + 1 if t is None else t + d[stand] + 1
                if i == 0:
                    check(d[stand] == full["walk"],
                          "%s walk %d != BFS %d" % (tag, full["walk"], d[stand]))
                cur, _ = stand, placed.add(tile)
            if ok:
                check(t == full["t_harvester"],
                      "%s t_harvester %d != simulated %d" % (tag, full["t_harvester"], t))
                check(route[-1][3] not in ray,
                      "%s the builder is parked in its own turret's lane" % tag)


def test_deny_tiles_never_block_our_spawn_ring():
    for name in atlas.MAP_NAMES:
        for team in ("a", "b"):
            rec = atlas.by_name(name, team)
            tag = "%s/%s" % (name, team)
            tiles = rushplan.deny_tiles(name, team)
            ring = spawn_ring(rec, rec["own_core_tiles"])
            own = set(rec["own_core_tiles"])
            p = rushplan.attack_plan(name, team)

            check(len(set(tiles)) == len(tiles), "%s deny list has duplicates" % tag)
            for t in tiles:
                check(t not in ring,
                      "%s deny tile %r is inside our own 12-tile spawn ring" % (tag, t))
                check(t not in own, "%s deny tile %r is on our Core footprint" % (tag, t))
                check(passable(rec, t), "%s deny tile %r is not a legal Barrier site" % (tag, t))
                check(t not in set(rec["ore"]), "%s deny tile %r sits on ore" % (tag, t))
                check(can_threaten(rec, t, own),
                      "%s deny tile %r cannot actually shoot our Core" % (tag, t))

            # never inside our own turret's firing lane
            if p is not None and p["facing"] in CARD:
                lane = set(trace_ray(rec, p["fire_pos"], CARD[p["facing"]], 3)[0])
                lane |= {p["fire_pos"], p["ore"]}
                for t in tiles:
                    check(t not in lane,
                          "%s deny tile %r sits in our own turret's lane" % (tag, t))

            # barriering the whole list must leave the ring usable and still connected to our ore
            free = ring - set(tiles)
            check(len(free) >= 8,
                  "%s the deny list would leave only %d spawn tiles" % (tag, len(free)))
            reach = bfs(rec, free, blocked=set(tiles))
            check(all(f in reach for f in free), "%s the deny list splits our spawn ring" % tag)
            before = bfs(rec, ring)
            for o in rec["ore"]:
                if o in before:
                    check(o in reach, "%s the deny list seals off reachable ore %r" % (tag, o))


def test_deny_ranking_is_as_documented():
    """Ore-adjacent first, then nearest to the enemy spawn."""
    for name in atlas.MAP_NAMES:
        for team in ("a", "b"):
            rec = atlas.by_name(name, team)
            tiles = rushplan.deny_tiles(name, team)
            tag = "%s/%s" % (name, team)
            ore = set(rec["ore"])
            from_enemy = bfs(rec, spawn_ring(rec, rec["enemy_core_tiles"]))
            keys = [(not any((t[0] + d[0], t[1] + d[1]) in ore for d in CDELTA),
                     from_enemy.get(t, 10 ** 6)) for t in tiles]
            check(all(a[0] <= b[0] for a, b in zip(keys, keys[1:])),
                  "%s ore-adjacent deny tiles are not ranked first" % tag)
            for a, b in zip(keys, keys[1:]):
                if a[0] == b[0]:
                    check(a[1] <= b[1],
                          "%s deny tiles not ordered by distance from the enemy spawn" % tag)


def test_never_raises_on_junk():
    junk = [("nosuchmap", "a"), ("", ""), (None, None), ("atoll", "zzz"), ("atoll", None),
            (123, 456), ("atoll", "Team.A"), ("atoll", "Team.B"), ("atoll", "A"), ("atoll", "B"),
            (("tuple",), object()), ("atoll", 0), ([], []), ("sprint", "team.b")]
    for m, t in junk:
        try:
            p = rushplan.attack_plan(m, t)
            d = rushplan.deny_tiles(m, t)
            r = rushplan.recommendation(m, t)
        except Exception as exc:            # noqa: BLE001
            CHECKS[0] += 1
            FAILS.append("raised on (%r, %r): %r" % (m, t, exc))
            continue
        check(p is None or isinstance(p, dict), "attack_plan(%r,%r) bad type" % (m, t))
        check(isinstance(d, tuple), "deny_tiles(%r,%r) is not a tuple" % (m, t))
        check(r in ("RUSH", "HYBRID", "ECON"), "recommendation(%r,%r) = %r" % (m, t, r))
    for form in ("a", "A", "Team.A"):
        check(rushplan.attack_plan("atoll", form) == rushplan.attack_plan("atoll", "a"),
              "team form %r does not resolve like 'a'" % form)
    for form in ("b", "B", "Team.B"):
        check(rushplan.attack_plan("atoll", form) == rushplan.attack_plan("atoll", "b"),
              "team form %r does not resolve like 'b'" % form)
    check(rushplan.attack_plan("nosuchmap", "a") is None, "unknown map should give None")
    check(rushplan.deny_tiles("nosuchmap", "a") == (), "unknown map should give ()")
    check(rushplan.recommendation("nosuchmap", "a") == "ECON", "unknown map should give ECON")


def test_interface_shape():
    want = {"fire_pos", "facing", "ore", "walk", "kill_turn", "ti_cost", "zero_conveyor"}
    p = rushplan.attack_plan("sprint", "a")
    check(p is not None and set(p) == want,
          "attack_plan keys = %r, want %r" % (set(p) if p else None, want))
    if not p:
        return
    check(isinstance(p["fire_pos"], tuple) and len(p["fire_pos"]) == 2, "fire_pos shape")
    check(isinstance(p["ore"], tuple) or p["ore"] is None, "ore shape")
    for f in ("walk", "kill_turn", "ti_cost"):
        check(isinstance(p[f], int) and not isinstance(p[f], bool), "%s is not an int" % f)
    check(isinstance(p["zero_conveyor"], bool), "zero_conveyor is not a bool")
    check(p is not rushplan.attack_plan("sprint", "a"),
          "attack_plan returns a shared mutable dict")
    # back-compatible surface used by the sibling tooling
    check(len(rushplan.PLANS) == 30, "PLANS should hold 30 entries")
    check(set(rushplan.PLANS) == set(rushplan.RECOMMENDATION), "PLANS/RECOMMENDATION key mismatch")


def test_import_time():
    """Cold import in a fresh interpreter with bytecode caching OFF -- the sandbox's real cost.

    A stray __pycache__ in a bot directory makes the engine run that bot inert (G30) and the engine
    writes one itself unless PYTHONDONTWRITEBYTECODE is set (G33), so the honest measurement is the
    uncached one, paid once per unit per match (G20: every unit gets its own sub-interpreter).
    """
    code = ("import sys, time\n"
            "sys.dont_write_bytecode = True\n"
            "sys.path.insert(0, %r)\n"
            "t = time.perf_counter(); import rushplan; a = (time.perf_counter()-t)*1000\n"
            "t = time.perf_counter(); import atlas;    b = (time.perf_counter()-t)*1000\n"
            "print('%%.4f %%.4f' %% (a, b))\n" % str(BOT))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    best = None
    for _ in range(5):
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        if r.returncode != 0:
            check(False, "cold import failed: %s" % r.stderr.strip()[:200])
            return
        ms = tuple(float(x) for x in r.stdout.split())
        best = ms if best is None else (min(best[0], ms[0]), min(best[1], ms[1]))
    print("      cold import (no .pyc): rushplan %.2f ms | atlas %.2f ms   [best of 5]" % best)
    check(best[0] < 25.0, "rushplan cold import %.2f ms blows the 25 ms budget" % best[0])

    t0 = time.perf_counter()
    n = 20000
    for _ in range(n):
        rushplan.attack_plan("sprint", "a")
        rushplan.deny_tiles("sprint", "a")
        rushplan.recommendation("sprint", "a")
    us = (time.perf_counter() - t0) / n * 1e6
    print("      per-turn lookup cost: %.2f us for all three calls" % us)
    check(us < 50.0, "lookups cost %.2f us against a 10 ms turn budget" % us)


def main():
    print("verifying bot/rushplan.py against bot/atlas.py (geometry re-derived independently)\n")
    tests = (test_every_map_resolves,
             test_attack_ray_bears_on_enemy_core,
             test_attack_supply_and_arithmetic,
             test_attack_route_is_walkable,
             test_deny_tiles_never_block_our_spawn_ring,
             test_deny_ranking_is_as_documented,
             test_never_raises_on_junk,
             test_interface_shape,
             test_import_time)
    for fn in tests:
        n0, f0 = CHECKS[0], len(FAILS)
        fn()
        print("  %-42s %5d checks   %s"
              % (fn.__name__, CHECKS[0] - n0,
                 "ok" if len(FAILS) == f0 else "%d FAILED" % (len(FAILS) - f0)))

    zc = sum(1 for n in atlas.MAP_NAMES for t in ("a", "b")
             if (rushplan.attack_plan(n, t) or {}).get("zero_conveyor"))
    both = [n for n in atlas.MAP_NAMES
            if all((rushplan.attack_plan(n, t) or {}).get("zero_conveyor") for t in ("a", "b"))]
    print("\nzero-conveyor kill: %d/30 (map, team) pairs; %d/15 maps on BOTH sides"
          % (zc, len(both)))
    print("maps needing conveyors: %s" % sorted(set(atlas.MAP_NAMES) - set(both)))
    print("\n%d assertions, %d failures" % (CHECKS[0], len(FAILS)))
    for f in FAILS[:40]:
        print("  FAIL:", f)
    print("\n%s" % ("PASS" if not FAILS else "FAIL"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
