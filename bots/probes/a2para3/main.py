"""ECON Q3: THREE parasite heads -- take 3 of the enemy harvester's 4 neighbours.

`a2para` (1 head of 2 live neighbours) split the enemy harvester 1230 / 1240.
`a2para2` (2 heads of 3) split it 1640 / 830 -- exactly two thirds.
If the round-robin really is "one stack to each LIVE adjacent building in turn", then
owning 3 of the 4 neighbours must take three quarters: about 1850 / 620.

Arena `maps/lab/para.map26`, opponent `a2econ`. Enemy harvester (8,5); its four orthogonal
neighbours are (7,5) (9,5) (8,4) (8,6), and the enemy's own belt occupies (9,5).

One westward trunk on y=6 into Core A tile (2,6), with three feeders:
    (8,6) W                          head 1, from the south
    (7,5) S -> (7,6)                 head 2, from the west
    (8,4) W -> (7,4) S -> (7,5)      head 3, from the north
Nine conveyors, 27 Ti. G61 lets the builder stand on its own conveyors, which is how it
reaches (7,6) and (7,4).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

S = Direction.SOUTH
W = Direction.WEST
# (stand_x, stand_y, build_x, build_y, facing) -- trunk first, west to east, so the belt is
# connected to our Core before any head starts drawing.
STEPS = (
    (3, 7, 3, 6, W),
    (4, 7, 4, 6, W),
    (5, 7, 5, 6, W),
    (6, 7, 6, 6, W),
    (7, 7, 7, 6, W),
    (8, 7, 8, 6, W),
    (7, 6, 7, 5, S),
    (6, 4, 7, 4, S),
    (7, 4, 8, 4, W),
)


class Player:
    def __init__(self):
        self.spawned = False
        self.i = 0
        self.done = None
        self.note = ""

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:6] + ":" + str(exc)[:18]

    def _walk(self, ct, me, gx, gy):
        order = []
        if me.y != gy:
            order.append(Direction.SOUTH if gy > me.y else Direction.NORTH)
        if me.x != gx:
            order.append(Direction.EAST if gx > me.x else Direction.WEST)
        for d in order:
            if ct.can_move(d):
                ct.move(d)
                return
        for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
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
                    self.done = r
            elif ct.get_tile_building_id(tgt) is not None:
                self.i += 1
            return

        if r == 995:
            ct.resign(("PARA3 built=%s step=%d ti=%d %s" % (
                self.done, self.i, ct.get_global_resources(), self.note))[:495])
