"""AREA-2, open item G43: the PARASITE CONVEYOR.

A Harvester round-robins its 10-Ti stacks to *all* adjacent buildings.  Nothing in the rules
says those buildings have to belong to the harvester's owner.  If we plant one 3-Ti conveyor
orthogonally adjacent to an enemy Harvester and drain it into OUR Core, we should take a share
of their income -- and score it as our own `titanium_collected`.

Arena `para`: enemy harvester at (8,5) (built by `a2econ`), Core A anchor (1,5).
We lay a west-flowing chain along y=6:  (8,6) (7,6) (6,6) (5,6) (4,6) (3,6) -> Core tile (2,6).
The head (8,6) is orthogonally adjacent to the enemy harvester at (8,5).
The builder walks the y=7 lane and builds each chain tile from directly below it.

MEASURED 2026-08-02, fcode 2.3.3, `maps/lab/para.map26` vs `a2econ` (full 1000 rounds):
    a_titanium_collected = 1230    b_titanium_collected = 1240
Team A owns NO harvester. CONFIRMED: the harvester round-robin is TEAM-BLIND -- it hands
one stack in turn to every orthogonally adjacent LIVE building regardless of owner, and
`titanium_collected` is credited to whoever owns the Core the stack finally lands on.
One head out of two live neighbours = one half. Cost 48 Ti (builder 30 + 6 conveyors).
Totals are conserved: 1230 + 1240 = 2470 = the harvester's undisturbed lifetime output.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

# built west-to-east so the chain is connected to our Core from the very first tile
PLAN = ((3, 7), (4, 7), (5, 7), (6, 7), (7, 7), (8, 7))


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
