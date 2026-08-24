"""Map-agnostic Core opening and spawn placement."""

from typing import TYPE_CHECKING

from fcode import Controller, Direction, Environment, Position

from constants import (ECONOMY_BUILDERS, MAX_OPENING_BUILDERS,
                       SLOT_CORE_DAMAGED, SLOT_OWN_CORE)
from utils import pack_pos

if TYPE_CHECKING:
    from main import Player


CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def run(player: "Player", ct: Controller) -> None:
    """Spawn one economy Builder and three conventional attackers."""
    _keep_ammunition(ct)
    if not hasattr(player, "repair_alert"):
        player.repair_alert = False
    hp, max_hp = ct.get_hp(ct.get_id()), ct.get_max_hp(ct.get_id())
    if hp <= max_hp - 50:
        player.repair_alert = True
    elif hp == max_hp:
        player.repair_alert = False
    ct.write_store(SLOT_OWN_CORE, pack_pos(ct.get_position()))
    ct.write_store(SLOT_CORE_DAMAGED, int(player.repair_alert))
    if not hasattr(player, "builders_spawned"):
        player.builders_spawned = 0
        core = ct.get_position()
        ores = [tile for tile in ct.get_nearby_tiles()
                if ct.get_tile_env(tile) == Environment.ORE_TITANIUM
                and ct.get_tile_building_id(tile) is None]
        ores.sort(key=lambda tile: (tile.distance_squared(core), tile.x, tile.y))
        player.opening_ore_targets = ores

    role = player.builders_spawned
    if role >= MAX_OPENING_BUILDERS or ct.get_global_resources() < ct.get_builder_bot_cost():
        return

    if role < ECONOMY_BUILDERS and role < len(player.opening_ore_targets):
        target = player.opening_ore_targets[role]
        goals = [target.add(direction) for direction in CARDINALS
                 if _on_map(ct, target.add(direction))]
    else:
        target = _scout_target(ct, role - ECONOMY_BUILDERS)
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


def _keep_ammunition(ct) -> None:
    """Turn titanium into ammunition, or no turret we own can fire at all.

    Engine 2.3.3 replaced 2.2.0's per-turret ammunition with a global pool the
    Core fills by conversion: 1 titanium for 1 ammunition, at most once per
    team per turn, no action cooldown, usable the same turn.
    """
    try:
        held = ct.get_global_ammo()
        if held >= 120:
            return
        amount = min(120 - held, ct.get_global_resources() - 60)
        if amount > 0 and ct.can_convert_ammo(amount):
            ct.convert_ammo(amount)
    except Exception:  # noqa: BLE001 - never let this kill the Core
        return
