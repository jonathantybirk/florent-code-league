"""Core behavior."""

from typing import TYPE_CHECKING

from fcode import Controller, Direction, Position

if TYPE_CHECKING:
    from main import Player


OPENING_ROUNDS = 6


def run(player: "Player", ct: Controller) -> None:
    """Spawn six builders onto the map-facing sides of the Core."""
    tick = ct.get_current_round()
    if tick >= OPENING_ROUNDS:
        return

    core_pos = ct.get_position()
    directions = _exploration_directions(ct, core_pos)

    # Start with this round's assigned direction. If that whole side is
    # blocked, fall back to the next useful exploration direction.
    start = tick % len(directions)
    ordered_directions = directions[start:] + directions[:start]

    for direction in ordered_directions:
        for spawn_pos in _spawn_tiles(core_pos, direction):
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                return


def _exploration_directions(
    ct: Controller, core_pos: Position
) -> tuple[Direction, ...]:
    """Return directions leading away from the nearest map edge or corner."""
    edge_distances = {
        Direction.WEST: core_pos.x,
        Direction.EAST: ct.get_map_width() - core_pos.x - 2,
        Direction.NORTH: core_pos.y,
        Direction.SOUTH: ct.get_map_height() - core_pos.y - 2,
    }

    horizontal_edge = min(
        (Direction.WEST, Direction.EAST), key=edge_distances.get
    )
    vertical_edge = min(
        (Direction.NORTH, Direction.SOUTH), key=edge_distances.get
    )

    horizontal_distance = edge_distances[horizontal_edge]
    vertical_distance = edge_distances[vertical_edge]

    # Similar horizontal and vertical edge distances mean a corner start.
    if abs(horizontal_distance - vertical_distance) <= 2:
        return (horizontal_edge.opposite(), vertical_edge.opposite())

    # A side start explores inward plus both directions along that side.
    if horizontal_distance < vertical_distance:
        return (
            horizontal_edge.opposite(),
            Direction.NORTH,
            Direction.SOUTH,
        )
    return (
        vertical_edge.opposite(),
        Direction.WEST,
        Direction.EAST,
    )


def _spawn_tiles(
    core_pos: Position, direction: Direction
) -> tuple[Position, Position, Position, Position]:
    """Return the four adjacent spawn tiles along one side of the 2x2 Core."""
    x, y = core_pos

    if direction == Direction.NORTH:
        return (
            Position(x, y - 1),
            Position(x + 1, y - 1),
            Position(x - 1, y - 1),
            Position(x + 2, y - 1),
        )
    if direction == Direction.SOUTH:
        return (
            Position(x, y + 2),
            Position(x + 1, y + 2),
            Position(x - 1, y + 2),
            Position(x + 2, y + 2),
        )
    if direction == Direction.WEST:
        return (
            Position(x - 1, y),
            Position(x - 1, y + 1),
            Position(x - 1, y - 1),
            Position(x - 1, y + 2),
        )
    return (
        Position(x + 2, y),
        Position(x + 2, y + 1),
        Position(x + 2, y - 1),
        Position(x + 2, y + 2),
    )
