"""Sentinel behavior."""

from typing import TYPE_CHECKING

from fcode import Controller

if TYPE_CHECKING:
    from .lineage import Player


def run(player: "Player", ct: Controller) -> None:
    """Fire at the lowest-HP visible enemy on the fixed firing line."""
    targets = [entity_id for entity_id in ct.get_nearby_entities()
               if ct.get_team(entity_id) != ct.get_team()
               and ct.can_fire(ct.get_position(entity_id))]
    if targets:
        target = min(targets, key=ct.get_hp)
        ct.fire(ct.get_position(target))
