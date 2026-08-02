"""DEFENCE Q5 -- how much board does each turret actually cover, and what does it cost?

Arena `maps/lab/dopen.map26`, vs noop.  No buildings are constructed: `get_attackable_tiles_from`
is callable from a plain Builder Bot (G34) and ignores ammo, cooldown and occupancy, so one
builder standing in open ground at (10,6) can enumerate every turret's raw pattern for free.

Answers: coverage tiles per turret type, whether turrets may face DIAGONAL directions (which
decides how many turrets a Core ring needs), and the base cost of every defensive piece.
The BUILDER is the reporter (M07).
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
ROUTE = [(5, 7), (6, 7), (7, 7), (8, 7), (9, 7), (10, 7), (10, 6)]
HERE = Position(10, 6)
CARD8 = (Direction.NORTH, Direction.NORTHEAST, Direction.EAST, Direction.SOUTHEAST,
         Direction.SOUTH, Direction.SOUTHWEST, Direction.WEST, Direction.NORTHWEST)


class Player:
    def __init__(self):
        self.spawned = False
        self.leg = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def scan(self, ct, et):
        out = []
        for d in CARD8:
            try:
                ts = ct.get_attackable_tiles_from(HERE, d, et)
            except Exception:
                out.append("x")
                continue
            m = 0
            for t in ts:
                q = t.distance_squared(HERE)
                if q > m:
                    m = q
            out.append("%d/%d" % (len(ts), m))
        return out

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(4, 7)):
                ct.spawn_builder(Position(4, 7))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        p = ct.get_position()
        if self.leg < len(ROUTE):
            if (p.x, p.y) == ROUTE[self.leg]:
                self.leg += 1
                return
            t = ROUTE[self.leg]
            d = DIRS.get((t[0] - p.x, t[1] - p.y))
            if d is not None and ct.can_move(d):
                ct.move(d)
            return
        self.done = True
        g = self.scan(ct, EntityType.GUNNER)
        s = self.scan(ct, EntityType.SENTINEL)
        ln = self.scan(ct, EntityType.LAUNCHER)
        dg = []
        for d in (Direction.NORTH, Direction.NORTHEAST):
            ok = 0
            try:
                ok = 1 if ct.can_build_gunner(Position(10, 5), d) else 0
            except Exception:
                ok = 9
            dg.append("%d" % ok)
        ct.resign("DFORT n/maxd2 by N,NE,E,SE,S,SW,W,NW GUN=%s SENT=%s LAUN=%s "
                  "buildgun N/NE=%s cost barr=%d gun=%d sent=%d laun=%d harv=%d bot=%d s=%.0f"
                  % (",".join(g), ",".join(s), ",".join(ln), ",".join(dg),
                     ct.get_barrier_cost(), ct.get_gunner_cost(), ct.get_sentinel_cost(),
                     ct.get_launcher_cost(), ct.get_harvester_cost(),
                     ct.get_builder_bot_cost(), ct.get_scale_percent()))
