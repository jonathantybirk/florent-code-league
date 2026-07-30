"""Sentinel targeting for supplied offensive emplacements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fcode import Controller

if TYPE_CHECKING:
    from main import Player


def run(player: Player, ct: Controller) -> None:
    targets = [
        entity_id
        for entity_id in ct.get_nearby_entities()
        if ct.get_team(entity_id) != ct.get_team()
        and ct.can_fire(ct.get_position(entity_id))
    ]
    if not targets:
        return
    target_id = min(targets, key=lambda entity_id: ct.get_hp(entity_id))
    ct.fire(ct.get_position(target_id))
