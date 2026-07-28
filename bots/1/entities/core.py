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
        self.spawn_assignment_announced = False

    def run_core(self, ct: Controller) -> None:
        km = known_map_or_warn(self.map_match_state)
        if km is None:
            return
        my_core, enemy_core = core_positions(ct, km)

        ores = ordered_ores(km, my_core)
        infrastructure_count = min(MAX_INFRASTRUCTURE_BUILDERS, len(ores))
        total_builders = ATTACKER_COUNT + infrastructure_count
        if self.spawn_count >= total_builders:
            return

        # Builder 0 needs no announcement: it is the only Builder born while
        # the assignment word is still zero and therefore identifies itself as
        # the first attacker. Every later assignment is announced before its
        # Builder spawns. Once announced, leave it unchanged until that Builder
        # is successfully spawned.
        if self.spawn_count != 0 and not self.spawn_assignment_announced:
            self._announce_spawn_assignment(ct)
            self.spawn_assignment_announced = True
            return

        if ct.get_global_resources() < ct.get_builder_bot_cost():
            return

        attacker = self.spawn_count < ATTACKER_COUNT
        target = enemy_core
        if not attacker:
            target = ores[self.spawn_count - ATTACKER_COUNT]

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
            if self.spawn_count == 0:
                ct.write_store(SLOT_ATTACKER_0_ID, builder_id)
            elif self.spawn_count == 1:
                ct.write_store(SLOT_ATTACKER_1_ID, builder_id)
            self.spawn_count += 1

            if self.spawn_count < total_builders:
                self._announce_spawn_assignment(ct)
                self.spawn_assignment_announced = True
            else:
                self.spawn_assignment_announced = False
            return

    def _announce_spawn_assignment(self, ct: Controller) -> None:
        ct.write_store(
            SLOT_SPAWN_ASSIGNMENT,
            encode_spawn_assignment(
                self.spawn_count,
                attacker=self.spawn_count < ATTACKER_COUNT,
            ),
        )
