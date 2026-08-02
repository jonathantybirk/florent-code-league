"""AREA-2 victim for the conveyor-interception test, arena `inject`.

Core B anchor (15,4).  Builder spawns on ring tile (14,5), walks west to (11,5), builds the
harvester on the ore at (10,5), steps north to (11,4) and builds ONE conveyor at (11,5)
facing SOUTH -- straight into tiles that Team A already owns.  Then it stops.

MEASURED 2026-08-02, fcode 2.3.3, `maps/lab/inject.map26`:
    vs `a2catch`  b_titanium_collected = 0   (a_titanium_collected = 2480 -- stolen)
    vs `noop`     b_titanium_collected = 0   (the belt dead-ends, nothing scores)
This bot is the victim half of the cross-team conveyor test: it points its only conveyor
SOUTH out of its own territory. See `a2catch` for the verdict.
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
            if not self.spawned and ct.can_spawn(Position(14, 5)):
                ct.spawn_builder(Position(14, 5))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.step > 2:
            return

        me = ct.get_position()
        if self.step == 0:
            if me.x > 11:
                if ct.can_move(Direction.WEST):
                    ct.move(Direction.WEST)
                return
            if ct.can_build_harvester(Position(10, 5)):
                ct.build_harvester(Position(10, 5))
                self.step = 1
            return
        if self.step == 1:
            if (me.x, me.y) != (11, 4):
                if ct.can_move(Direction.NORTH):
                    ct.move(Direction.NORTH)
                return
            if ct.can_build_conveyor(Position(11, 5), Direction.SOUTH):
                ct.build_conveyor(Position(11, 5), Direction.SOUTH)
                self.step = 3
            return
