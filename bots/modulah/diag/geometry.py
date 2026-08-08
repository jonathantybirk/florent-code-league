# GENERATED from bots/modulah/lib/geometry.py -- edit that file, not this copy.
"""Board geometry: footprints, rays, and safe tile access.

Everything here is pure arithmetic over the Controller's read API. No module
in lib/ builds, moves, or spends anything -- the decision modules do that.

The two facts this module exists to encode, both measured against the 2.3.6
engine rather than taken from the docs:

  * The Core occupies a 2x2 block, and its vision is the UNION of radius-6
    discs around all four footprint tiles -- 140 tiles on open ground, not
    the 113 a single disc would give. Walls do not occlude it.

  * Turrets are LINE weapons with 8 facings, not area weapons. A turret can
    only ever hit a tile lying on one of its 8 rays, so most turrets near
    the Core physically cannot hit it and never will without being rebuilt.
"""

from __future__ import annotations

from fcode import Direction, EntityType, GameConstants, GameError, Position

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
DIAGONALS = (
    Direction.NORTHEAST,
    Direction.SOUTHEAST,
    Direction.SOUTHWEST,
    Direction.NORTHWEST,
)
COMPASS = CARDINALS + DIAGONALS

# Ray length per turret type, as (cardinal_tiles, diagonal_tiles). Measured
# with get_attackable_tiles_from over all 8 facings on fcode 2.3.6:
#   gunner   cardinal 3 (dist_sq 9),  diagonal 2 (dist_sq 8)
#   sentinel cardinal 5 (dist_sq 25), diagonal 4 (dist_sq 32)
# Note that SENTINEL's worst-case reach (32) is a DIAGONAL, and that it sits
# just inside CORE_VISION_RADIUS_SQ (36) -- which is why the Core can always
# see everything able to shoot it. That margin is 4, so it is worth
# re-measuring after any balance patch.
RAY_LEN = {
    EntityType.GUNNER: (3, 2),
    EntityType.SENTINEL: (5, 4),
}

TURRET_DAMAGE = {
    EntityType.GUNNER: GameConstants.GUNNER_DAMAGE,
    EntityType.SENTINEL: GameConstants.SENTINEL_DAMAGE,
}

# Sustained damage per round = damage / fire cooldown. A Sentinel hits for 18
# but only every other round, so it is worth less per round than the raw
# number suggests.
TURRET_DPR = {
    EntityType.GUNNER: GameConstants.GUNNER_DAMAGE / max(1, GameConstants.GUNNER_FIRE_COOLDOWN),
    EntityType.SENTINEL: GameConstants.SENTINEL_DAMAGE / max(1, GameConstants.SENTINEL_FIRE_COOLDOWN),
}


def in_bounds(ct, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


def building_at(ct, pos: Position) -> int | None:
    """Building id at pos, or None if empty, out of bounds, or out of vision.

    get_tile_building_id raises on out-of-vision positions rather than
    returning None, and a walk that runs to the edge of vision will hit that
    constantly. Collapsing the three "nothing usable here" cases into None
    keeps every caller from growing its own try/except.
    """
    if not in_bounds(ct, pos):
        return None
    try:
        return ct.get_tile_building_id(pos)
    except GameError:
        return None


def entity_type_of(ct, bid: int | None) -> EntityType | None:
    if bid is None:
        return None
    try:
        return ct.get_entity_type(bid)
    except GameError:
        return None


def core_footprint(ct) -> list[Position]:
    """All four tiles of this Core's 2x2 block.

    dist_sq=2 is enough from any tile inside the block: the two farthest
    tiles of a 2x2 are a diagonal step apart, which is distance_squared 2.
    """
    core_id = ct.get_id()
    return [p for p in ct.get_nearby_tiles(dist_sq=2) if building_at(ct, p) == core_id]


def ray_step(dx: int, dy: int) -> tuple[int, int] | None:
    """Decompose an offset into (steps, is_diagonal), or None if off-ray.

    A turret can only fire along the 8 compass directions, so an offset is
    reachable only when it is purely horizontal, purely vertical, or exactly
    diagonal. An enemy Sentinel at offset (3, 4) is well inside its own reach
    of dist_sq 32 and still cannot ever hit that tile -- (3, 4) is on no ray.
    Checking this first turns the threat sweep into integer comparisons and
    keeps can_fire_from (a pyo3 crossing) for the few that survive.
    """
    if dx == 0 and dy == 0:
        return None
    if dx == 0:
        return abs(dy), False
    if dy == 0:
        return abs(dx), False
    if abs(dx) == abs(dy):
        return abs(dx), True
    return None


def can_ray_reach(kind: EntityType, dx: int, dy: int) -> bool:
    """Could a turret of this type at the origin ever hit offset (dx, dy)?

    Ignores facing (one rotate is 10 Ti and a single round away), ignores
    walls and blocking -- this is the cheap geometric filter, not legality.
    """
    lens = RAY_LEN.get(kind)
    if lens is None:
        return False
    step = ray_step(dx, dy)
    if step is None:
        return False
    steps, diagonal = step
    return steps <= (lens[1] if diagonal else lens[0])


def orthogonal_neighbours(pos: Position) -> list[Position]:
    return [pos.add(d) for d in CARDINALS]


def touches_footprint(pos: Position, footprint: list[Position]) -> bool:
    """True if pos is orthogonally adjacent to any footprint tile.

    Builder bots may only attack an orthogonally adjacent tile, so this is
    the whole of their threat range against the Core.
    """
    for tile in footprint:
        if abs(tile.x - pos.x) + abs(tile.y - pos.y) == 1:
            return True
    return False


def enemy_core_guess(ct, footprint) -> Position:
    """Where the enemy Core is, from map dimensions alone, at round 0.

    Every map in the official pool is rotationally symmetric (`fcode maps
    list` reports all 15 as `rotational`), so the enemy Core is ours mirrored
    about the map centre. No scouting, no atlas, available on the first turn.
    """
    x = min(f.x for f in footprint)
    y = min(f.y for f in footprint)
    return Position(ct.get_map_width() - 1 - x, ct.get_map_height() - 1 - y)


def rear_corner(footprint, enemy: Position) -> Position:
    """The footprint tile farthest from the enemy Core.

    Measuring anything from `get_position()` is a seat bug waiting to happen:
    it returns the 2x2 block's top-left tile for BOTH seats, so under the
    180-degree symmetry one seat reads its rear corner and the other its front
    corner. The same deposit is then a tile further away for one of them, and
    every downstream decision inherits the difference.

    Anchoring on the rear corner is well defined for both seats AND is the
    strategically better reference: it prefers ground behind the Core, which
    can be worked without crossing the middle of the map.
    """
    return max(footprint, key=lambda f: f.distance_squared(enemy))


# Chebyshev Core-to-Core distance at or below which economy is dead weight.
# Steward measured 6 over 138,785 tournament matches: on a map where the enemy
# Core is six tiles away the game is decided before the first stack is
# delivered. Of the 15 official maps only fjordgate (5) qualifies; the rest
# run 8-20. So this branch is narrow by design -- it exists because that one
# map is otherwise played with an opening that cannot possibly pay off.
BLITZ_MAX_DISTANCE = 6


def core_distance(ct, footprint) -> int:
    """Chebyshev distance from our Core to the enemy's, known at round 0.

    Uses enemy_core_guess, so it needs no scouting: every official map is
    rotationally symmetric.
    """
    enemy = enemy_core_guess(ct, footprint)
    near = min(footprint, key=lambda f: f.distance_squared(enemy))
    return max(abs(enemy.x - near.x), abs(enemy.y - near.y))


def is_blitz_map(ct, footprint) -> bool:
    return core_distance(ct, footprint) <= BLITZ_MAX_DISTANCE
