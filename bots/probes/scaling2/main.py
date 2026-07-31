"""Completes G07: the scale increments for splitter, sentinel and launcher.

`scaling` measured builder +20, gunner +10, harvester +5, conveyor +1, barrier +1 and confirmed
cost = floor(scale x base) with ONE global scale. The 2.3.3 docs additionally claim
splitter +1, sentinel +20, launcher +10. Measure those three.

Arena `openfield` (no ore). The builder walks north up column x=6 building eastward as it goes.
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
            self.n.append("TOP:" + type(exc).__name__ + str(exc)[:26])

    def snap(self, ct, label):
        self.n.append("%s %s %d/%d/%d" % (
            label, ct.get_scale_percent(), ct.get_conveyor_cost(),
            ct.get_gunner_cost(), ct.get_builder_bot_cost()))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
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
            self.snap(ct, "base")
            return
        if self.ph == 1:
            self.ph = 2
            ct.build_splitter(Position(7, 9), Direction.EAST)
            self.snap(ct, "split")
            return
        if self.ph == 2:
            self.ph = 3
            if ct.can_move(Direction.NORTH):
                ct.move(Direction.NORTH)
            return
        if self.ph == 3:
            self.ph = 4
            ct.build_sentinel(Position(7, 8), Direction.EAST)
            self.snap(ct, "sent")
            return
        if self.ph == 4:
            self.ph = 5
            if ct.can_move(Direction.NORTH):
                ct.move(Direction.NORTH)
            return
        if self.ph == 5:
            self.ph = 6
            ct.build_launcher(Position(7, 7))
            self.snap(ct, "launch")
            return
        ct.resign(" | ".join(self.n[:8]))
