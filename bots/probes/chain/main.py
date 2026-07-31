"""Probe G01-G04 on 2.3.3: what does titanium_collected actually count?

Arena `belt`: Core A anchor (1,5) -> footprint {(1,5),(2,5),(1,6),(2,6)}; ore at (5,5).
Builds the FULL chain  harvester(5,5) -> conveyor(4,5)W -> conveyor(3,5)W -> Core tile (2,5)
and then does nothing for the rest of the match. Never resigns, so the match runs the full
1000 rounds and `a_titanium_collected` in the result dict is the measurement.

Compare with the `chainshort` probe, which is identical but omits the last conveyor, so the
belt dead-ends one tile short of the Core footprint.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(4, 5)

SCRIPT = [
    ("harv", Position(5, 5), None),
    ("mv", Direction.NORTH, None),          # (4,5) -> (4,4)
    ("conv", Position(4, 5), Direction.WEST),
    ("mv", Direction.WEST, None),           # (4,4) -> (3,4)
    ("conv", Position(3, 5), Direction.WEST),
    ("mv", Direction.NORTH, None),          # get out of the way
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
