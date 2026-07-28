"""Core spawning and Builder Bot role assignment."""

from __future__ import annotations

from fcode import Controller

from utils.common import (
    SLOT_BUILDER_ID_START,
    attacker_count,
    core_perimeter,
    core_positions,
    infrastructure_builder_count,
    ordered_ores,
    known_map_or_warn,
)


class CoreMixin:
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.spawn_count = 0

    def run_core(self, ct: Controller) -> None:
        km = known_map_or_warn(self.map_match_state)
        if km is None:
            return
        my_core, enemy_core = core_positions(ct, km)

        ores = ordered_ores(km, my_core)
        attackers = attacker_count(ct, km)
        infrastructure_count = min(infrastructure_builder_count(ct, km), len(ores))
        total_builders = attackers + infrastructure_count
        if self.spawn_count >= total_builders:
            return

        if ct.get_global_resources() < ct.get_builder_bot_cost():
            return

        attacker = self.spawn_count < attackers
        target = enemy_core
        if not attacker:
            target = ores[self.spawn_count - attackers]

        spawn_positions = [
            position
            for position in core_perimeter(my_core)
            if 0 <= position.x < km.width and 0 <= position.y < km.height
        ]
        spawn_positions.sort(
            key=lambda position: (
                position.distance_squared(target),
                position.y,
                position.x,
            )
        )

        for spawn_position in spawn_positions:
            if not ct.can_spawn(spawn_position):
                continue
            builder_id = ct.spawn_builder(spawn_position)
            ct.write_store(SLOT_BUILDER_ID_START + self.spawn_count, builder_id)
            self.spawn_count += 1
            return
