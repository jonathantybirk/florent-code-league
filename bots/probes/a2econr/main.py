"""ECON victim that REPAIRS: `a2econ` plus a builder that rebuilds the final conveyor.

`a2econ` is a dummy -- once its belt is shot out it never rebuilds, so denial probes score
against it forever. This variant is the realistic opponent: its builder parks on (12,4),
orthogonally adjacent to the last link (12,5), and rebuilds that conveyor for 3 Ti on any
round it finds the tile empty. It never fights back.

Arena `maps/lab/para.map26`. Core B anchor (13,5) -> footprint (13,5)(14,5)(13,6)(14,6).
Belt: harvester (8,5) -> (9,5)(10,5)(11,5)(12,5) all EAST -> Core tile (13,5).

Run `a2snip` against this to price a denial war instead of a denial demo.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

PLAN = (
    ((12, 4), (12, 5)),
    ((11, 4), (11, 5)),
    ((10, 4), (10, 5)),
    ((9, 4), (9, 5)),
)
HARV_STAND = (8, 4)
HARV = Position(8, 5)
GUARD = (12, 4)
LAST = Position(12, 5)


class Player:
    def __init__(self):
        self.spawned = False
        self.i = 0
        self.built = False
        self.repairs = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _walk(self, ct, me, goal):
        gx, gy = goal
        if me.x != gx:
            d = Direction.EAST if gx > me.x else Direction.WEST
        else:
            d = Direction.SOUTH if gy > me.y else Direction.NORTH
        if ct.can_move(d):
            ct.move(d)

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(12, 4)):
                ct.spawn_builder(Position(12, 4))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        me = ct.get_position()
        if self.i < len(PLAN):
            stand, build = PLAN[self.i]
            if (me.x, me.y) != stand:
                self._walk(ct, me, stand)
                return
            tgt = Position(build[0], build[1])
            if ct.can_build_conveyor(tgt, Direction.EAST):
                ct.build_conveyor(tgt, Direction.EAST)
                self.i += 1
            elif ct.get_tile_building_id(tgt) is not None:
                self.i += 1
            return

        if not self.built:
            if (me.x, me.y) != HARV_STAND:
                self._walk(ct, me, HARV_STAND)
                return
            if ct.can_build_harvester(HARV):
                ct.build_harvester(HARV)
                self.built = True
            elif ct.get_tile_building_id(HARV) is not None:
                self.built = True
            return

        # park next to the last link and keep it alive
        if (me.x, me.y) != GUARD:
            self._walk(ct, me, GUARD)
            return
        if ct.get_tile_building_id(LAST) is None:
            if ct.can_build_conveyor(LAST, Direction.EAST):
                ct.build_conveyor(LAST, Direction.EAST)
                self.repairs += 1
