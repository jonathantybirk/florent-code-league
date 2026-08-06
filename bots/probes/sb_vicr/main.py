"""SABOTAGE VERIFY -- the victim that ROUTES AROUND the occupied tile.  Team B, maps/lab/sab.map26.

sb_vic is hard-scripted to rebuild the terminal conveyor at exactly one tile, (17,4), and to do
nothing else ever.  That is what makes a single 3 Ti barrier on (17,4) deny 91% of its harvest --
the victim has no other behaviour available to it.  This probe tests whether that denial is a
property of the game or a property of that script.

Same opening, same chain:
    harvester(15,4) -> conveyor(16,4)E -> conveyor(17,4)E -> Core foot (18,4), builder parks (17,3)

New behaviour: if (17,4) holds an ENEMY building for PATIENCE consecutive rounds, the (otherwise
idle) builder lays a bypass one row north, which no part of the attacker's rig can reach --
the occupier at (17,5) is adjacent only to (17,4), and the sentinel at (17,9) firing NORTH has
reach 5, i.e. (17,8)..(17,4):

    destroy (16,4); rebuild it pointing NORTH; then (16,3)E -> (17,3)E -> (18,3)S -> Core (18,4)

Four conveyors, laid once.  The builder then parks on (18,2) and is done.

Reports nothing; the attacker resigns.  b_titanium_collected is this team's side of the ledger.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

SPAWN = Position(17, 3)
HARV = Position(15, 4)
MID = Position(16, 4)
TERM = Position(17, 4)
PARK = Position(17, 3)
PATIENCE = 3

SCRIPT = (
    ("mv", Direction.WEST, None),
    ("mv", Direction.WEST, None),
    ("harv", HARV, None),
    ("mv", Direction.EAST, None),
    ("conv", MID, Direction.EAST),
    ("mv", Direction.EAST, None),
    ("conv", TERM, Direction.EAST),
)

# the bypass, as (kind, arg, arg) executed strictly in order from PARK=(17,3)
BYPASS = (
    ("mv", Direction.WEST, None),               # -> (16,3)
    ("kill", Position(16, 4), None),            # destroy own conveyor (16,4)
    ("conv", Position(16, 4), Direction.NORTH),  # rebuild it feeding north
    ("mv", Direction.WEST, None),               # -> (15,3)
    ("conv", Position(16, 3), Direction.EAST),
    ("mv", Direction.NORTH, None),              # -> (15,2)
    ("mv", Direction.EAST, None),               # -> (16,2)
    ("mv", Direction.EAST, None),               # -> (17,2)
    ("conv", Position(17, 3), Direction.EAST),
    ("mv", Direction.EAST, None),               # -> (18,2)
    ("conv", Position(18, 3), Direction.SOUTH),
)


class Player:
    def __init__(self):
        self.spawned = False
        self.step = 0
        self.blocked = 0
        self.bstep = 0
        self.rerouting = False

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

        # ---- opening chain
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

        # ---- bypass, once triggered, runs to completion
        if self.rerouting:
            if self.bstep >= len(BYPASS):
                return
            kind, a, b = BYPASS[self.bstep]
            if kind == "mv":
                if ct.can_move(a):
                    ct.move(a)
                    self.bstep += 1
            elif kind == "kill":
                if ct.get_tile_building_id(a) is None:
                    self.bstep += 1
                elif ct.can_destroy(a):
                    ct.destroy(a)
                    self.bstep += 1
            elif kind == "conv":
                if ct.can_build_conveyor(a, b):
                    ct.build_conveyor(a, b)
                    self.bstep += 1
            return

        # ---- normal: replant the cut link; count how long an enemy has squatted the tile
        bid = ct.get_tile_building_id(TERM)
        if bid is not None and ct.get_team(bid) != ct.get_team():
            self.blocked += 1
            if self.blocked >= PATIENCE and ct.get_position() == PARK:
                self.rerouting = True
            return
        self.blocked = 0
        if ct.get_position() != PARK:
            return
        if bid is None and ct.can_build_conveyor(TERM, Direction.EAST):
            ct.build_conveyor(TERM, Direction.EAST)
        return
