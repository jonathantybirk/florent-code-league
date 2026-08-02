"""ECON Q2/Q7: the RECYCLING LOOP -- a parasite that never has to reach home.

A dead-end parasite jams after one stack per conveyor (`a2deny`, `a2deny4`), so the
harvester's round-robin skips it and the denial is worth only 10 Ti per conveyor.
A CYCLE has no end. If a conveyor can hand its stack to a neighbour that hands it back,
the loop circulates forever, always has room, and swallows the enemy harvester's share
indefinitely -- 12 Ti for a permanent tax on a 20 Ti harvester, with no belt home.

Arena `maps/lab/para.map26`, opponent `a2econ` (harvester (8,5), belt east into Core B).

Four conveyors, one closed cycle, head (8,6) touching the harvester from the south:
    (8,6) EAST  -> (9,6)
    (9,6) SOUTH -> (9,7)
    (9,7) WEST  -> (8,7)
    (8,7) NORTH -> (8,6)

Read `b_titanium_collected` against the 2470 baseline (`noop` vs `a2econ`). If the loop
deadlocks once four stacks are inside it, the shortfall is ~40 Ti and a cycle is just a
dead end with extra steps; if it circulates, the shortfall is ~1230 Ti -- half the
harvester's lifetime output, for 12 Ti and no route home.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

# (stand_x, stand_y, build_x, build_y, facing).  G61 lets the builder stand on its own
# conveyors, which is how it reaches (9,7) to build (9,6).
STEPS = (
    (7, 6, 8, 6, Direction.EAST),    # head, fed by the enemy harvester at (8,5)
    (7, 7, 8, 7, Direction.NORTH),   # closes the ring back into the head
    (9, 8, 9, 7, Direction.WEST),    # feeds (8,7)
    (9, 7, 9, 6, Direction.SOUTH),   # feeds (9,7); built from on top of (9,7)
)
LOOP = (Position(8, 6), Position(9, 6), Position(9, 7), Position(8, 7))


class Player:
    def __init__(self):
        self.spawned = False
        self.i = 0
        self.done_round = None
        self.note = ""

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:6] + ":" + str(exc)[:18]

    def _walk(self, ct, me, gx, gy):
        order = []
        if me.x != gx:
            order.append(Direction.EAST if gx > me.x else Direction.WEST)
        if me.y != gy:
            order.append(Direction.SOUTH if gy > me.y else Direction.NORTH)
        for d in order:
            if ct.can_move(d):
                ct.move(d)
                return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 7)):
                ct.spawn_builder(Position(3, 7))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        me = ct.get_position()
        if self.i < len(STEPS):
            sx, sy, bx, by, face = STEPS[self.i]
            if (me.x, me.y) != (sx, sy):
                self._walk(ct, me, sx, sy)
                return
            tgt = Position(bx, by)
            if ct.can_build_conveyor(tgt, face):
                ct.build_conveyor(tgt, face)
                self.i += 1
                if self.i == len(STEPS):
                    self.done_round = r
            elif ct.get_tile_building_id(tgt) is not None:
                self.i += 1
            return

        if r == 995:
            ids = []
            for p in LOOP:
                b = ct.get_tile_building_id(p)
                ids.append("-" if b is None else str(ct.get_stored_resource_id(b)))
            ct.resign(("LOOP built=%s ring(8,6)(9,6)(9,7)(8,7)=%s %s" % (
                self.done_round, ",".join(ids), self.note))[:495])
