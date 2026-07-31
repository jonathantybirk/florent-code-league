"""Probe G07 on 2.3.3: cost scaling.

2.2.0 finding: one global scale across all entity types, cost = floor(scale x base);
builder +20 percentage points, gunner +10, harvester +5, conveyor/splitter/barrier +1.
The 2.3.3 docs additionally claim sentinel +20 and launcher +10, and say get_scale_percent()
returns 1.0 at base -- but the type stub says 100.0. Measure everything.

Arena `scal`: ore at (6,8) and (6,10), both orthogonally adjacent to a builder parked at (6,9),
so each scaling step is taken without moving.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(6, 9)


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.ph = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__ + str(exc)[:30])

    def snap(self, ct, label):
        # scale, then conveyor(3) gunner(10) harvester(20) builder(30) sentinel(30) launcher(20)
        self.n.append("%s %s %d/%d/%d/%d" % (
            label, ct.get_scale_percent(),
            ct.get_conveyor_cost(), ct.get_gunner_cost(),
            ct.get_harvester_cost(), ct.get_builder_bot_cost()))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned:
                if ct.get_current_round() == 0:
                    self.n.append("core0 %s %d/%d/%d/%d" % (
                        ct.get_scale_percent(), ct.get_conveyor_cost(),
                        ct.get_gunner_cost(), ct.get_harvester_cost(),
                        ct.get_builder_bot_cost()))
                p = Position(3, 9)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        if self.ph == 0:
            if pos != HOME:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                return
            self.ph = 1
            self.snap(ct, "bb1")          # after one builder bot exists
            return

        if self.ph == 1:
            self.ph = 2
            ct.build_conveyor(Position(5, 9), Direction.NORTH)
            self.snap(ct, "conv")
            return
        if self.ph == 2:
            self.ph = 3
            ct.build_harvester(Position(6, 8))
            self.snap(ct, "harv")
            return
        if self.ph == 3:
            self.ph = 4
            ct.build_gunner(Position(7, 9), Direction.EAST)
            self.snap(ct, "gun")
            return
        if self.ph == 4:
            self.ph = 5
            ct.build_barrier(Position(6, 10))
            self.snap(ct, "barr")
            return
        ct.resign(" | ".join(self.n[:9]))
