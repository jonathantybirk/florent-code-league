"""ECON Q1: the actual cheapest economic attack -- a 3 Ti BARRIER on the ORE TILE itself.

Denying the final conveyor costs 20 Ti of builder shots (`a2snip`) or 4 Ti of gunner ammo,
and the victim can rebuild the link for 3 Ti. Denying the ORE is permanent: a harvester may
only be built on an ORE_TITANIUM tile, so if a barrier already stands there the tile is gone
for the rest of the match and there is nothing to rebuild.

Arena `maps/lab/para.map26` has exactly ONE ore tile, (8,5), and `a2econ` reaches it on
round 9. Our builder spawns at (3,7) and needs six moves to reach (8,6), so it can seal the
tile on round 8 -- one round ahead.

Reports whether a barrier is legal on ore at all, and `b_titanium_collected` says whether the
opponent's whole economy died with it.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

ORE = Position(8, 5)
STAND = Position(8, 6)
LANE = ((4, 7), (5, 7), (6, 7), (7, 7), (8, 7), (8, 6))


class Player:
    def __init__(self):
        self.spawned = False
        self.i = 0
        self.built = None
        self.can = None
        self.note = ""

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:6] + ":" + str(exc)[:18]

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
        if (me.x, me.y) != (STAND.x, STAND.y):
            while self.i < len(LANE) and (me.x, me.y) == LANE[self.i]:
                self.i += 1
            gx, gy = LANE[min(self.i, len(LANE) - 1)]
            d = Direction.EAST if gx > me.x else (
                Direction.WEST if gx < me.x else (
                    Direction.SOUTH if gy > me.y else Direction.NORTH))
            if ct.can_move(d):
                ct.move(d)
            return

        if self.built is None:
            if self.can is None:
                self.can = "env=%s bar=%s conv=%s harv=%s" % (
                    ct.get_tile_env(ORE), ct.can_build_barrier(ORE),
                    ct.can_build_conveyor(ORE, Direction.WEST),
                    ct.can_build_harvester(ORE))
            if ct.can_build_barrier(ORE):
                ct.build_barrier(ORE)
                self.built = r
            else:
                self.built = -1
            return

        if r == 995:
            ct.resign(("OREBLK r%s %s | tile=%s ti=%d %s" % (
                self.built, self.can, ct.get_tile_building_id(ORE),
                ct.get_global_resources(), self.note))[:495])
