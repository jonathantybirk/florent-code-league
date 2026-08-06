"""SABOTAGE VERIFY -- the victim that shoots the squatter with the builder it ALREADY has.

sb_vic answers an occupied terminal tile with nothing; sb_vics answers it by buying a whole
sentinel (30 Ti + 10 Ti/shot).  Neither tests the zero-new-entity counter: the victim's chain
builder is parked adjacent to (17,4) and idle for 700+ rounds, and a builder's fire() does
2 dmg / 2 Ti against buildings.  A 30 HP barrier is therefore 15 rounds and 30 Ti of an
otherwise-wasted unit's time.

Identical to sb_vic except for the one extra branch: if (17,4) holds an ENEMY building, shoot it.

This also tests the finding's turn-order claim directly.  Team A acts before team B, so if the
attacker's occupier really does get first refusal on the empty tile every round, this victim
should break the barrier and still never manage to replant the conveyor.
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

        if ct.get_position() != PARK:
            return
        bid = ct.get_tile_building_id(TERM)
        if bid is None:
            if ct.can_build_conveyor(TERM, Direction.EAST):
                ct.build_conveyor(TERM, Direction.EAST)
            return
        if ct.get_team(bid) != ct.get_team() and ct.can_fire(TERM):
            ct.fire(TERM)
        return
