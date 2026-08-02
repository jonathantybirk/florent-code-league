"""AREA-2 / G43: TWO parasite heads on the same enemy harvester.

If the harvester's round-robin really is "one stack to each adjacent building in turn", then
owning 2 of its 3 live neighbours should take 2/3 of its output instead of 1/2.

Enemy harvester (8,5); enemy chain head (9,5); enemy builder parked at (8,4).
We take (8,6) and (7,5), both draining into a single westward trunk on y=6 into Core A (2,6).

Build order (stand -> build):
    (3,7)->(3,6)W  (4,7)->(4,6)W  (5,7)->(5,6)W  (6,7)->(6,6)W  (7,7)->(7,6)W
    (8,7)->(8,6)W                         [head 1, adjacent to harvester from the south]
    (7,6)->(7,5)S                         [head 2, adjacent to harvester from the west]
A builder may stand on a conveyor (G61), which is how it reaches (7,6).

MEASURED 2026-08-02, fcode 2.3.3, `maps/lab/para.map26` vs `a2econ` (full 1000 rounds):
    a_titanium_collected = 1640    b_titanium_collected = 830
Two heads of three live neighbours = exactly two thirds. Cost 51 Ti (builder 30 + 7
conveyors). `a2para3` takes three of four and scores 1830 / 620 = three quarters. The share
is k/n where n is the number of live adjacent buildings and k is how many we own.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

S = Direction.SOUTH
W = Direction.WEST
# (stand_x, stand_y, build_x, build_y, facing)
PLAN = (
    (3, 7, 3, 6, W),
    (4, 7, 4, 6, W),
    (5, 7, 5, 6, W),
    (6, 7, 6, 6, W),
    (7, 7, 7, 6, W),
    (8, 7, 8, 6, W),
    (7, 6, 7, 5, S),
)


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
        sx, sy, bx, by, face = PLAN[self.i]
        if (me.x, me.y) != (sx, sy):
            if me.y != sy:
                d = Direction.SOUTH if sy > me.y else Direction.NORTH
            else:
                d = Direction.EAST if sx > me.x else Direction.WEST
            if ct.can_move(d):
                ct.move(d)
            return
        tgt = Position(bx, by)
        if ct.can_build_conveyor(tgt, face):
            ct.build_conveyor(tgt, face)
            self.i += 1
        elif ct.get_tile_building_id(tgt) is not None:
            self.i += 1
