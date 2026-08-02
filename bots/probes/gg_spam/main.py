"""Opponent for the spawn-ring lockout test: spawn a builder every round it is legal,
and walk each builder EAST off the spawn ring so the ring does not clog with its own units.

`b_units` in the run_game result dict is the count of builders it managed to produce.
"""

from fcode import Controller, Direction, EntityType, GameError, Position


class Player:
    def __init__(self):
        self.n = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("GGPROBE|SPAMEXC %s %s" % (type(exc).__name__, str(exc)[:30]))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            a = ct.get_position()
            for dx in (-1, 0, 1, 2):
                for dy in (-1, 0, 1, 2):
                    p = Position(a.x + dx, a.y + dy)
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        self.n += 1
                        if self.n <= 3 or self.n % 10 == 0:
                            print("GGPROBE|SPAWNED n=%d r=%d at=%d,%d" % (
                                self.n, ct.get_current_round(), p.x, p.y))
                        return
            if ct.get_current_round() % 100 == 0:
                print("GGPROBE|NOSPAWN r=%d total=%d" % (ct.get_current_round(), self.n))
            return
        if et != EntityType.BUILDER_BOT:
            return
        for d in (Direction.WEST, Direction.NORTH, Direction.SOUTH, Direction.EAST):
            if ct.can_move(d):
                ct.move(d)
                return
