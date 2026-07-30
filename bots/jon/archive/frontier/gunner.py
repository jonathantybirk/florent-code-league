"""Gunner logic for the custom bot.

Gunners are static turrets that fire along their facing direction. They need
ammo delivered by conveyor to actually shoot — this starter bot doesn't set up
that supply chain, which is a good first thing to add.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fcode import Controller, Direction, EntityType

if TYPE_CHECKING:
    from main import Player


def run(player: Player, ct: Controller) -> None:
    """Fire at the first enemy in our line of sight.

    get_gunner_target() returns the closest entity along the gunner's facing
    direction, or None if the line is clear. We only fire if can_fire()
    confirms we have ammo and cooldown is ready.
    """
    target = ct.get_gunner_target()
    if target is not None and ct.can_fire(target):
        ct.fire(target)
        return

    # Re-aim only in response to a real visible enemy. Avoid facing directly
    # away from an adjacent splitter, which is the direction ammo enters from.
    enemies = [
        entity_id
        for entity_id in ct.get_nearby_entities()
        if ct.get_team(entity_id) != ct.get_team()
    ]
    if not enemies:
        return
    enemy_id = min(
        enemies,
        key=lambda entity_id: ct.get_position().distance_squared(ct.get_position(entity_id)),
    )
    desired = ct.get_position().direction_to(ct.get_position(enemy_id))
    feed_direction = _feed_direction(ct)
    if desired == feed_direction:
        desired = desired.rotate_left()
    if desired != Direction.CENTRE and ct.can_rotate(desired):
        ct.rotate(desired)


def _feed_direction(ct: Controller) -> Direction | None:
    pos = ct.get_position()
    for direction in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST):
        tile = pos.add(direction)
        if not (0 <= tile.x < ct.get_map_width() and 0 <= tile.y < ct.get_map_height()):
            continue
        if not ct.is_in_vision(tile):
            continue
        building_id = ct.get_tile_building_id(tile)
        if building_id is None:
            continue
        if (
            ct.get_team(building_id) == ct.get_team()
            and ct.get_entity_type(building_id) == EntityType.SPLITTER
        ):
            return direction
    return None
