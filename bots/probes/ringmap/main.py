"""Q1: enumerate the Core's spawn ring BY MEASUREMENT, not by assuming r^2<=2.

The Core scans the whole 8x8 offset block dx,dy in -3..4 around its own anchor and records
can_spawn for every tile.  That block strictly contains the claimed 4x4 ring, so if any legal
spawn target lies outside the 4x4 the grid will show it.

Three snapshots:
  r0  action cooldown 0, nothing built              -> the true ring
  r1  action cooldown BURNED by the r0 spawn        -> does can_spawn gate on cooldown?
  r3  cooldown recovered, one builder on a ring tile-> does a friendly BODY close a ring tile?

Legend per tile: 1 = can_spawn, 0 = cannot, . = out of bounds / raised.
Rows are dy = -3..4, columns dx = -3..4, so the anchor is at row 3 / col 3.

Reported by the CORE (M07) through resign (G29/M06).
"""

from fcode import Controller, EntityType, Position

LO, HI = -3, 5


class Player:
    def __init__(self):
        self.n = []
        self.bid = -1

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__)

    def _grid(self, ct, a, w, h):
        rows = []
        for dy in range(LO, HI):
            row = ""
            for dx in range(LO, HI):
                x, y = a.x + dx, a.y + dy
                if not (0 <= x < w and 0 <= y < h):
                    row += "."
                    continue
                try:
                    row += "1" if ct.can_spawn(Position(x, y)) else "0"
                except Exception:
                    row += "."
            rows.append(row)
        return ",".join(rows)

    def _run(self, ct):
        if ct.get_entity_type() != EntityType.CORE:
            return
        r = ct.get_current_round()
        a = ct.get_position()
        w, h = ct.get_map_width(), ct.get_map_height()

        if r == 0:
            self.n.append("a=%d,%d %dx%d cd=%d" % (a.x, a.y, w, h, ct.get_action_cooldown()))
            self.n.append("R0[" + self._grid(ct, a, w, h) + "]")
            # spawn on the first legal tile so the later snapshots have a body in the ring
            for dy in range(-1, 3):
                for dx in range(-1, 3):
                    p = Position(a.x + dx, a.y + dy)
                    if not (0 <= p.x < w and 0 <= p.y < h):
                        continue
                    try:
                        if ct.can_spawn(p):
                            self.bid = ct.spawn_builder(p)
                            self.n.append("spawn@%d,%d" % (dx, dy))
                            return
                    except Exception:
                        continue
            return

        if r == 1:
            self.n.append("R1cd=%d[" % ct.get_action_cooldown() + self._grid(ct, a, w, h) + "]")
            return

        if r == 3:
            self.n.append("R3cd=%d[" % ct.get_action_cooldown() + self._grid(ct, a, w, h) + "]")
            return

        if r == 4:
            self.n.append("u=%d ti=%d" % (ct.get_unit_count(), ct.get_global_resources()))
            ct.resign(" ".join(self.n)[:495])
