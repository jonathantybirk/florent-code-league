"""Core spawning, economy throttling, and Builder Bot assignment."""

from __future__ import annotations

from fcode import Controller

from utils.common import (
    INFRASTRUCTURE_STATUS_SLOTS,
    MAX_BUILDERS,
    SLOT_RESOURCE_PRESSURE,
    SLOT_SPAWN_ASSIGNMENT,
    SLOT_SPAWN_COUNT,
    core_perimeter,
    core_positions,
    encode_spawn_assignment,
    infrastructure_ordinal,
    is_attacker_spawn,
    known_map_or_warn,
    ordered_ores,
    pack_infrastructure_status,
    unpack_infrastructure_status,
)


class CoreMixin:
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.spawn_count = 0

    def run_core(self, ct: Controller) -> None:
        # Clear last round's request. Builders that are still short on global
        # titanium write 1 later in this round, after the Core has acted.
        resource_pressure = ct.read_store(SLOT_RESOURCE_PRESSURE) != 0
        ct.write_store(SLOT_RESOURCE_PRESSURE, 0)
        ct.write_store(SLOT_SPAWN_COUNT, self.spawn_count)

        km = known_map_or_warn(self.map_match_state)
        if km is None or self.spawn_count >= MAX_BUILDERS or resource_pressure:
            return
        if ct.get_global_resources() < ct.get_builder_bot_cost():
            return

        my_core, enemy_core = core_positions(ct, km)
        attacker = is_attacker_spawn(self.spawn_count)
        target = enemy_core
        infrastructure_slot: int | None = None
        ore_index: int | None = None

        if not attacker:
            ordinal = infrastructure_ordinal(self.spawn_count)
            if ordinal >= len(INFRASTRUCTURE_STATUS_SLOTS):
                return
            infrastructure_slot = INFRASTRUCTURE_STATUS_SLOTS[ordinal]
            statuses = [
                unpack_infrastructure_status(ct.read_store(slot))
                for slot in INFRASTRUCTURE_STATUS_SLOTS
            ]
            claimed_ores = {
                status[0] for status in statuses if status is not None
            }
            ores = ordered_ores(km, my_core)
            ore_index = next(
                (index for index in range(len(ores)) if index not in claimed_ores),
                None,
            )
            if ore_index is None:
                return
            target = ores[ore_index]

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
            ct.spawn_builder(spawn_position)
            ct.write_store(
                SLOT_SPAWN_ASSIGNMENT,
                encode_spawn_assignment(self.spawn_count, attacker=attacker),
            )
            self.spawn_count += 1
            ct.write_store(SLOT_SPAWN_COUNT, self.spawn_count)
            if infrastructure_slot is not None and ore_index is not None:
                ct.write_store(
                    infrastructure_slot,
                    pack_infrastructure_status(ore_index),
                )
            return
