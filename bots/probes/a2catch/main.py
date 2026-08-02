"""AREA-2: catch an ENEMY conveyor's output on OUR conveyor, arena `inject`.

Core A anchor (11,8), footprint (11,8)(12,8)(11,9)(12,9).  Builder spawns on ring tile (10,7).
  r1  build conveyor (11,7) facing SOUTH  -> outputs onto our own Core footprint tile (11,8)
  r2  step north to (10,6)
  r3  build conveyor (11,6) facing SOUTH  -> outputs into (11,7)
Both are in place before the enemy harvester at (10,5) exists.  The enemy's only conveyor,
(11,5) facing SOUTH, then points straight at our (11,6).

MEASURED 2026-08-02, fcode 2.3.3, `maps/lab/inject.map26` vs `a2inj`:
    a_titanium_collected = 2480    b_titanium_collected = 0
CONFIRMED, and it is a theft mechanic, not a doc error. Team B's conveyor output onto a
Team A conveyor and Team A banked 100% of Team B's mine. A stack belongs to whoever owns
the tile it lands on. The mirror image is `a2gift`: our belt pointed at the enemy Core gave
THEM 2450 while we scored 0. Never point a belt at anything the opponent owns.
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
            if not self.spawned and ct.can_spawn(Position(10, 7)):
                ct.spawn_builder(Position(10, 7))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.step > 2:
            return

        me = ct.get_position()
        if self.step == 0:
            if ct.can_build_conveyor(Position(11, 7), Direction.SOUTH):
                ct.build_conveyor(Position(11, 7), Direction.SOUTH)
                self.step = 1
            return
        if self.step == 1:
            if (me.x, me.y) != (10, 6):
                if ct.can_move(Direction.NORTH):
                    ct.move(Direction.NORTH)
                return
            if ct.can_build_conveyor(Position(11, 6), Direction.SOUTH):
                ct.build_conveyor(Position(11, 6), Direction.SOUTH)
                self.step = 3
            return
