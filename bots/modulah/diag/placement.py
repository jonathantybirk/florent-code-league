# GENERATED from bots/modulah/lib/placement.py -- edit that file, not this copy.
"""Where to put a turret, given that turrets are line weapons.

The usual approach is "build a Gunner near the Core". That wastes most of what
a turret is, because a turret does not cover an area -- it covers ONE ray of
3 tiles (Gunner) or 5 (Sentinel) along one of 8 facings, and re-aiming costs 10
Ti and a round.

So siting is a covering problem, not a proximity problem: pick the (tile,
facing) whose ray crosses the most ground an attacker must actually walk over
to reach the Core. Two turrets three tiles apart pointing down the same
corridor are worth far less than two covering different approaches.

Everything here is scoring only -- it returns candidates, it never builds.
"""

from __future__ import annotations

from fcode import EntityType, GameError, Position

from geometry import (
    COMPASS,
    RAY_LEN,
    building_at,
    in_bounds,
)

# How far out to consider approach ground. A Sentinel reaches 5 along a
# cardinal, so anything beyond ~6 from the footprint is ground we cannot cover
# from home anyway, and scoring it only blurs the comparison.
APPROACH_RADIUS_SQ = 36


def ray_tiles(origin: Position, facing, kind: EntityType) -> list[Position]:
    """The tiles a turret at `origin` facing `facing` would cover.

    Mirrors the engine's pattern exactly (verified tile-for-tile by diag):
    fixed-length rays, shorter in tile count on the diagonals but reaching
    further in Euclidean terms.
    """
    lens = RAY_LEN.get(kind)
    if lens is None:
        return []
    dx, dy = facing.delta()
    if dx == 0 and dy == 0:  # Direction.CENTRE
        return []
    n = lens[1] if (dx != 0 and dy != 0) else lens[0]
    return [Position(origin.x + dx * i, origin.y + dy * i) for i in range(1, n + 1)]


def approach_weights(ct, footprint) -> dict[tuple[int, int], float]:
    """How much each nearby tile matters as ground an attacker crosses.

    Weighted by closeness to the Core: a tile adjacent to the footprint is
    where the damage actually lands, so covering it beats covering open ground
    five tiles out. Walls score nothing -- nobody walks through them.
    """
    weights: dict[tuple[int, int], float] = {}
    for tile in ct.get_nearby_tiles():
        try:
            if not ct.is_tile_passable(tile):
                continue
        except GameError:
            continue
        d = min(f.distance_squared(tile) for f in footprint)
        if d == 0 or d > APPROACH_RADIUS_SQ:
            continue
        weights[(tile.x, tile.y)] = 1.0 / (1.0 + d)
    return weights


def score_site(ct, pos: Position, facing, kind: EntityType, weights, taken) -> float:
    """Value of covering ground from here, discounting ground already covered.

    `taken` carries the tiles existing friendly turrets already cover, which is
    what stops the third Gunner from being stacked into the same corridor as
    the first two.
    """
    total = 0.0
    for t in ray_tiles(pos, facing, kind):
        if not in_bounds(ct, t):
            break
        key = (t.x, t.y)
        w = weights.get(key)
        if w is None:
            continue
        total += w * (0.25 if key in taken else 1.0)
    return total


def covered_by_friendly_turrets(ct, footprint) -> set[tuple[int, int]]:
    me = ct.get_team()
    covered: set[tuple[int, int]] = set()
    for bid in ct.get_nearby_buildings():
        try:
            if ct.get_team(bid) != me:
                continue
            kind = ct.get_entity_type(bid)
            if kind not in RAY_LEN:
                continue
            pos = ct.get_position(bid)
            facing = ct.get_direction(bid)
        except GameError:
            continue
        for t in ray_tiles(pos, facing, kind):
            covered.add((t.x, t.y))
    return covered


def best_turret_site(ct, footprint, kind: EntityType, buildable, limit: int = 40):
    """Best (position, facing, score) for a new turret, or None.

    `buildable` is a callable so the caller keeps ownership of legality --
    can_build_gunner needs the Builder's own adjacency rules, which this module
    has no business knowing about.

    Candidates are capped at `limit` tiles nearest the Core. The platform kills
    a unit over 10 ms per turn and this runs 8 facings per candidate, so the
    search is bounded by work rather than trusted to stay small.
    """
    weights = approach_weights(ct, footprint)
    if not weights:
        return None
    taken = covered_by_friendly_turrets(ct, footprint)

    candidates = sorted(
        (t for t in ct.get_nearby_tiles()
         if min(f.distance_squared(t) for f in footprint) <= APPROACH_RADIUS_SQ),
        key=lambda t: min(f.distance_squared(t) for f in footprint),
    )[:limit]

    best = None
    for pos in candidates:
        if building_at(ct, pos) is not None:
            continue
        for facing in COMPASS:
            if not buildable(pos, facing):
                continue
            s = score_site(ct, pos, facing, kind, weights, taken)
            if s > 0 and (best is None or s > best[2]):
                best = (pos, facing, s)
    return best
