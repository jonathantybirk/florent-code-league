"""Q6 -- MAX_TEAM_UNITS = 50: what exactly does it count, and what happens at the ceiling?

Same gunner-serpentine engine as `cs_high` (gunners are the cheapest scale/titanium, and with
global ammo left at 0 the team-blind turrets never fire), but this probe keeps going once the
ceiling is hit and interrogates it:

  A  get_unit_count() and the GameError text from build_gunner() at the ceiling
  B  can_build_barrier() / build_barrier() at the ceiling -- do BUILDINGS count against the cap?
     (barrier is +1pp, so the scale also proves the build really happened)
  C  the Core relays its own can_spawn() through store slot 1 -- is spawning blocked too?
  D  destroy() one gunner and immediately build a replacement -- is removal a release valve?

Arena `lab/csopen`.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

SPAWN = Position(3, 6)
HIWAY = 4
XLO, XHI = 5, 21
PAIRS = ((6, 5), (8, 9), (4, 3), (10, 11), (2, 1), (12, 13))


def _route():
    pts, builds = [], []

    def add(x, y, b=None):
        pts.append(Position(x, y))
        builds.append(b)

    add(HIWAY, PAIRS[0][0])
    cur = PAIRS[0][0]
    for walk_y, build_y in PAIRS:
        step = 1 if walk_y > cur else -1
        for y in range(cur + step, walk_y + step, step):
            add(HIWAY, y)
        cur = walk_y
        for x in range(XLO, XHI + 1):
            add(x, walk_y, Position(x, build_y))
        for x in range(XHI - 1, HIWAY - 1, -1):
            add(x, walk_y)
    return pts, builds


ROUTE, BUILDS = _route()
CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def e(exc):
    return type(exc).__name__[:4] + ":" + str(exc)[:26]


class Player:
    def __init__(self):
        self.spawned = False
        self.i = 0
        self.n = 0
        self.note = []
        self.phase = 0
        self.cap_at = None
        self.done = False
        self.stuck = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note.append("!" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            ct.write_store(1, 1 if ct.can_spawn(Position(3, 7)) else 0)
            ct.write_store(2, ct.get_unit_count())
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return

        r = ct.get_current_round()
        if r > 960:
            self.finish(ct)
            return

        if self.phase == 0:
            self.grow(ct)
            return
        self.probe_cap(ct)

    # ---------------------------------------------------------------- phase 0
    def grow(self, ct):
        if self.i >= len(ROUTE):
            self.phase = 1
            return
        pos = ct.get_position()
        tgt = ROUTE[self.i]
        if pos.x != tgt.x or pos.y != tgt.y:
            d = pos.cardinal_direction_to(tgt)
            if ct.can_move(d):
                ct.move(d)
                self.stuck = 0
                return
            self.stuck += 1
            if self.stuck > 3:
                self.stuck = 0
                self.i += 1
            return
        b = BUILDS[self.i]
        if b is None:
            self.i += 1
            return
        if ct.get_global_resources() < ct.get_gunner_cost():
            return
        if ct.can_build_gunner(b, Direction.NORTH):
            ct.build_gunner(b, Direction.NORTH)
            self.n += 1
            self.i += 1
            return
        # ceiling
        self.cap_at = b
        self.phase = 1
        self.note.append("CAP n=%d u=%d s=%.0f ti=%d" % (
            self.n, ct.get_unit_count(), ct.get_scale_percent(),
            ct.get_global_resources()))
        try:
            ct.build_gunner(b, Direction.NORTH)
            self.note.append("forced=OK")
        except Exception as exc:
            self.note.append("forced=" + e(exc))

    # ---------------------------------------------------------------- phase 1
    def probe_cap(self, ct):
        pos = ct.get_position()
        if len(self.note) < 3:
            spot = None
            for d in CARD:
                p = pos.add(d)
                if ct.can_build_barrier(p):
                    spot = p
                    break
            if spot is None:
                self.note.append("nobarrspot")
                return
            ct.build_barrier(spot)
            self.note.append("barr=OK u=%d s=%.0f corespawn=%d coreu=%d" % (
                ct.get_unit_count(), ct.get_scale_percent(),
                ct.read_store(1), ct.read_store(2)))
            return

        if len(self.note) == 3:
            # step back so the previously built gunner is orthogonally adjacent
            tgt = Position(pos.x - 1, pos.y)
            if ct.can_move(Direction.WEST):
                ct.move(Direction.WEST)
            self.note.append("stepW->%d,%d" % (tgt.x, tgt.y))
            return

        if len(self.note) == 4:
            g = Position(pos.x, self.cap_at.y) if self.cap_at else None
            if g is None:
                self.finish(ct)
                return
            try:
                ct.destroy(g)
                self.note.append("des u=%d s=%.0f" % (
                    ct.get_unit_count(), ct.get_scale_percent()))
            except Exception as exc:
                self.note.append("des!" + e(exc))
            return

        if len(self.note) == 5:
            g = Position(pos.x, self.cap_at.y)
            if ct.get_global_resources() < ct.get_gunner_cost():
                return                                # wait for passive income, not a cap block
            try:
                ct.build_gunner(g, Direction.NORTH)
                self.note.append("refill=OK u=%d s=%.0f" % (
                    ct.get_unit_count(), ct.get_scale_percent()))
            except Exception as exc:
                self.note.append("refill!" + e(exc))
            return

        self.finish(ct)

    def finish(self, ct):
        self.done = True
        ct.resign(("CSCAP gun=%d u=%d s=%.0f | %s" % (
            self.n, ct.get_unit_count(), ct.get_scale_percent(),
            " | ".join(self.note)))[:495])
