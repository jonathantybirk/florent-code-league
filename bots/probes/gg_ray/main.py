"""AREA 3b: turret ray geometry -- diagonal facings, wall penetration, true range.

can_fire_from() only accepts positions inside the caller's own vision (r^2 = 20 for a
builder), so the builder builds four barrier targets, then walks to a query station beside
each one.

Arena `diaglab` (26x22). Walls at (11,12), (10,11), (7,5). Core A anchor (2,10).

  B1 (11,11) : first NE step from (10,12); flanked by walls (11,12) and (10,11).
               Does a DIAGONAL ray slip through the corner between two walls?
  B2 (8,5)   : behind the wall (7,5) on the cardinal ray from (5,5) facing EAST.
  B3 (10,7)  : 5 tiles EAST of (5,7). Gunner cardinal max is 3, Sentinel 5.
  B4 (18,10) : 4 NE steps from (14,14), d^2 = 32. Gunner diagonal max is 2.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

NE = Direction.NORTHEAST
E = Direction.EAST
G = EntityType.GUNNER
S = EntityType.SENTINEL

JOBS = [
    (Position(12, 11), Position(11, 11)),
    (Position(9, 5), Position(8, 5)),
    (Position(10, 8), Position(10, 7)),
    (Position(18, 11), Position(18, 10)),
]

# (station, [(label, turret_pos, facing, type, target)])
STATIONS = [
    (Position(12, 12), [
        ("Gcorner", Position(10, 12), NE, G, Position(11, 11)),
        ("Scorner", Position(10, 12), NE, S, Position(11, 11)),
    ]),
    (Position(9, 5), [
        ("Gwall", Position(5, 5), E, G, Position(8, 5)),
        ("Swall", Position(5, 5), E, S, Position(8, 5)),
    ]),
    (Position(8, 8), [
        ("Gfar5", Position(5, 7), E, G, Position(10, 7)),
        ("Sfar5", Position(5, 7), E, S, Position(10, 7)),
        ("Gnear3", Position(7, 7), E, G, Position(10, 7)),
    ]),
    (Position(16, 12), [
        ("Gdiag4", Position(14, 14), NE, G, Position(18, 10)),
        ("Sdiag4", Position(14, 14), NE, S, Position(18, 10)),
        ("Sdiag2", Position(16, 12), NE, S, Position(18, 10)),
    ]),
]


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:14]


class Player:
    def __init__(self):
        self.i = 0
        self.j = 0
        self.out = []
        self.built = ""
        self.done = False
        self.spawned = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.out.append("T:" + e(exc))

    def step(self, ct, pos, tgt):
        best = None
        for d in (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST):
            if not ct.can_move(d):
                continue
            q = pos.add(d)
            sc = q.distance_squared(tgt)
            if best is None or sc < best[0]:
                best = (sc, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(4, 10)):
                ct.spawn_builder(Position(4, 10))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        pos = ct.get_position()

        r = ct.get_current_round()
        if r % 10 == 0:
            print("GGPROBE|r=%d i=%d j=%d at=%d,%d out=%s" % (
                r, self.i, self.j, pos.x, pos.y, ";".join(self.out)))
        if r > 300:
            self.done = True
            ct.resign("GGP|STUCK i=%d j=%d at=%d,%d|%s" % (
                self.i, self.j, pos.x, pos.y, "|".join(self.out)))
            return

        if self.i < len(JOBS):
            stand, site = JOBS[self.i]
            if pos != stand:
                self.step(ct, pos, stand)
                return
            if ct.get_tile_building_id(site) is not None:
                self.i += 1
                return
            if ct.can_build_barrier(site):
                ct.build_barrier(site)
                self.i += 1
            return

        if self.j < len(STATIONS):
            station, qs = STATIONS[self.j]
            if pos != station:
                self.step(ct, pos, station)
                return
            for (label, p, d, ty, t) in qs:
                try:
                    self.out.append("%s=%d" % (label, 1 if ct.can_fire_from(p, d, ty, t) else 0))
                except Exception as exc:
                    self.out.append("%s!%s" % (label, e(exc)))
            self.j += 1
            return

        self.done = True
        print("GGPROBE|FINAL " + "|".join(self.out))
        ct.resign("GGP|" + "|".join(self.out))
