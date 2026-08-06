"""SABOTAGE Q0b -- WHICH entities push the cost scale up?  Arena `dopen.map26`, vs noop.

sb_scale showed scale = 100% + 20% per *unit* and that it multiplies EVERY cost including the 3 Ti
conveyor.  If economy buildings counted the same, a defender rebuilding a cut link would pay a
rising price and sabotage would win on its own.  This probe settles the attribution: one builder
walks along row y=9 planting things on row y=8 -- six conveyors, three barriers, a harvester on
the (10,11) ore, then two gunners -- and samples (unit_count, scale, conveyor_cost, gunner_cost,
barrier_cost) immediately after every successful build.

Resigns from the builder once the script is done.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
SPAWN = Position(4, 7)

# (kind, target) -- the builder always stands one tile SOUTH of target and builds NORTH.
SCRIPT = (
    ("conv", Position(5, 8)), ("conv", Position(6, 8)), ("conv", Position(7, 8)),
    ("conv", Position(8, 8)), ("conv", Position(9, 8)), ("conv", Position(10, 8)),
    ("barr", Position(11, 8)), ("barr", Position(12, 8)), ("barr", Position(13, 8)),
    ("harv", Position(9, 0)),
    ("gun", Position(14, 8)), ("gun", Position(15, 8)), ("gun", Position(16, 8)),
)


class Player:
    def __init__(self):
        self.spawned = False
        self.i = 0
        self.rows = []
        self.done = False
        self.note = ""

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:8] + ":" + str(exc)[:40]

    def step(self, ct, pos, tgt):
        best = None
        for d in CARD:
            if not ct.can_move(d):
                continue
            sc = pos.add(d).distance_squared(tgt)
            if best is None or sc < best[0]:
                best = (sc, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])

    def sample(self, ct, tag):
        self.rows.append((tag, ct.get_unit_count(), int(ct.get_scale_percent()),
                          ct.get_conveyor_cost(), ct.get_gunner_cost(),
                          ct.get_barrier_cost()))

    def _run(self, ct):
        et = ct.get_entity_type()

        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        p = ct.get_position()

        if self.done:
            ct.resign("SBSCALE2 (tag,units,scale,conv,gun,barr) %s ti=%d n=%s"
                      % (self.rows, ct.get_global_resources(), self.note))
            return

        if self.i >= len(SCRIPT):
            self.done = True
            return

        kind, tgt = SCRIPT[self.i]
        stand = Position(tgt.x, tgt.y + 1)
        if p != stand:
            if not self.rows:
                self.sample(ct, "start")
            self.step(ct, p, stand)
            return

        ok = False
        if kind == "conv" and ct.can_build_conveyor(tgt, Direction.NORTH):
            ct.build_conveyor(tgt, Direction.NORTH)
            ok = True
        elif kind == "barr" and ct.can_build_barrier(tgt):
            ct.build_barrier(tgt)
            ok = True
        elif kind == "harv" and ct.can_build_harvester(tgt):
            ct.build_harvester(tgt)
            ok = True
        elif kind == "gun" and ct.can_build_gunner(tgt, Direction.NORTH):
            ct.build_gunner(tgt, Direction.NORTH)
            ok = True
        if ok:
            self.sample(ct, "%s%d" % (kind, self.i))
        self.i += 1
        return
