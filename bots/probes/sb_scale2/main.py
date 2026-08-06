"""SABOTAGE Q0b -- WHICH entities push the cost scale up?  Arena `dopen.map26`, vs noop.

sb_scale showed scale = 100% + 20% per unit and that it multiplies EVERY cost including the 3 Ti
conveyor.  If economy buildings counted, a defender rebuilding a cut link would pay a rising
price and sabotage would eventually win on its own.  This probe settles it: one builder plants
six conveyors in a row, then three barriers, then a harvester, then two gunners, sampling
(unit_count, scale, conveyor_cost, gunner_cost) after every single build.

Resigns from the builder at the end of the sequence.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
SPAWN = Position(4, 7)
STAND = Position(8, 9)
CONVS = (Position(7, 9), Position(9, 9), Position(8, 10), Position(8, 8),
         Position(7, 8), Position(9, 8))
BARRS = (Position(7, 10), Position(9, 10), Position(7, 7))
HARV = Position(9, 0)
GUNS = (Position(9, 7), Position(8, 7))


class Player:
    def __init__(self):
        self.spawned = False
        self.st = 0
        self.i = 0
        self.rows = []
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
                          ct.get_conveyor_cost(), ct.get_gunner_cost()))

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
        if self.st == 0:
            if p == STAND:
                self.sample(ct, "start")
                self.st = 1
            else:
                self.step(ct, p, STAND)
            return

        if self.st == 1:
            if self.i >= len(CONVS):
                self.i = 0
                self.st = 2
                return
            t = CONVS[self.i]
            if ct.can_build_conveyor(t, Direction.NORTH):
                ct.build_conveyor(t, Direction.NORTH)
                self.i += 1
                self.sample(ct, "conv%d" % self.i)
            else:
                self.i += 1
            return

        if self.st == 2:
            if self.i >= len(BARRS):
                self.i = 0
                self.st = 3
                return
            t = BARRS[self.i]
            if ct.can_build_barrier(t):
                ct.build_barrier(t)
                self.i += 1
                self.sample(ct, "barr%d" % self.i)
            else:
                self.i += 1
            return

        if self.st == 3:
            if self.i >= len(GUNS):
                self.st = 4
                return
            t = GUNS[self.i]
            if ct.can_build_gunner(t, Direction.NORTH):
                ct.build_gunner(t, Direction.NORTH)
                self.i += 1
                self.sample(ct, "gun%d" % self.i)
            else:
                self.i += 1
            return

        if self.st == 4:
            ct.resign("SBSCALE2 (tag,units,scale,conv,gun) %s ti=%d n=%s"
                      % (self.rows, ct.get_global_resources(), self.note))
            return
