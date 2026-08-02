"""ECON Q3, direction A->B: can OUR belt deliver into the ENEMY Core, and do THEY score it?

`a2catch` proved the B->A direction: Team B's conveyor output onto a Team A conveyor and
Team A banked 2480 of Team B's titanium. This probe proves the mirror image, which is the
one that matters defensively: a belt is credited to whoever owns the tile the stack lands
on, so pointing our own belt at anything of theirs is a gift, not an attack.

Arena `maps/lab/belt.map26` (20x12): Core A anchor (1,5), Core B anchor (17,5), ore (5,5).

    harvester (5,5)
    conveyor  (6,5)..(16,5) all EAST  -> (16,5) outputs onto Core B footprint tile (17,5)

Team A never touches its own Core. If `b_titanium_collected` climbs while
`a_titanium_collected` stays 0, cross-team delivery is confirmed in both directions and
"resource injection" is real -- as a way to LOSE resources.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HARV = Position(5, 5)
FIRST = 6
LAST = 16


class Player:
    def __init__(self):
        self.spawned = False
        self.i = -1
        self.done = None
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
            if not self.spawned and ct.can_spawn(Position(3, 4)):
                ct.spawn_builder(Position(3, 4))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        me = ct.get_position()
        if self.i < 0:
            if me.x < 5:
                if ct.can_move(Direction.EAST):
                    ct.move(Direction.EAST)
                return
            if ct.can_build_harvester(HARV):
                ct.build_harvester(HARV)
                self.i = FIRST
            elif ct.get_tile_building_id(HARV) is not None:
                self.i = FIRST
            return

        if self.i <= LAST:
            if me.x != self.i:
                if ct.can_move(Direction.EAST):
                    ct.move(Direction.EAST)
                return
            tgt = Position(self.i, 5)
            if ct.can_build_conveyor(tgt, Direction.EAST):
                ct.build_conveyor(tgt, Direction.EAST)
                self.i += 1
                if self.i > LAST:
                    self.done = r
            elif ct.get_tile_building_id(tgt) is not None:
                self.i += 1
            return

        if r == 995:
            ct.resign(("GIFT built=%s ti=%d %s" % (
                self.done, ct.get_global_resources(), self.note))[:495])
