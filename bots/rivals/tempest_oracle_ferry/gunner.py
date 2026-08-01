"""Gunner behavior."""

from typing import TYPE_CHECKING

from fcode import Controller

if TYPE_CHECKING:
    from main import Player


def run(player: "Player", ct: Controller) -> None:
    """Fire at the first target in the current ray when locally supplied."""
    target = ct.get_gunner_target()
    if target is None:
        return
    target_id = ct.get_tile_builder_bot_id(target)
    if target_id is None:
        target_id = ct.get_tile_building_id(target)
    if (target_id is not None and ct.get_team(target_id) != ct.get_team()
            and ct.can_fire(target)):
        ct.fire(target)
