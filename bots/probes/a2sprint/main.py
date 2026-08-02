"""AREA-2 headline: a PARASITE BELT against a real rival on the real map `sprint`.

This bot owns no harvester and never builds one, so every titanium it collects was taken out
of the opponent's harvester by round-robin theft.

`sprint` is 10x10, Core A anchor (1,1) [footprint (1,1)(2,1)(1,2)(2,2)], Core B anchor (7,7),
ore at (6,1) (8,3) (4,4) (5,5) (1,6) (3,8).  The `a2spy` sweep found jonbot, vanguard and
undertow all harvest (5,5), first seen rounds 8-17, with 1-3 free orthogonal neighbours.

Belt:  (5,4)N -> (5,3)W -> (4,3)W -> (3,3)W -> (2,3)N -> Core footprint tile (2,2).
Five 3-Ti conveyors.  The head (5,4) is orthogonally adjacent to BOTH contested ore tiles
(5,5) and (4,4); the trunk tile (4,3) is also orthogonally adjacent to (4,4).
Built tail-first so the belt is never a dead end (a dead-end parasite jams after one stack).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

N = Direction.NORTH
W = Direction.WEST
S = Direction.SOUTH
E = Direction.EAST

# (stand_x, stand_y, build_x, build_y, facing)
PLAN = (
    (3, 3, 2, 3, N),
    (4, 3, 3, 3, W),
    (5, 3, 4, 3, W),
    (6, 3, 5, 3, W),
    (6, 4, 5, 4, N),
)
SPAWN = (3, 2)


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
            if not self.spawned:
                p = Position(SPAWN[0], SPAWN[1])
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return

        me = ct.get_position()
        if self.i >= len(PLAN):
            self.done = True
            return
        sx, sy, bx, by, face = PLAN[self.i]

        tgt = Position(bx, by)
        if (me.x, me.y) == (sx, sy):
            if ct.can_build_conveyor(tgt, face):
                ct.build_conveyor(tgt, face)
                self.i += 1
                return
            if ct.get_tile_building_id(tgt) is not None:
                self.i += 1
            return

        # walk: y first, then x (keeps the bot off the belt tiles it still has to build)
        if me.y != sy:
            d = S if sy > me.y else N
            if ct.can_move(d):
                ct.move(d)
                return
        if me.x != sx:
            d = E if sx > me.x else W
            if ct.can_move(d):
                ct.move(d)
                return
        for d in (N, E, S, W):
            if ct.can_move(d):
                ct.move(d)
                return
