"""Launcher entity logic for the two registered attacker bots."""

from __future__ import annotations

from fcode import Controller, Direction, Position

from utils.common import (
    MAX_THROW_DIST_SQ,
    SLOT_ATTACKER_0_ID,
    SLOT_ATTACKER_1_ID,
    core_perimeter,
    core_positions,
    known_map_or_warn,
    path_distance,
    use_path_aware_launch,
)
from utils.map import KnownMap


class LauncherMixin:
    def run_launcher(self, ct: Controller) -> None:
        pos = ct.get_position()
        bot_pos = self._find_adjacent_attacker(ct, pos)
        if bot_pos is None:
            return

        km = known_map_or_warn(self.map_match_state)
        if km is None:
            return
        _, enemy_core = core_positions(ct, km)

        target = self._closest_reachable_to(ct, km, pos, bot_pos, enemy_core)
        if target is not None:
            ct.launch(bot_pos, target)

    def _find_adjacent_attacker(self, ct: Controller, pos: Position) -> Position | None:
        attacker_ids = [
            ct.read_store(SLOT_ATTACKER_0_ID),
            ct.read_store(SLOT_ATTACKER_1_ID),
        ]
        attacker_priority = {
            attacker_id: index
            for index, attacker_id in enumerate(attacker_ids)
            if attacker_id != 0
        }
        width, height = ct.get_map_width(), ct.get_map_height()
        candidates: list[tuple[int, Position]] = []
        for d in Direction:
            if d == Direction.CENTRE:
                continue
            check = pos.add(d)
            if not (0 <= check.x < width and 0 <= check.y < height):
                continue
            builder_id = ct.get_tile_builder_bot_id(check)
            if builder_id in attacker_priority:
                candidates.append((attacker_priority[builder_id], check))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[0])[1]

    def _closest_reachable_to(
        self,
        ct: Controller,
        km: KnownMap,
        launcher_pos: Position,
        bot_pos: Position,
        target: Position,
    ) -> Position | None:
        """The throwable tile (dist^2 <= MAX_THROW_DIST_SQ from the Launcher)
        that ends up nearest to `target`.
        """
        width, height = ct.get_map_width(), ct.get_map_height()
        reach = int(MAX_THROW_DIST_SQ**0.5) + 1
        best: Position | None = None
        target_tiles = set(core_perimeter(target))
        best_key: tuple[int, int, int, int] | None = None

        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                dist_sq = dx * dx + dy * dy
                if dist_sq == 0 or dist_sq > MAX_THROW_DIST_SQ:
                    continue
                cand_x, cand_y = launcher_pos.x + dx, launcher_pos.y + dy
                if not (0 <= cand_x < width and 0 <= cand_y < height):
                    continue
                candidate = Position(cand_x, cand_y)
                if not ct.can_launch(bot_pos, candidate):
                    continue
                if use_path_aware_launch(ct, km):
                    remaining = path_distance(km, candidate, target_tiles)
                    if remaining is None:
                        continue
                else:
                    remaining = candidate.distance_squared(target)
                key = (
                    remaining,
                    candidate.distance_squared(target),
                    candidate.y,
                    candidate.x,
                )
                if best_key is None or key < best_key:
                    best = candidate
                    best_key = key

        return best
