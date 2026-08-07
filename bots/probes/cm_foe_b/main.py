"""CONVEYOR MAZE Q2 (side B): lay an enemy-owned belt chain in no-man's land, then leave.

Partner of `cm_foe_a`, which walks a Team-A builder onto this chain and measures whether
the belt carries it. Arena `maps/lab/belt.map26` (20x12), Core B anchor (17,5).

    (12,4) WEST -> (11,4) WEST -> (10,4) WEST -> spills onto bare ground at (9,4)

Pointing WEST means a displacement rule, if one existed, would shove the Team-A visitor
back toward its own side -- the exact effect the "conveyor maze" idea is claiming.
The builder then retreats to (14,4) so it is not standing in the visitor's way.
"""

from fcode import Controller, Direction, EntityType, Position

# (tile to stand on, tile to build, facing)
PLAN = (
    (Position(13, 4), Position(12, 4), Direction.WEST),
    (Position(12, 4), Position(11, 4), Direction.WEST),
    (Position(11, 4), Position(10, 4), Direction.WEST),
)
RETREAT = Position(14, 4)
SPAWNS = (Position(16, 4), Position(16, 7), Position(19, 4), Position(16, 5),
          Position(17, 4), Position(17, 7), Position(19, 7))


class Player:
    def __init__(self):
        self.tries = 0
        self.i = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            pass

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if ct.get_unit_count() < 2 and r % 3 == 1:
                q = SPAWNS[self.tries % len(SPAWNS)]
                self.tries += 1
                if ct.can_spawn(q):
                    ct.spawn_builder(q)
            return
        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()
        if self.i >= len(PLAN):
            if pos != RETREAT:
                self.walk(ct, pos, RETREAT)
            return
        stand, tile, face = PLAN[self.i]
        if pos != stand:
            self.walk(ct, pos, stand)
            return
        if not ct.is_tile_empty(tile):
            self.i += 1
            return
        if ct.can_build_conveyor(tile, face):
            ct.build_conveyor(tile, face)

    def walk(self, ct, pos, tgt):
        opts = []
        if pos.x != tgt.x:
            opts.append(Direction.EAST if tgt.x > pos.x else Direction.WEST)
        if pos.y != tgt.y:
            opts.append(Direction.SOUTH if tgt.y > pos.y else Direction.NORTH)
        for d in opts:
            if ct.can_move(d):
                ct.move(d)
                return
