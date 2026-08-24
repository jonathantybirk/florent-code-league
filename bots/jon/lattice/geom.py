"""Pure geometry. No Controller, no game state, no imports from this bot.

Builder Bots move on a 4-neighbour graph (cardinal only) and act on a
4-neighbour graph (orthogonal only), but *vision*, turret facing and building
orientation are all 8-way. Keeping the two neighbourhoods explicitly named is
the whole point of this module: mixing them up is the most common way to write
a move that raises, or a build that silently never happens.
"""
from __future__ import annotations

from fcode import Direction, Position

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
DIAGONALS = (Direction.NORTHEAST, Direction.SOUTHEAST,
             Direction.SOUTHWEST, Direction.NORTHWEST)
ALL_EIGHT = CARDINALS + DIAGONALS

# Deltas cached as plain tuples: Direction.delta() is a call per use and these
# sit in the hot loops of pathing and siting.
CARD_DELTAS = tuple(d.delta() for d in CARDINALS)
EIGHT_DELTAS = tuple(d.delta() for d in ALL_EIGHT)


def in_bounds(x: int, y: int, w: int, h: int) -> bool:
    return 0 <= x < w and 0 <= y < h


def orth_neighbours(pos: Position, w: int, h: int):
    """The four tiles a Builder can move onto, build on, heal or attack."""
    x, y = pos.x, pos.y
    for dx, dy in CARD_DELTAS:
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h:
            yield Position(nx, ny)


def eight_neighbours(pos: Position, w: int, h: int):
    """The eight tiles that matter for vision, facing and adjacency-in-spirit."""
    x, y = pos.x, pos.y
    for dx, dy in EIGHT_DELTAS:
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h:
            yield Position(nx, ny)


def manhattan(a: Position, b: Position) -> int:
    """True step count for a Builder, which cannot move diagonally."""
    return abs(a.x - b.x) + abs(a.y - b.y)


def chebyshev(a: Position, b: Position) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def dist_sq(a: Position, b: Position) -> int:
    dx = a.x - b.x
    dy = a.y - b.y
    return dx * dx + dy * dy


def toward(src: Position, dst: Position) -> Direction:
    """A legal cardinal step from src toward dst, or CENTRE if already there."""
    return src.cardinal_direction_to(dst)


def facing_from_to(src: Position, dst: Position) -> Direction:
    """Eight-way facing for a turret or conveyor sited at src aimed at dst."""
    dx = dst.x - src.x
    dy = dst.y - src.y
    sx = (dx > 0) - (dx < 0)
    sy = (dy > 0) - (dy < 0)
    for d in ALL_EIGHT:
        if d.delta() == (sx, sy):
            return d
    return Direction.CENTRE


# --- symmetry ---------------------------------------------------------------
# Every map in the pool is symmetric, and the transform tells us where the enemy
# Core is long before anything of ours can see it. Only these three occur.
ROT180 = "rot180"
MIRROR_X = "mirror_x"   # reflection across the vertical mid-line: x -> w-1-x
MIRROR_Y = "mirror_y"   # reflection across the horizontal mid-line: y -> h-1-y
SYMMETRIES = (ROT180, MIRROR_X, MIRROR_Y)


def reflect(pos: Position, sym: str, w: int, h: int) -> Position:
    if sym == ROT180:
        return Position(w - 1 - pos.x, h - 1 - pos.y)
    if sym == MIRROR_X:
        return Position(w - 1 - pos.x, pos.y)
    return Position(pos.x, h - 1 - pos.y)


def core_anchor_reflect(core: Position, sym: str, w: int, h: int) -> Position:
    """Where the enemy Core's anchor sits, given ours and the symmetry.

    The Core occupies a 2x2 footprint anchored at its reported position, so the
    reflection of the *anchor* is off by one on each mirrored axis -- reflecting
    the anchor alone would name the wrong corner of their footprint.
    """
    if sym == ROT180:
        return Position(w - 2 - core.x, h - 2 - core.y)
    if sym == MIRROR_X:
        return Position(w - 2 - core.x, core.y)
    return Position(core.x, h - 2 - core.y)
