"""AREA 3a: map the Core's ACTION radius by scanning can_build_barrier / can_spawn.

Arena `corelab`: Core A anchor (6,9); footprint (6,9)(7,9)(6,10)(7,10).
Scan offsets dx,dy in -3..+5 (9x9 block centred on the footprint).
Row-major, y outer, printed as one 81-char string per grid.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

OFF = (-3, -2, -1, 0, 1, 2, 3, 4, 5)


class Player:
    def __init__(self):
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("GGP|TOP:" + type(exc).__name__ + ":" + str(exc)[:60])
            except Exception:
                pass

    def _run(self, ct):
        if ct.get_entity_type() != EntityType.CORE or self.done:
            return
        if ct.get_current_round() != 0:
            return
        self.done = True
        p = ct.get_position()

        def grid(fn):
            s = ""
            for dy in OFF:
                for dx in OFF:
                    q = Position(p.x + dx, p.y + dy)
                    try:
                        s += "1" if fn(q) else "0"
                    except Exception:
                        s += "X"
            return s

        bar = grid(ct.can_build_barrier)
        spn = grid(ct.can_spawn)
        cnv = grid(lambda q: ct.can_build_conveyor(q, Direction.EAST))
        ct.resign("GGP|anchor=%d,%d|BAR=%s|SPN=%s|CNV=%s" % (p.x, p.y, bar, spn, cnv))
