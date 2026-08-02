"""Q1/Q6 -- how high can the global cost scale go, and is there a CAP?

Gunners are the cheapest scale inflation in the game: +10 percentage points for floor(0.10*scale)
titanium, i.e. 1 Ti per point per 100% of scale.  (Builder/sentinel cost 1.5 Ti per point per
100%, launcher 2, barrier/conveyor 3, splitter 6, harvester 4.)  So the fastest legal way to drive
the team scale to its ceiling is to build gunners and nothing else.  Global ammo is never
converted, so the team-blind gunners (G10) never fire and never disturb the experiment.

Arena `lab/csopen` (26x14, zero walls).  One Builder Bot runs a six-row serpentine off a clear
vertical highway at x=4, building a gunner at every waypoint and WAITING in place whenever the
next gunner is unaffordable.  It re-checks cost == floor(scale/100 * base) for all eight types at
every new scale value, so the formula is verified far outside the 100..170 band cs_form covers.

Once MAX_TEAM_UNITS blocks any further gunner the probe falls back to BARRIERS (+1pp each, and
buildings are exempt from the unit cap), so the scale keeps climbing on whatever titanium is left.
That is the highest scale reachable inside one 1000-round game, and therefore the strongest
statement this engine allows about whether the scale has a ceiling at all.

Also reports get_unit_count() so a turret can be classified as a "unit" or not against
MAX_TEAM_UNITS = 50, and the GameError text from the first build that is refused.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

SPAWN = Position(3, 6)
BASE = (3, 6, 20, 3, 10, 30, 20, 30)   # cv sp hv br gn st lu bb
HIWAY = 4                              # column kept permanently clear
XLO, XHI = 5, 21
PAIRS = ((6, 5), (8, 9), (4, 3), (10, 11), (2, 1), (12, 13))
REPORT_ROUND = 940


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


def costs(ct):
    return (ct.get_conveyor_cost(), ct.get_splitter_cost(), ct.get_harvester_cost(),
            ct.get_barrier_cost(), ct.get_gunner_cost(), ct.get_sentinel_cost(),
            ct.get_launcher_cost(), ct.get_builder_bot_cost())


class Player:
    def __init__(self):
        self.spawned = False
        self.i = 0
        self.n = 0
        self.nb = 0
        self.capped = False
        self.seen = set()
        self.nmis = 0
        self.mis = ""
        self.dec = 0
        self.prev = None
        self.smax = 0
        self.err = ""
        self.done = False
        self.stuck = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            if not self.err:
                self.err = "TOP:" + type(exc).__name__ + ":" + str(exc)[:30]

    def record(self, ct):
        s = ct.get_scale_percent()
        t = int(round(s * 10))
        if self.prev is not None and t < self.prev:
            self.dec += 1
        self.prev = t
        self.smax = max(self.smax, t)
        if t in self.seen:
            return
        self.seen.add(t)
        c = costs(ct)
        for k in range(8):
            pred = (t * BASE[k]) // 1000
            if pred != c[k]:
                self.nmis += 1
                if not self.mis:
                    self.mis = "MIS s=%d k=%d got=%d pred=%d" % (t, k, c[k], pred)

    def report(self, ct):
        self.done = True
        ct.resign(("CSHIGH gun=%d barr=%d smax=%.1f obs=%d mis=%d dec=%d ucount=%d ti=%d "
                   "gcost=%d bcost=%d hcost=%d %s %s" % (
                       self.n, self.nb, self.smax / 10.0, len(self.seen), self.nmis, self.dec,
                       ct.get_unit_count(), ct.get_global_resources(),
                       ct.get_gunner_cost(), ct.get_barrier_cost(),
                       ct.get_harvester_cost(), self.mis, self.err))[:495])

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return

        self.record(ct)
        r = ct.get_current_round()
        if r >= REPORT_ROUND or self.i >= len(ROUTE):
            self.report(ct)
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
        if not self.capped:
            if ct.get_global_resources() < ct.get_gunner_cost():
                return                               # wait in place for passive income
            if ct.can_build_gunner(b, Direction.NORTH):
                ct.build_gunner(b, Direction.NORTH)
                self.n += 1
                self.i += 1
                self.record(ct)
                return
            self.capped = True
            self.err = "CAP@%d,%d gun=%d u=%d s=%.1f" % (
                b.x, b.y, self.n, ct.get_unit_count(), ct.get_scale_percent())
            return
        # unit cap reached -- buildings are exempt, so keep inflating with barriers
        if ct.get_global_resources() < ct.get_barrier_cost():
            return
        if not ct.can_build_barrier(b):
            self.i += 1
            return
        ct.build_barrier(b)
        self.nb += 1
        self.i += 1
        self.record(ct)
