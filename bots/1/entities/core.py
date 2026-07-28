"""Core spawning and Builder Bot role assignment."""

from __future__ import annotations

from fcode import Controller

from utils.common import (
    ATTACKER_COUNT,
    MAX_INFRASTRUCTURE_BUILDERS,
    SLOT_ATTACKER_0_ID,
    SLOT_ATTACKER_1_ID,
    SLOT_SPAWN_ASSIGNMENT,
    core_perimeter,
    core_positions,
    encode_spawn_assignment,
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

        infrastructure_count = min(MAX_INFRASTRUCTURE_BUILDERS, len(ordered_ores(km, my_core)))
        if self.spawn_count >= ATTACKER_COUNT + infrastructure_count:
            return
        if ct.get_global_resources() < ct.get_builder_bot_cost():
            return

        attacker = self.spawn_count < ATTACKER_COUNT
        target = enemy_core
        if not attacker:
            target = ordered_ores(km, my_core)[self.spawn_count - ATTACKER_COUNT]

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
            ct.write_store(
                SLOT_SPAWN_ASSIGNMENT,
                encode_spawn_assignment(self.spawn_count, attacker=attacker),
            )
            if self.spawn_count == 0:
                ct.write_store(SLOT_ATTACKER_0_ID, builder_id)
            elif self.spawn_count == 1:
                ct.write_store(SLOT_ATTACKER_1_ID, builder_id)
            self.spawn_count += 1
            return
