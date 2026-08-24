"""Getting a Builder from where it is to where its next build is.

Along a lane this is a single cardinal step and needs no search -- the lane is
the path.  A search is only wanted when a Builder finishes one lane and has to
cross to another, which happens a handful of times a match, so the BFS here is
run rarely and its result is kept until it stops being usable.
"""

from fcode import Direction, Position

from board import STEPS

STEP_DIR = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
            (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}


def route(board, start, goal, blocked=frozenset()):
    """Tiles from `start` (exclusive) to `goal` (inclusive), or None."""
    if start == goal:
        return []
    came = {start: None}
    frontier = [start]
    while frontier:
        nxt = []
        for tile in frontier:
            x, y = tile
            for dx, dy in STEPS:
                spot = (x + dx, y + dy)
                if spot in came or spot in blocked:
                    continue
                if not board.walkable(spot):
                    continue
                came[spot] = tile
                if spot == goal:
                    return _unwind(came, goal)
                nxt.append(spot)
        frontier = nxt
    return None


def _unwind(came, goal):
    out = []
    tile = goal
    while came[tile] is not None:
        out.append(tile)
        tile = came[tile]
    out.reverse()
    return out


def step(ct, here, there):
    """Take the single cardinal step from `here` onto the adjacent `there`."""
    direction = STEP_DIR.get((there[0] - here[0], there[1] - here[1]))
    if direction is None or not ct.can_move(direction):
        return False
    ct.move(direction)
    return True


def at(tile):
    return Position(tile[0], tile[1])


def sidestep(ct, seed):
    """Any legal move at all, to break a jam.

    Two Builders that each want the tile the other is standing on will hold
    that pose forever: neither move is legal, so neither ever gives way and
    no amount of re-routing helps, because the route is right and the tile is
    simply occupied. Somebody has to move somewhere unhelpful. `seed` varies
    the direction with the round and the seat so that the two do not step in
    step and re-block each other.
    """
    for offset in range(4):
        direction = _ORDER[(seed + offset) % 4]
        if ct.can_move(direction):
            ct.move(direction)
            return True
    return False


_ORDER = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
