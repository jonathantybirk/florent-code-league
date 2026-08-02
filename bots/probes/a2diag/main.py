"""AREA-2 / G43: is the Harvester's round-robin ORTHOGONAL-only, or does it feed DIAGONALS?

Same trunk as `a2para` but one tile short: the head is (7,6), which is DIAGONALLY adjacent to
the enemy harvester at (8,5) and orthogonally adjacent to nothing of theirs.

  a_titanium_collected > 0  -> diagonal feeding, so a harvester has up to 8 parasite slots.
  a_titanium_collected == 0 -> orthogonal only, 4 slots, of which the owner needs one.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

PLAN = ((3, 7), (4, 7), (5, 7), (6, 7), (7, 7))


class Player:
    def __init__(self):
        self.spawned = False
        self.i = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 7)):
                ct.spawn_builder(Position(3, 7))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return

        me = ct.get_position()
        if self.i >= len(PLAN):
            self.done = True
            return
        sx, sy = PLAN[self.i]
        if (me.x, me.y) != (sx, sy):
            if me.x != sx:
                d = Direction.EAST if sx > me.x else Direction.WEST
            else:
                d = Direction.SOUTH if sy > me.y else Direction.NORTH
            if ct.can_move(d):
                ct.move(d)
            return
        tgt = Position(sx, sy - 1)
        if ct.can_build_conveyor(tgt, Direction.WEST):
            ct.build_conveyor(tgt, Direction.WEST)
            self.i += 1
        elif ct.get_tile_building_id(tgt) is not None:
            self.i += 1
