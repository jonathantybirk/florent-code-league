"""Core behavior."""

from typing import TYPE_CHECKING

from fcode import Controller, Direction, Position


if TYPE_CHECKING:
    from main import Player


def run(player: "Player", ct: Controller) -> None:
    """Spawn exactly two opening Builders.

    Engine-backed peer review found that round-zero visible ore count is a
    misleading predictor of useful economic parallelism. Reconsider any third
    Builder later from live workload/combat evidence, not a map fingerprint.
    """
    if not hasattr(player, "builders_spawned"):
        player.builders_spawned = 0
    if player.builders_spawned >= 2:
        return
    if ct.get_global_resources() < ct.get_builder_bot_cost():
        return

    # Engine ordering is deterministic. Keeping the spawn rule simple also
    # avoids placing a Builder on the far side of the 2x2 Core from its first
    # visible job; task selection handles directional specialization afterward.
    for spawn_pos in ct.get_nearby_tiles(2):
        if ct.can_spawn(spawn_pos):
            ct.spawn_builder(spawn_pos)
            player.builders_spawned += 1
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
