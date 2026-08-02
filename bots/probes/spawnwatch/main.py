"""AREA-2 opponent/observer: report how many of MY OWN 12 spawn-ring tiles still accept can_spawn.

Never spawns anything, so the only thing that can ever close a ring tile is the enemy.
Resigns at round 120 with a sampled series, so `ringlock` can be scored on rounds-to-lock.
"""

from fcode import Controller, EntityType, GameError, Position


class Player:
    def __init__(self):
        self.n = []
        self.ring = None
        self.locked = -1

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        if ct.get_entity_type() != EntityType.CORE:
            return
        r = ct.get_current_round()
        if self.ring is None:
            p = ct.get_position()
            w, h = ct.get_map_width(), ct.get_map_height()
            foot = ((0, 0), (1, 0), (0, 1), (1, 1))
            self.ring = []
            for dx in range(-1, 3):
                for dy in range(-1, 3):
                    if (dx, dy) in foot:
                        continue
                    t = Position(p.x + dx, p.y + dy)
                    if 0 <= t.x < w and 0 <= t.y < h:
                        self.ring.append(t)
            self.n.append("ring=%d" % len(self.ring))

        ok = 0
        for t in self.ring:
            try:
                if ct.can_spawn(t):
                    ok += 1
            except Exception:
                pass
        if ok == 0 and self.locked < 0:
            self.locked = r
        if r % 10 == 0 and r <= 120:
            self.n.append("r%d:%d" % (r, ok))
        if r == 121:
            self.n.append("LOCKED_AT=%d ti=%d" % (self.locked, ct.get_global_resources()))
            ct.resign(" ".join(self.n)[:495])
