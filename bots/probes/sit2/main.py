"""Opponent: spawn exactly ONE Builder Bot on the first legal ring tile and never move it.

Used by `botshot` to get an enemy Builder Bot to stand still on a tile with no building under it,
so the question "can a Builder Bot's adjacent attack hit a BOT, or only a building?" can be asked
of a real target. Deliberately builds nothing: the target tile must hold a bot and nothing else.
"""

from fcode import Controller, EntityType, Position


class Player:
    def __init__(self):
        self.spawned = False

    def run(self, ct: Controller) -> None:
        try:
            if ct.get_entity_type() != EntityType.CORE or self.spawned:
                return
            pos = ct.get_position()
            foot = ((0, 0), (1, 0), (0, 1), (1, 1))
            w, h = ct.get_map_width(), ct.get_map_height()
            for dx in range(-1, 3):
                for dy in range(-1, 3):
                    if (dx, dy) in foot:
                        continue
                    t = Position(pos.x + dx, pos.y + dy)
                    if not (0 <= t.x < w and 0 <= t.y < h):
                        continue
                    try:
                        if ct.can_spawn(t):
                            ct.spawn_builder(t)
                            self.spawned = True
                            return
                    except Exception:
                        continue
        except Exception:
            return
