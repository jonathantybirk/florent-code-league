"""Control for `chain` (G02): identical build, but the belt dead-ends ONE TILE SHORT.

harvester(5,5) -> conveyor(4,5) facing WEST -> (3,5) left EMPTY, so nothing ever reaches the
Core footprint. If G02 still holds, `a_titanium_collected` is exactly 0 while `chain` scores
in the thousands.

MEASURED 2026-08-02, fcode 2.3.3, `maps/lab/belt.map26` vs `idle` (full 1000 rounds):
    a_titanium_collected = 0   a_titanium = 2943   win_condition = harvesters
It still BEAT `idle` (3000 banked, 0 collected) because the tiebreak order is
titanium_collected > harvesters > titanium_stored (G03): an unconnected harvester wins on
the second key while holding less titanium. Every 10-Ti stack the belt swallows is
annihilated -- 2943 = 500 - 57 spend + 2500 passive, with nothing added by the harvester.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(4, 5)

SCRIPT = [
    ("harv", Position(5, 5), None),
    ("mv", Direction.NORTH, None),          # (4,5) -> (4,4)
    ("conv", Position(4, 5), Direction.WEST),
    ("mv", Direction.NORTH, None),          # get out of the way; NO final conveyor
]


class Player:
    def __init__(self):
        self.spawned = False
        self.step = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            pass

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 5)):
                ct.spawn_builder(Position(3, 5))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        if self.step == 0 and pos != HOME:
            d = pos.cardinal_direction_to(HOME)
            if ct.can_move(d):
                ct.move(d)
            return
        if self.step >= len(SCRIPT):
            return
        kind, a, b = SCRIPT[self.step]
        ok = False
        if kind == "mv":
            if ct.can_move(a):
                ct.move(a)
                ok = True
        elif kind == "harv":
            if ct.can_build_harvester(a):
                ct.build_harvester(a)
                ok = True
        elif kind == "conv":
            if ct.can_build_conveyor(a, b):
                ct.build_conveyor(a, b)
                ok = True
        if ok:
            self.step += 1
