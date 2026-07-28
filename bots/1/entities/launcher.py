"""Launcher logic driven by a packed one-slot Builder request protocol."""

from __future__ import annotations

from fcode import Controller, Direction, Position

from utils.common import (
    MAX_THROW_DIST_SQ,
    SLOT_LAUNCH_REQUEST,
    SLOT_SPAWN_COUNT,
    core_positions,
    known_map_or_warn,
    unpack_launch_request,
)


class LauncherMixin:
    def run_launcher(self, ct: Controller) -> None:
        km = known_map_or_warn(self.map_match_state)
        if km is None:
            return
        _, enemy_core = core_positions(ct, km)
        launcher_pos = ct.get_position()

        # On the initial relay round the store still says exactly two Builders
        # exist, and both are attackers. This lets the first Launcher start
        # immediately even before a request wins the shared request slot.
        if ct.read_store(SLOT_SPAWN_COUNT) <= 2:
            bot_pos = self._find_adjacent_builder(ct, launcher_pos)
            requested_target = enemy_core
        else:
            request = unpack_launch_request(ct.read_store(SLOT_LAUNCH_REQUEST))
            if request is None:
                return
            requested_id, requested_target = request
            bot_pos = self._find_adjacent_builder(
                ct, launcher_pos, requested_id=requested_id
            )

        if bot_pos is None:
            return
        target = self._closest_reachable_to(
            ct, launcher_pos, bot_pos, requested_target
        )
        if target is not None:
            ct.launch(bot_pos, target)

    def _find_adjacent_builder(
        self,
        ct: Controller,
        position: Position,
        *,
        requested_id: int | None = None,
    ) -> Position | None:
        width, height = ct.get_map_width(), ct.get_map_height()
        for direction in Direction:
            if direction == Direction.CENTRE:
                continue
            candidate = position.add(direction)
            if not (0 <= candidate.x < width and 0 <= candidate.y < height):
                continue
            builder_id = ct.get_tile_builder_bot_id(candidate)
            if builder_id is None or ct.get_team(builder_id) != ct.get_team():
                continue
            if requested_id is None or builder_id & 0xFFFF == requested_id:
                return candidate
        return None

    def _closest_reachable_to(
        self,
        ct: Controller,
        launcher_pos: Position,
        bot_pos: Position,
        target: Position,
    ) -> Position | None:
        width, height = ct.get_map_width(), ct.get_map_height()
        reach = int(MAX_THROW_DIST_SQ**0.5) + 1
        best: Position | None = None
        best_dist_sq: int | None = None

        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                dist_sq = dx * dx + dy * dy
                if dist_sq == 0 or dist_sq > MAX_THROW_DIST_SQ:
                    continue
                candidate = Position(launcher_pos.x + dx, launcher_pos.y + dy)
                if not (0 <= candidate.x < width and 0 <= candidate.y < height):
                    continue
                if not ct.can_launch(bot_pos, candidate):
                    continue
                remaining = candidate.distance_squared(target)
                if best_dist_sq is None or remaining < best_dist_sq:
                    best = candidate
                    best_dist_sq = remaining

        return best
