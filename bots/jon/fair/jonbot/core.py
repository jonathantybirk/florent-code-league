"""Map-agnostic Core opening and spawn placement."""

from typing import TYPE_CHECKING

from fcode import Controller, Direction, Environment, Position

if TYPE_CHECKING:
    from main import Player


CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def run(player: "Player", ct: Controller) -> None:
    """Spawn two Builders toward distinct visible work or scout objectives."""
    if not hasattr(player, "builders_spawned"):
        player.builders_spawned = 0
        core = ct.get_position()
        ores = [tile for tile in ct.get_nearby_tiles()
                if ct.get_tile_env(tile) == Environment.ORE_TITANIUM
                and ct.get_tile_building_id(tile) is None]
        ores.sort(key=lambda tile: (tile.distance_squared(core), tile.x, tile.y))
        player.opening_ore_targets = ores

    role = player.builders_spawned
    if role >= 2 or ct.get_global_resources() < ct.get_builder_bot_cost():
        return

    if role < len(player.opening_ore_targets):
        target = player.opening_ore_targets[role]
        goals = [target.add(direction) for direction in CARDINALS
                 if _on_map(ct, target.add(direction))]
    else:
        target = _scout_target(ct, role - len(player.opening_ore_targets))
        goals = [target]

    candidates = [tile for tile in ct.get_nearby_tiles(2) if ct.can_spawn(tile)]
    candidates.sort(key=lambda tile: (
        min(_chebyshev(tile, goal) for goal in goals),
        tile.distance_squared(target),
        tile.x,
        tile.y,
    ))
    if candidates:
        ct.spawn_builder(candidates[0])
        player.builders_spawned += 1


def _scout_target(ct: Controller, index: int) -> Position:
    """Split generic symmetry candidates when visible ore jobs run out."""
    core = ct.get_position()
    candidates = (
        Position(ct.get_map_width() - 2 - core.x,
                 ct.get_map_height() - 2 - core.y),
        Position(ct.get_map_width() - 2 - core.x, core.y),
        Position(core.x, ct.get_map_height() - 2 - core.y),
    )
    unique = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique[index % len(unique)]


def _chebyshev(a: Position, b: Position) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def _on_map(ct: Controller, position: Position) -> bool:
    return 0 <= position.x < ct.get_map_width() and 0 <= position.y < ct.get_map_height()
