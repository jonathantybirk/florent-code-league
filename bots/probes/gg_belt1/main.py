"""AREA 3c control: harvester -> CONVEYOR -> Core.  Arena `maps/lab/cd4.map26` (ore at (5,5)).

Core A anchor (2,5) -> footprint (2,5)(3,5)(2,6)(3,6).
Builder spawns at (4,4), steps to (4,5), builds the harvester at (5,5), steps back to
(4,4), builds the belt element at (4,5) facing WEST (output = core tile (3,5)),
then walks clear and idles for the rest of the match.

MEASURED 2026-08-02, fcode 2.3.3, vs `idle`:
    gg_belt1 (CONVEYOR, 3 Ti)  a_titanium_collected = 2490, a_titanium = 5433
    gg_belt2 (SPLITTER, 6 Ti)  a_titanium_collected = 2490, a_titanium = 5429
Identical throughput. A splitter costs twice as much and delivers nothing extra, and its
two unused output sides -- bare ground -- cost nothing either (see `a2split` for what
happens when those sides DO hold buildings). The belt is never the bottleneck: a harvester
emits one stack per 4 rounds and a conveyor moves one stack per round.

`a_titanium_collected` is the measurement; the probe also resigns at r995 (G29).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

W = Direction.WEST
CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
ORE = Position(5, 5)
BELT = Position(4, 5)
USE_SPLITTER = False


class Player:
    def __init__(self):
        self.spawned = False
        self.phase = 0
        self.built = None
        self.note = ""

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:6] + ":" + str(exc)[:20]

    def step(self, ct, pos, tgt):
        best = None
        for d in CARD:
            if not ct.can_move(d):
                continue
            s = pos.add(d).distance_squared(tgt)
            if best is None or s < best[0]:
                best = (s, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(4, 4)):
                ct.spawn_builder(Position(4, 4))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return
        pos = ct.get_position()

        if self.phase == 0:
            if pos != Position(4, 5):
                self.step(ct, pos, Position(4, 5))
                return
            if ct.can_build_harvester(ORE):
                ct.build_harvester(ORE)
                self.phase = 1
            return
        if self.phase == 1:
            if pos != Position(4, 4):
                self.step(ct, pos, Position(4, 4))
                return
            if USE_SPLITTER:
                if ct.can_build_splitter(BELT, W):
                    ct.build_splitter(BELT, W)
                    self.phase = 2
            else:
                if ct.can_build_conveyor(BELT, W):
                    ct.build_conveyor(BELT, W)
                    self.phase = 2
            return
        if self.phase == 2:
            if self.built is None:
                self.built = r
            if pos != Position(4, 3):
                self.step(ct, pos, Position(4, 3))
                return
            if r == 995:
                ct.resign(("BELT splitter=%s built_r=%s ti=%d %s" % (
                    USE_SPLITTER, self.built, ct.get_global_resources(),
                    self.note))[:495])
            return
