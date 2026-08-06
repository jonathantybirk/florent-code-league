"""SABOTAGE Q5 -- BARRIER-ON-ORE denial, on 2.3.6.  `maps/lab/sab.map26`.

The victim's only ore is (15,4).  A 3 Ti barrier standing on it means no harvester can ever be
built there, so the denial is the whole chain rather than the single stack in transit that
belt-sniping destroys.

Team A's war builder parks on (15,5) -- SOUTH of the ore, deliberately off the victim's own
approach lane along row y=3, so that any denial measured here is the BARRIER's and not an
accident of body-blocking the victim's builder.  Each round it classifies (15,4):

    empty        -> build a barrier (3 Ti, 30 HP)
    ours+damaged -> heal it (+4 HP for 1 Ti)
    theirs       -> nothing; destroy() is allied-only, and the builder's own 2 dmg attack
                    would need 10 rounds and 20 Ti to remove a harvester

It counts placements, heals, and rounds held, and resigns at round 800.

Run it twice: vs `sb_vic` (whose builder reaches the ore on round ~3, so team A loses the race by
about fourteen moves) and vs `sb_vicd` (identical but idle until round 40, which hands team A the
tile).  The first run prices the RACE, the second prices the DENIAL.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

ECON_SPAWN = Position(4, 3)
WAR_SPAWN = Position(4, 6)
HARV = Position(6, 4)
MID = Position(5, 4)
TERM = Position(4, 4)

PARK = Position(15, 5)
TARGET = Position(15, 4)
REPORT = 800

ECON = (
    ("mv", Direction.EAST, None),
    ("mv", Direction.EAST, None),
    ("harv", HARV, None),
    ("mv", Direction.WEST, None),
    ("conv", MID, Direction.WEST),
    ("mv", Direction.WEST, None),
    ("conv", TERM, Direction.WEST),
)


class Player:
    def __init__(self):
        self.spawned = 0
        self.role = None
        self.step = 0
        self.note = ""
        self.placed = 0
        self.heals = 0
        self.ours = 0
        self.theirs = 0
        self.empty = 0
        self.arrived = 0
        self.firsthold = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:8] + ":" + str(exc)[:40]

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
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if self.spawned == 0:
                if ct.can_spawn(ECON_SPAWN):
                    ct.spawn_builder(ECON_SPAWN)
                    self.spawned = 1
                return
            if self.spawned == 1 and ct.can_spawn(WAR_SPAWN):
                ct.spawn_builder(WAR_SPAWN)
                self.spawned = 2
            return

        if et != EntityType.BUILDER_BOT:
            return

        p = ct.get_position()
        if self.role is None:
            self.role = "econ" if p == ECON_SPAWN else "war"

        if self.role == "econ":
            if self.step < len(ECON):
                kind, a, b = ECON[self.step]
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

        if p != PARK:
            self.walk(ct, p, PARK)
            return
        if not self.arrived:
            self.arrived = r

        bid = ct.get_tile_building_id(TARGET)
        if bid is None:
            self.empty += 1
            if ct.can_build_barrier(TARGET):
                ct.build_barrier(TARGET)
                self.placed += 1
                if not self.firsthold:
                    self.firsthold = r
        elif ct.get_team(bid) == ct.get_team():
            self.ours += 1
            if ct.get_hp(bid) < ct.get_max_hp(bid) and ct.can_heal(TARGET):
                ct.heal(TARGET)
                self.heals += 1
        else:
            self.theirs += 1

        if r >= REPORT:
            ct.resign(
                "SBORE r=%d arrived=%d firsthold=%d placed=%d heals=%d ours=%d theirs=%d "
                "empty=%d a_ti=%d scale=%d n=%s"
                % (r, self.arrived, self.firsthold, self.placed, self.heals, self.ours,
                   self.theirs, self.empty, ct.get_global_resources(),
                   int(ct.get_scale_percent()), self.note))
        return
