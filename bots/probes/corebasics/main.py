"""Probe G33 / G23 / G31 / spawn radius / passability on 2.3.3, reported from the Core.

  C1 (G33) is get_position() the TOP-LEFT anchor of the Core's 2x2 footprint?
  C2 (G23) does get_tile_env() still raise outside vision? what about out of bounds?
  C3 (G31) does a Builder Bot act on the round it is spawned?  (builder stamps the store)
  C4 core spawn radius: which offsets accept can_spawn()?
  C5 is_tile_passable on our own Core footprint, and on a tile holding a friendly building.
"""

from fcode import Controller, Direction, EntityType, GameError, Position


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:22]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.stamped = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.BUILDER_BOT:
            # C3: stamp our first-seen round + 100 into slot 1 (0 means "never ran").
            if not self.stamped:
                self.stamped = True
                ct.write_store(1, r + 100)
            return

        if et != EntityType.CORE:
            return

        if r == 0:
            p = ct.get_position()
            me = ct.get_id()
            foot = []
            for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0), (0, -1), (2, 0), (0, 2)):
                q = Position(p.x + dx, p.y + dy)
                try:
                    bid = ct.get_tile_building_id(q)
                except Exception:
                    bid = "X"
                foot.append("1" if bid == me else ("0" if bid is None else "?"))
            self.n.append("C1 pos=%d,%d foot(00,10,01,11,-10,0-1,20,02)=%s" % (
                p.x, p.y, "".join(foot)))

            # C4: spawn radius shape over the 5x5 block around the anchor.
            rows = []
            for dy in (-1, 0, 1, 2):
                row = ""
                for dx in (-1, 0, 1, 2):
                    try:
                        row += "1" if ct.can_spawn(Position(p.x + dx, p.y + dy)) else "0"
                    except Exception:
                        row += "X"
                rows.append(row)
            self.n.append("C4 spawn=" + ",".join(rows))

            # C5: passability of our own footprint
            self.n.append("C5 ownfoot pass=%s empty=%s" % (
                ct.is_tile_passable(p), ct.is_tile_empty(p)))

            if ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
                self.spawned = True
            return

        if r == 1:
            p = ct.get_position()
            # C2: vision. Core vision r^2=36 -> 6 tiles.
            far = Position(p.x + 15, p.y)
            oob = Position(-1, -1)
            for label, q in (("far", far), ("oob", oob)):
                try:
                    v = ct.get_tile_env(q)
                    self.n.append("C2 %s env=%s invis=%s" % (label, v, ct.is_in_vision(q)))
                except Exception as exc:
                    self.n.append("C2 %s " % label + e(exc))
            return

        if r == 4:
            self.n.append("C3 builder_first_round=%d (core spawned r0)" % (
                ct.read_store(1) - 100))
            ct.resign(" | ".join(self.n[:8]))
