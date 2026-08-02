"""Q1 -- the EXACT global cost-scale formula, measured at every integer scale from 100 to ~149.

Arena `lab/csopen` (26x14, zero walls, Core A anchor (1,6)).  One Builder Bot serpentines through
three free rows dropping a BARRIER every second round.  A barrier is +1 percentage point, so the
team scale walks 100, 101, 102, ... one point at a time and the probe gets to read all eight cost
getters at EVERY integer scale in the range -- including both sides of every floor() edge.

At each new scale the probe checks  cost == floor(scale/100 * base)  for all eight entity types
using exact integer arithmetic (tenths * base // 1000), counts mismatches, checks that the
titanium actually deducted equals the advertised cost, and checks the scale never decreases.

The reporting builder only exists after the Core has already paid +20pp for it, so the round-0
baseline (scale with NOTHING built) is relayed through the 16-slot store: the Core writes
scale-tenths to slot 0 and the eight base costs to slots 1..8 on round 0, and the builder reads
them back (one-round write lag, G20).

Witnesses reported are the two scales that straddle a floor() edge for each base, chosen inside
the 120..169 band the route actually walks:
  base 3 -> 133/134 and 166/167   base 6 -> 133/134 and 149/150   base 10 -> 129/130
  base 20 -> 124/125              base 30 -> 123/124 and 166/167
"""

from fcode import Controller, Direction, EntityType, GameError, Position

SPAWN = Position(3, 6)
BASE = (3, 6, 20, 3, 10, 30, 20, 30)   # cv sp hv br gn st lu bb

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def _route():
    """(route positions, build target per route index).  Every consecutive pair is 1 cardinal step."""
    pts = []
    builds = []

    def add(x, y, b=None):
        pts.append(Position(x, y))
        builds.append(b)

    # leg 1: walk east along y=6, barrier at (x,5).  x=4 is left clear so the bot can climb later.
    add(4, 6, None)
    for x in range(5, 21):
        add(x, 6, Position(x, 5))
    # drop to y=8
    add(20, 7, None)
    add(20, 8, Position(20, 9))
    # leg 2: walk west along y=8, barrier at (x,9)
    for x in range(19, 4, -1):
        add(x, 8, Position(x, 9))
    # climb column x=4 (kept free of barriers) up to y=4
    add(4, 8, None)
    add(4, 7, None)
    add(4, 6, None)
    add(4, 5, None)
    add(4, 4, Position(4, 3))
    # leg 3: walk east along y=4, barrier at (x,3)
    for x in range(5, 21):
        add(x, 4, Position(x, 3))
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
        self.seen = {}
        self.mis = ""
        self.nmis = 0
        self.paymis = 0
        self.dec = 0
        self.prev = None
        self.smin = 10000
        self.smax = 0
        self.done = False
        self.err = ""
        self.r0 = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.err = "TOP:" + type(exc).__name__ + ":" + str(exc)[:24]

    # ------------------------------------------------------------------ record
    def record(self, ct):
        s = ct.get_scale_percent()
        t = int(round(s * 10))
        if self.prev is not None and t < self.prev:
            self.dec += 1
        self.prev = t
        self.smin = min(self.smin, t)
        self.smax = max(self.smax, t)
        if t in self.seen:
            return
        c = costs(ct)
        self.seen[t] = c
        for k in range(8):
            pred = (t * BASE[k]) // 1000
            if pred != c[k]:
                self.nmis += 1
                if not self.mis:
                    self.mis = "MIS s=%d k=%d got=%d pred=%d" % (t, k, c[k], pred)

    # ------------------------------------------------------------------ report
    def report(self, ct):
        w = []
        want = (("br", 3, 133, 134), ("br", 3, 166, 167), ("sp", 1, 133, 134),
                ("sp", 1, 149, 150), ("gn", 4, 129, 130), ("hv", 2, 124, 125),
                ("bb", 7, 123, 124), ("st", 5, 166, 167))
        for name, k, lo, hi in want:
            a = self.seen.get(lo * 10)
            b = self.seen.get(hi * 10)
            w.append("%s%d/%d=%s/%s" % (name, lo, hi,
                                        a[k] if a else "-", b[k] if b else "-"))
        base = "?"
        if self.r0:
            base = "%.1f:%s" % (self.r0[0] / 10.0, ",".join(str(v) for v in self.r0[1]))
        msg = "CSFORM obs=%d s=%.1f..%.1f mis=%d pay=%d dec=%d %s | r0=%s | %s" % (
            len(self.seen), self.smin / 10.0, self.smax / 10.0,
            self.nmis, self.paymis, self.dec, self.mis or self.err, base, " ".join(w))
        ct.resign(msg[:495])

    # ------------------------------------------------------------------ main
    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned:
                # relay the with-nothing-built baseline to the reporting builder (1-round lag)
                ct.write_store(0, int(round(ct.get_scale_percent() * 10)))
                for k, v in enumerate(costs(ct)):
                    ct.write_store(1 + k, v)
                if ct.can_spawn(SPAWN):
                    ct.spawn_builder(SPAWN)
                    self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return

        if self.r0 is None:
            t0 = ct.read_store(0)
            if t0:
                self.r0 = (t0, [ct.read_store(1 + k) for k in range(8)])
        self.record(ct)
        if self.i >= len(ROUTE) or ct.get_current_round() > 600:
            self.done = True
            self.report(ct)
            return

        pos = ct.get_position()
        tgt = ROUTE[self.i]
        if pos.x != tgt.x or pos.y != tgt.y:
            d = pos.cardinal_direction_to(tgt)
            if ct.can_move(d):
                ct.move(d)
                return
            # blocked -- skip this waypoint rather than deadlock
            self.i += 1
            return

        b = BUILDS[self.i]
        self.i += 1
        if b is None:
            return
        if not ct.can_build_barrier(b):
            return
        want = ct.get_barrier_cost()
        ti0 = ct.get_global_resources()
        ct.build_barrier(b)
        paid = ti0 - ct.get_global_resources()
        if paid != want and paid != want - 10:
            self.paymis += 1
        self.record(ct)
