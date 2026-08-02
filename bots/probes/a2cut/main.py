"""ECON Q1/Q2: cut the FINAL conveyor of a working chain, then put it back.

Arena `maps/lab/belt.map26` (20x12): Core A anchor (1,5) -> footprint (1,5)(2,5)(1,6)(2,6),
ore at (5,5).

The builder spawns on ring tile (3,4) and lays
    harvester(5,5) -> conveyor(4,5) WEST -> conveyor(3,5) WEST -> Core tile (2,5)
then parks on (3,4) forever, from where it can destroy AND rebuild (3,5) at will.

  round 300  ct.destroy((3,5))              -- the chain now dead-ends one tile short
  round 600  rebuild conveyor (3,5) WEST    -- does the backed-up titanium flush?

Instrumentation: every round it samples the stack id sitting on conveyor (4,5) and on the
harvester, counts how many DISTINCT stacks pass through (4,5) in each phase, and records the
longest run of consecutive rounds during which (4,5) held the same stack (= jam length).
Treasury is checkpointed every 100 rounds; the chain contributes +10 Ti per 4 rounds on top
of the +10/4 passive, so the slope of `ti` is the whole answer to "how much is denied".

Reports with ct.resign() at round 995 (G29/M06); `a_titanium_collected` in the result dict is
the second, independent measurement.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HARV = Position(5, 5)
MID = Position(4, 5)
TAIL = Position(3, 5)
PARK = Position(3, 4)
CUT_ROUND = 300
FIX_ROUND = 600

SCRIPT = (
    ("mv", Direction.EAST, None),
    ("mv", Direction.EAST, None),
    ("harv", HARV, None),
    ("mv", Direction.WEST, None),
    ("conv", MID, Direction.WEST),
    ("mv", Direction.WEST, None),
    ("conv", TAIL, Direction.WEST),
)


class Player:
    def __init__(self):
        self.spawned = False
        self.step = 0
        self.built_round = None
        self.ti = []
        self.seen = [0, 0, 0]
        self.prev = None
        self.hold = 0
        self.maxhold = [0, 0, 0]
        self.harvfull = [0, 0, 0]
        self.cut = False
        self.fixed = False
        self.note = ""

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:6] + ":" + str(exc)[:20]

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(PARK):
                ct.spawn_builder(PARK)
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        if self.step < len(SCRIPT):
            kind, a, b = SCRIPT[self.step]
            ok = False
            if kind == "mv" and ct.can_move(a):
                ct.move(a)
                ok = True
            elif kind == "harv" and ct.can_build_harvester(a):
                ct.build_harvester(a)
                ok = True
            elif kind == "conv" and ct.can_build_conveyor(a, b):
                ct.build_conveyor(a, b)
                ok = True
            if ok:
                self.step += 1
                if self.step == len(SCRIPT):
                    self.built_round = r
            return

        phase = 0 if r < CUT_ROUND else (1 if r < FIX_ROUND else 2)
        self._sample(ct, phase)

        if r % 100 == 0 and len(self.ti) < 10:
            self.ti.append(ct.get_global_resources())

        if r == CUT_ROUND and not self.cut:
            if ct.can_destroy(TAIL):
                ct.destroy(TAIL)
                self.cut = True
            return
        if r == FIX_ROUND and not self.fixed:
            if ct.can_build_conveyor(TAIL, Direction.WEST):
                ct.build_conveyor(TAIL, Direction.WEST)
                self.fixed = True
            return

        if r == 995:
            ct.resign(self._msg())

    def _sample(self, ct, phase):
        mid = ct.get_tile_building_id(MID)
        sid = None
        if mid is not None:
            sid = ct.get_stored_resource_id(mid)
        if sid is not None:
            if sid == self.prev:
                self.hold += 1
            else:
                self.hold = 1
                self.seen[phase] += 1
            if self.hold > self.maxhold[phase]:
                self.maxhold[phase] = self.hold
        else:
            self.hold = 0
        self.prev = sid

        hid = ct.get_tile_building_id(HARV)
        if hid is not None:
            try:
                if ct.get_stored_resource_id(hid) is not None:
                    self.harvfull[phase] += 1
            except Exception:
                self.harvfull[phase] = -1

    def _msg(self):
        return ("CUT r%d/%d built=%s|ti=%s|stacks p1=%d p2=%d p3=%d|jam p1=%d p2=%d p3=%d"
                "|harvheld=%s|%s" % (
                    CUT_ROUND, FIX_ROUND, self.built_round,
                    ",".join(str(v) for v in self.ti),
                    self.seen[0], self.seen[1], self.seen[2],
                    self.maxhold[0], self.maxhold[1], self.maxhold[2],
                    self.harvfull, self.note))[:495]
