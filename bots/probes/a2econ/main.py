"""AREA-2 victim: a scripted, honest little economy for Team B on arena `para`/`cut`.

Core B anchor (13,5), footprint (13,5)(14,5)(13,6)(14,6).
Builder spawns on ring tile (12,4) and lays, east-to-west:
    conveyor (12,5)E  (11,5)E  (10,5)E  (9,5)E   then  harvester (8,5)
so a full stack lands on the Core footprint tile (13,5).  Then it sits still forever.
It never fights, never rebuilds -- so any change in `b_titanium_collected` is caused
entirely by the opponent.

MEASURED 2026-08-02, fcode 2.3.3, `maps/lab/para.map26`: undisturbed it collects 2470 as
Team B (vs `noop`). It is the standing victim for every economy-denial probe:
    vs noop      2470     baseline
    vs a2deny    2460     one dead-end conveyor, -10
    vs a2deny4   2420     four-conveyor dead end, -40 (plus 10 for the early resign)
    vs a2loop    2420     closed four-conveyor cycle -- identical to a dead end
    vs a2para    1240     one live parasite head, half
    vs a2para2    830     two heads, one third left
    vs a2para3    620     three heads, one quarter left
    vs a2snip      20     final conveyor shot dead on round 21 for 20 Ti of builder fire
    vs a2oreblk     0     3-Ti barrier placed on the ore tile on round 7
"""

from fcode import Controller, Direction, EntityType, GameError, Position

# (stand tile, build tile) pairs, in order
PLAN = (
    ((12, 4), (12, 5)),
    ((11, 4), (11, 5)),
    ((10, 4), (10, 5)),
    ((9, 4), (9, 5)),
)
HARV_STAND = (8, 4)
HARV = (8, 5)


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
            if not self.spawned and ct.can_spawn(Position(12, 4)):
                ct.spawn_builder(Position(12, 4))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
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

        if (me.x, me.y) != HARV_STAND:
            self._walk(ct, me, HARV_STAND)
            return
        tgt = Position(HARV[0], HARV[1])
        if ct.can_build_harvester(tgt):
            ct.build_harvester(tgt)
            self.done = True
        elif ct.get_tile_building_id(tgt) is not None:
            self.done = True

    def _walk(self, ct, me, goal):
        gx, gy = goal
        if me.x != gx:
            d = Direction.EAST if gx > me.x else Direction.WEST
        else:
            d = Direction.SOUTH if gy > me.y else Direction.NORTH
        if ct.can_move(d):
            ct.move(d)
