"""SABOTAGE -- the VICTIM THAT FIGHTS BACK.  Team B on `maps/lab/sab.map26`.

sb_vic only replants the cut link, so once team A parks a barrier on the terminal tile (17,4) the
chain stays dead forever: destroy() is allied-only and sb_vic owns no weapon.  That measures the
ceiling of cut-then-occupy, not its steady state.  This victim closes the loop.

Same chain, same park tile:
    harvester(15,4) -> conveyor(16,4)E -> conveyor(17,4)E -> Core foot (18,4), builder on (17,3)

plus one reactive weapon.  The FIRST time (17,4) is found holding an ENEMY building, the builder
walks two tiles north to (17,1), plants a SENTINEL on (17,0) facing SOUTH, and walks back to
(17,3).  A sentinel and not a gunner because the builder's own park tile (17,3) sits between
(17,0) and the target: gunner fire would stop on it, sentinel fire is not blocked.  Reach is 4
tiles, d^2=16 <= 32.

Thereafter the loop is:
    enemy building on (17,4) -> sentinel shoots it (30 HP barrier = 2 shots = 20 Ti)
    tile empty              -> builder replants the conveyor for 3 Ti

which is exactly the price a competent opponent pays to break an occupation, and therefore the
number the abandon condition has to be built from.  Never resigns; the attacker reports.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

SPAWN = Position(17, 3)
HARV = Position(15, 4)
MID = Position(16, 4)
TERM = Position(17, 4)
PARK = Position(17, 3)
SENPOS = Position(17, 0)
SENSTAND = Position(17, 1)

AMMO_LOW = 20
AMMO_TOP = 60

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
        self.phase = 0          # 0 = park, 1 = go build sentinel, 2 = come back
        self.sentinel_up = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def walk(self, ct, pos, tgt):
        best = None
        for d in CARD:
            if not ct.can_move(d):
                continue
            sc = pos.add(d).distance_squared(tgt)
            if best is None or sc < best[0]:
                best = (sc, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])

    def _run(self, ct):
        et = ct.get_entity_type()

        if et == EntityType.CORE:
            if not self.spawned:
                if ct.can_spawn(SPAWN):
                    ct.spawn_builder(SPAWN)
                    self.spawned = True
                return
            if ct.get_global_ammo() < AMMO_LOW:
                want = AMMO_TOP - ct.get_global_ammo()
                while want > 0 and not ct.can_convert_ammo(want):
                    want -= 5
                if want > 0:
                    ct.convert_ammo(want)
            return

        if et == EntityType.SENTINEL:
            bid = ct.get_tile_building_id(TERM)
            if bid is not None and ct.get_team(bid) != ct.get_team():
                if ct.can_fire(TERM):
                    ct.fire(TERM)
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

        p = ct.get_position()
        bid = ct.get_tile_building_id(TERM)
        enemy_here = bid is not None and ct.get_team(bid) != ct.get_team()

        # one-off detour to plant the counter-battery
        if self.phase == 0 and enemy_here and not self.sentinel_up:
            self.phase = 1
        if self.phase == 1:
            if p == SENSTAND:
                if ct.can_build_sentinel(SENPOS, Direction.SOUTH):
                    ct.build_sentinel(SENPOS, Direction.SOUTH)
                    self.sentinel_up = True
                    self.phase = 2
            else:
                self.walk(ct, p, SENSTAND)
            return
        if self.phase == 2:
            if p != PARK:
                self.walk(ct, p, PARK)
                return
            self.phase = 0

        if p != PARK:
            self.walk(ct, p, PARK)
            return
        if bid is None and ct.can_build_conveyor(TERM, Direction.EAST):
            ct.build_conveyor(TERM, Direction.EAST)
        return
