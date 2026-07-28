"""Gunner entity logic."""

from __future__ import annotations

from fcode import Controller


class GunnerMixin:
    def run_gunner(self, ct: Controller) -> None:
        target = ct.get_gunner_target()
        if target is None:
            return
        entity_id = ct.get_tile_builder_bot_id(target)
        if entity_id is None:
            entity_id = ct.get_tile_building_id(target)
        if entity_id is None or ct.get_team(entity_id) == ct.get_team():
            return
        if ct.can_fire(target):
            ct.fire(target)
