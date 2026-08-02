"""AREA-2 opponent: build two cheap buildings next to our approach lane, then sit forever.

Arena `close` (14x11): Core B anchor (8,5), footprint (8,5)(9,5)(8,6)(9,6).
Builder spawns on ring tile (7,5); it builds a CONVEYOR at (6,5) facing EAST and a
BARRIER at (7,4).  Never moves, never attacks -- it is a target dummy.
"""

from fcode import Controller, Direction, EntityType, GameError, Position


class Player:
    def __init__(self):
        self.spawned = False
        self.step = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(7, 5)):
                ct.spawn_builder(Position(7, 5))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return
        if self.step == 0:
            if ct.can_build_conveyor(Position(6, 5), Direction.EAST):
                ct.build_conveyor(Position(6, 5), Direction.EAST)
                self.step = 1
            return
        if self.step == 1:
            if ct.can_build_barrier(Position(7, 4)):
                ct.build_barrier(Position(7, 4))
                self.step = 2
            return
        return
