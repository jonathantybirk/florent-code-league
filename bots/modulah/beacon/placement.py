# GENERATED from bots/modulah/lib/placement.py -- edit that file, not this copy.
"""Where to put a turret, and why that is a covering problem.

Baseline: `steward_hardened_reinforced._aligned_turret_site` /
`_build_basic_gunner`. Those are TARGET-driven -- a seat is accepted only when
`can_fire_from` confirms a live firing solution against a specific enemy,
"never a hopeful compass bearing" -- and they carry two hard refusals that were
measured, not reasoned:

  * never build in a friendly turret's firing lane (`_preserves_friendly_turret_lanes`);
  * never seat a turret on a tile already under an enemy ray. Refused outright
    rather than ranked down, because a turret fires one ray of eight, so seven
    directions are always free and walking to a clean seat is cheap.

Both are kept here verbatim in spirit. What is different is the third question.
Steward answers "where can I shoot this enemy from", which is right for
engaging. It does not answer "where should a turret stand before anyone
arrives", and a home turret built at a bearing nothing walks past is 20 Ti
doing nothing for the rest of the game.

The value of a defensive seat
-----------------------------
An attacker heading for our Core takes a shortest path to it. So a tile is
worth covering in proportion to how many of those shortest paths cross it --
betweenness on the approach graph. That is a computed quantity, not a tuned
decay: a tile in a one-tile corridor carries every path through it and scores
enormously; a tile in open ground carries almost none and scores near zero.

This is why the module holds no distance-falloff constant. An earlier version
weighted tiles by 1/(1+d) from the Core, which produces confident numbers with
nothing behind them -- it cannot tell a corridor from a plaza, which is the
entire question.

Coverage itself always comes from the engine
--------------------------------------------
Ray tiles come from `get_attackable_tiles_from`, exactly as steward's
`_turret_cover` does, rather than from re-derived geometry. It cannot drift
from the engine across a balance patch, and it already accounts for walls. The
arithmetic form in geometry.can_ray_reach stays, but only as the cheap
pre-filter that decides which candidates are worth an engine call.
"""

from __future__ import annotations

from collections import deque

from fcode import EntityType, GameError, Position

from geometry import RAY_LEN, COMPASS, building_at, in_bounds

# How far out an approach is modelled. A Sentinel reaches 5 tiles along a
# cardinal, so ground beyond this cannot be covered from home at all and only
# dilutes the comparison.
APPROACH_RADIUS_SQ = 36


def _passable(ct, pos: Position) -> bool:
    try:
        return ct.is_tile_passable(pos)
    except GameError:
        return False


def approach_betweenness(ct, footprint) -> dict[tuple[int, int], float]:
    """Share of shortest attack paths into the Core that cross each tile.

    Two passes over the approach region:

      1. BFS outward from the footprint gives every tile its distance to the
         Core, and `ways[t]` -- the number of distinct shortest paths from t to
         the Core -- accumulated from its already-closer neighbours.
      2. A reverse sweep, farthest first, pushes each tile's traffic down onto
         the closer neighbours that lie on its shortest paths, split in
         proportion to `ways`.

    The result is normalised traffic: a chokepoint every route must use
    approaches 1.0, a tile in the open approaches 0. No tuned constants.
    """
    foot = {(f.x, f.y) for f in footprint}
    dist: dict[tuple[int, int], int] = {f: 0 for f in foot}
    ways: dict[tuple[int, int], float] = {f: 1.0 for f in foot}
    order: list[tuple[int, int]] = []

    q = deque(foot)
    while q:
        cur = q.popleft()
        order.append(cur)
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nxt = (cur[0] + dx, cur[1] + dy)
            p = Position(*nxt)
            if not in_bounds(ct, p):
                continue
            if min(f.distance_squared(p) for f in footprint) > APPROACH_RADIUS_SQ:
                continue
            if nxt not in foot and not _passable(ct, p):
                continue
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1
                ways[nxt] = 0.0
                q.append(nxt)
            if dist[nxt] == dist[cur] + 1:
                ways[nxt] += ways[cur]

    # Every frontier tile is one unit of incoming attacker traffic; push it
    # inward along shortest paths.
    traffic = {t: 1.0 for t in dist if t not in foot}
    for cur in reversed(order):
        if cur in foot or not traffic.get(cur):
            continue
        closer = [
            (cur[0] + dx, cur[1] + dy)
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0))
            if dist.get((cur[0] + dx, cur[1] + dy), 10**9) == dist[cur] - 1
        ]
        total = sum(ways[c] for c in closer) or 1.0
        for c in closer:
            traffic[c] = traffic.get(c, 0.0) + traffic[cur] * ways[c] / total

    peak = max(traffic.values(), default=1.0) or 1.0
    return {t: v / peak for t, v in traffic.items() if t not in foot}


def turret_cover(ct, spot: Position, facing, kind: EntityType) -> set[tuple[int, int]]:
    """Tiles a turret at `spot` facing `facing` would cover, per the engine."""
    try:
        return {(t.x, t.y) for t in ct.get_attackable_tiles_from(spot, facing, kind)}
    except GameError:
        return set()


def friendly_turret_lanes(ct) -> dict[tuple[int, int], int]:
    """Tiles between a friendly turret and something it is currently shooting.

    Building on one of these silently disables a turret we already paid for --
    buildings block firing lines. Steward refuses such tiles outright and so
    does this.
    """
    me = ct.get_team()
    try:
        enemies = [e for e in ct.get_nearby_entities() if ct.get_team(e) != me]
    except GameError:
        return {}
    if not enemies:
        return {}

    lanes: dict[tuple[int, int], int] = {}
    for bid in ct.get_nearby_buildings():
        try:
            if ct.get_team(bid) != me:
                continue
            kind = ct.get_entity_type(bid)
            if kind not in RAY_LEN:
                continue
            origin, facing = ct.get_position(bid), ct.get_direction(bid)
        except GameError:
            continue
        covered = turret_cover(ct, origin, facing, kind)
        for eid in enemies:
            try:
                target = ct.get_position(eid)
            except GameError:
                continue
            if (target.x, target.y) not in covered:
                continue
            dx, dy = facing.delta()
            tile = (origin.x + dx, origin.y + dy)
            while tile != (target.x, target.y):
                lanes.setdefault(tile, bid)
                tile = (tile[0] + dx, tile[1] + dy)
    return lanes


def enemy_covered_tiles(ct) -> set[tuple[int, int]]:
    """Every tile a visible enemy turret could hit at its current facing.

    Used to refuse seats outright rather than rank them down: a turret fires
    one ray of eight, so a clean seat almost always exists nearby, and a turret
    that dies for nothing costs more than the walk.
    """
    me = ct.get_team()
    out: set[tuple[int, int]] = set()
    for bid in ct.get_nearby_buildings():
        try:
            if ct.get_team(bid) == me:
                continue
            kind = ct.get_entity_type(bid)
            if kind not in RAY_LEN:
                continue
            out |= turret_cover(ct, ct.get_position(bid), ct.get_direction(bid), kind)
        except GameError:
            continue
    return out


def best_defensive_site(ct, footprint, kind: EntityType, buildable, limit: int = 24):
    """Best (position, facing, score) for a home turret, or None.

    Scores by how much attacker traffic the ray intercepts, discounting ground
    friendly turrets already cover so the second turret picks a different
    approach instead of doubling up on the first one's corridor.

    `buildable` is supplied by the caller because legality depends on the
    Builder's own adjacency rules, which this module has no business knowing.
    Candidates are capped and pre-filtered arithmetically before any engine
    call: the platform kills a unit over 10 ms a turn, and this would otherwise
    be 8 `get_attackable_tiles_from` calls per tile.
    """
    traffic = approach_betweenness(ct, footprint)
    if not traffic:
        return None

    lanes = friendly_turret_lanes(ct)
    unsafe = enemy_covered_tiles(ct)
    already = set()
    me = ct.get_team()
    for bid in ct.get_nearby_buildings():
        try:
            if ct.get_team(bid) != me or ct.get_entity_type(bid) not in RAY_LEN:
                continue
            already |= turret_cover(
                ct, ct.get_position(bid), ct.get_direction(bid), ct.get_entity_type(bid)
            )
        except GameError:
            continue

    # Seats worth considering: near the Core, empty, not in a friendly lane,
    # not already under enemy fire.
    seats = sorted(
        (
            t for t in ct.get_nearby_tiles()
            if min(f.distance_squared(t) for f in footprint) <= APPROACH_RADIUS_SQ
            and building_at(ct, t) is None
            and (t.x, t.y) not in lanes
            and (t.x, t.y) not in unsafe
            and (t.x, t.y) in traffic
        ),
        key=lambda t: -traffic[(t.x, t.y)],
    )[:limit]

    best = None
    for spot in seats:
        for facing in COMPASS:
            if not buildable(spot, facing):
                continue
            score = 0.0
            for tile in turret_cover(ct, spot, facing, kind):
                w = traffic.get(tile)
                if w:
                    score += w * (0.25 if tile in already else 1.0)
            if score > 0 and (best is None or score > best[2]):
                best = (spot, facing, score)
    return best


def best_firing_seat(ct, enemies, kind: EntityType, buildable, near: Position):
    """Best adjacent seat with a live firing solution against a visible enemy.

    The engaging counterpart to best_defensive_site, and a direct port of
    steward's `_aligned_turret_site`: only seats the engine confirms can fire
    are considered, friendly lanes are preserved, and seats under enemy fire
    are refused.
    """
    lanes = friendly_turret_lanes(ct)
    unsafe = enemy_covered_tiles(ct)
    best = None
    for d in COMPASS:
        spot = near.add(d)
        key = (spot.x, spot.y)
        if not in_bounds(ct, spot) or key in lanes or key in unsafe:
            continue
        if building_at(ct, spot) is not None:
            continue
        for eid in enemies:
            try:
                target = ct.get_position(eid)
                facing = spot.direction_to(target)
                if not ct.can_fire_from(spot, facing, kind, target):
                    continue
            except GameError:
                continue
            if not buildable(spot, facing):
                continue
            d2 = spot.distance_squared(target)
            if best is None or d2 < best[2]:
                best = (spot, facing, d2)
    return best


# MEASURED AND REJECTED: counter_battery_seat -- a Sentinel seat found near an
# enemy turret, walked to by a Builder. The reasoning was sound (an enemy
# turret is a building, so the seat is still there when you arrive) and it
# measured worse on every axis over the 6-map panel:
#
#     wins                 6 -> 5
#     titanium collected   2121 -> 1856
#     core hp at end        200 -> 161
#     enemy cores killed   mean round 233 -> never
#
# The walk is the problem, not the seat. A Builder sent five tiles out to
# answer a siege is neither mining nor mending, and it crosses exactly the
# ground the siege covers to get there. best_firing_seat, which only seats
# from tiles already adjacent to the Builder, keeps the counter-battery that
# works and drops the part that does not.


# MEASURED AND REJECTED: home_counter_seat -- a seat near our OWN Core with a
# firing solution on an enemy Gunner. Motivated by replay attribution showing
# enemy Gunners deal 94-100% of all damage to our Core, and unlike the earlier
# counter_battery_seat the walk was short and stayed inside our defences.
#
# Full 15-map pool, vs steward/vidar/odin:
#     titanium collected   823 -> 375
#     core hp at end        47 -> 12
#     games survived      7/45 -> 2/45
#
# Fourth reactive-combat change in a row to measure worse. The pattern is
# consistent and is not about siting: every behaviour that diverts a Builder
# to answer a threat costs more economy than the threat costs us. With this
# few Builders they are simply too scarce to spend on reacting, and a bot that
# out-mines its opponent and mends is worth more than one that fights back
# badly. The gap to steward is that it can afford both, because its economy
# and its unit count are larger to begin with.
