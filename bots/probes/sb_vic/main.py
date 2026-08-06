"""SABOTAGE -- the VICTIM.  A defender that does nothing but run one chain and rebuild the cut.

Arena `maps/lab/sab.map26`, team B (Core foot (18,4)(19,4)(18,5)(19,5)).

One builder spawns on (17,3), walks west, and lays the whole chain:

    harvester(15,4) -> conveyor(16,4) EAST -> conveyor(17,4) EAST -> Core foot (18,4)

then parks on (17,3) forever.  (17,3) is orthogonally adjacent to the TERMINAL conveyor (17,4)
and sits BEHIND it relative to an attacker firing north up column x=17, so the builder can
replant the cut link every single round without ever eclipsing the target.

This is deliberately the cheapest possible defence -- no turrets, no menders, no counter-attack,
just `if the terminal conveyor is gone, build another one for 3 Ti`.  It is the exact opponent
the 2.3.3 belt-sniping measurement used, so the 2.3.6 exchange ratio is comparable.

It never resigns; the attacking probe is the reporter and the result dict's b_* fields carry this
team's side of the ledger.
"""

from fcode import Controller, Direction, EntityType, Position

SPAWN = Position(17, 3)
HARV = Position(15, 4)
MID = Position(16, 4)
TERM = Position(17, 4)
PARK = Position(17, 3)

SCRIPT = (
    ("mv", Direction.WEST, None),
    ("mv", Direction.WEST, None),
    ("harv", HARV, None),
    ("mv", Direction.EAST, None),
    ("conv", MID, Direction.EAST),
    ("mv", Direction.EAST, None),
    ("conv", TERM, Direction.EAST),
)


class Player:
    def __init__(self):
        self.spawned = False
        self.step = 0
        self.rebuilds = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()

        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return

        if et != EntityType.BUILDER_BOT:
            return

        if self.step < len(SCRIPT):
            kind, a, b = SCRIPT[self.step]
            if kind == "mv":
                if ct.can_move(a):
                    ct.move(a)
                    self.step += 1
            elif kind == "harv":
                if ct.can_build_harvester(a):
                    ct.build_harvester(a)
                    self.step += 1
            elif kind == "conv":
                if ct.can_build_conveyor(a, b):
                    ct.build_conveyor(a, b)
                    self.step += 1
            return

        # parked on (17,3): replant the terminal conveyor the moment it goes missing
        if ct.get_position() != PARK:
            return
        if ct.get_tile_building_id(TERM) is None:
            if ct.can_build_conveyor(TERM, Direction.EAST):
                ct.build_conveyor(TERM, Direction.EAST)
                self.rebuilds += 1
        return
