"""Sentinel entity logic."""

from __future__ import annotations

from fcode import Controller, Position


class SentinelMixin:
    def run_sentinel(self, ct: Controller) -> None:
        """Fire at the closest enemy entity in the Sentinel's attack area."""

        position = ct.get_position()
        own_team = ct.get_team()
        attackable_tiles = sorted(
            ct.get_attackable_tiles(),
            key=lambda target: (
                position.distance_squared(target),
                target.y,
                target.x,
            ),
        )

        for target in attackable_tiles:
            # A Builder Bot takes the hit when it shares a tile with a building.
            entity_id = ct.get_tile_builder_bot_id(target)
            if entity_id is None:
                entity_id = ct.get_tile_building_id(target)

            if entity_id is None or ct.get_team(entity_id) == own_team:
                continue
            if ct.can_fire(target):
                ct.fire(target)
                return
