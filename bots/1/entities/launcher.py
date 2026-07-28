"""Launcher entity logic: throw an adjacent friendly builder bot as far northeast as possible."""

from __future__ import annotations

from fcode import Controller, Direction, Position

# Throw radius^2 = 26, measured from the Launcher (see game-rules-turrets.md)
_MAX_THROW_DIST_SQ = 26


class LauncherMixin:
    def run_launcher(self, ct: Controller) -> None:
        pos = ct.get_position()
        bot_pos = self._find_adjacent_builder(ct, pos)
        if bot_pos is None:
            return

        target = self._farthest_northeast_target(ct, pos, bot_pos)
        if target is not None:
            ct.launch(bot_pos, target)

    def _find_adjacent_builder(self, ct: Controller, pos: Position) -> Position | None:
        width, height = ct.get_map_width(), ct.get_map_height()
        for d in Direction:
            if d == Direction.CENTRE:
                continue
            check = pos.add(d)
            if not (0 <= check.x < width and 0 <= check.y < height):
                continue
            if ct.get_tile_builder_bot_id(check) is not None:
                return check
        return None

    def _farthest_northeast_target(
        self, ct: Controller, launcher_pos: Position, bot_pos: Position
    ) -> Position | None:
        """Search the throw radius for the tile furthest to the northeast.

        Northeast means +x (east), -y (north, since y increases southward).
        Among tiles at the greatest reachable distance, prefer the one
        closest to a true 45-degree northeast line.
        """
        width, height = ct.get_map_width(), ct.get_map_height()
        best: Position | None = None
        best_score: tuple[int, int] | None = None
        reach = int(_MAX_THROW_DIST_SQ**0.5) + 1

        for dx in range(0, reach + 1):
            for dy in range(-reach, 1):
                dist_sq = dx * dx + dy * dy
                if dist_sq == 0 or dist_sq > _MAX_THROW_DIST_SQ:
                    continue
                cand_x, cand_y = launcher_pos.x + dx, launcher_pos.y + dy
                if not (0 <= cand_x < width and 0 <= cand_y < height):
                    continue
                candidate = Position(cand_x, cand_y)
                if not ct.can_launch(bot_pos, candidate):
                    continue
                score = (dist_sq, -abs(dx + dy))
                if best_score is None or score > best_score:
                    best = candidate
                    best_score = score

        return best
