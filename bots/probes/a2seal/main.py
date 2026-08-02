"""ECON Q5: a harvester as a WALL -- 20 Ti that seals a corridor, and seals it both ways.

Harvesters block movement (G42). Arena `maps/lab/eseal.map26` (16x11) is built so that the
claim can be tested at all: a solid wall column at x=8 with exactly one gap, at (8,5), and
that gap tile is ORE. Nothing else connects the two halves.

The builder spawns at (3,5), walks east to (7,5) and builds the harvester on (8,5).
Then it reports, from the WEST side of its own wall:

    pass   is_tile_passable((8,5))
    canE   can_move(EAST) from (7,5)
    n8     how many of (8,4)(8,5)(8,6) are passable  -- the whole crossing
    coll   the harvester is 6 conveyors from our Core, so it is also worth 0 income

The self-harm half of the question is the same measurement: our own builder is now locked
on its own side of the map. Read alongside the static sweep, which found ZERO ore tiles on
the 21 shipped maps that are articulation points of the passable graph.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

SPAWN = Position(3, 5)
STAND = Position(7, 5)
GAP = Position(8, 5)
PROBE = (Position(8, 4), Position(8, 5), Position(8, 6))


class Player:
    def __init__(self):
        self.spawned = False
        self.built = None
        self.pre = ""
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
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        me = ct.get_position()
        if self.built is None:
            if me != STAND:
                if ct.can_move(Direction.EAST):
                    ct.move(Direction.EAST)
                return
            if not self.pre:
                self.pre = "pre pass=%s canE=%s" % (
                    ct.is_tile_passable(GAP), ct.can_move(Direction.EAST))
            if ct.can_build_harvester(GAP):
                ct.build_harvester(GAP)
                self.built = r
            return

        if r == 200:
            n = 0
            for p in PROBE:
                if ct.is_tile_passable(p):
                    n += 1
            ct.resign(("SEAL built=%s | %s | post pass=%s canE=%s open_of_3=%d ti=%d %s" % (
                self.built, self.pre, ct.is_tile_passable(GAP),
                ct.can_move(Direction.EAST), n, ct.get_global_resources(),
                self.note))[:495])
