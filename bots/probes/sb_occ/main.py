"""SABOTAGE Q3 -- CUT-THEN-OCCUPY.  `maps/lab/sab.map26` vs sb_vic.

Belt-sniping loses because destroy() is ALLIED-ONLY: the victim replants the cut link for 3 Ti
and the attacker pays 12 Ti of ammo again.  The counter is to not leave the tile empty.  Kill the
victim's TERMINAL conveyor (17,4) and put OUR OWN building on the vacated tile.  They cannot
destroy() an enemy building, so clearing it costs them turret ammo -- and while it stands their
whole chain is cut, not merely interrupted.

Layout:
  SENTINEL (17,9) facing NORTH -- reach 5, d^2=25<=32, and unblocked, so it still hits (17,4)
  with our own builder standing on (17,5).  A gunner could not: (17,5) would eclipse the target.
  BUILDER parked on (17,5) -- the ONLY tile adjacent to (17,4) that team A can occupy, since
  (16,4) is the victim's conveyor, (17,3) is the victim's builder and (18,4) is their Core.

Each round the builder classifies (17,4) with get_team(building_id) and acts:
    empty        -> build a BARRIER (3 Ti, 30 HP)
    ours+damaged -> heal it (+4 HP for 1 Ti)   <- 1 Ti per 4 HP against their 4 Ti per 7 HP
    theirs       -> nothing (destroy() is allied-only)
The sentinel fires at (17,4) only while the building there belongs to the enemy.

The builder publishes its counters through store slots 0..5; the SENTINEL is the reporter and
resigns at round 800 with both halves of the ledger (G29, one-round store lag accepted).
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

ECON_SPAWN = Position(4, 3)
WAR_SPAWN = Position(4, 6)
HARV = Position(6, 4)
MID = Position(5, 4)
TERM = Position(4, 4)

SENPOS = Position(17, 9)
SENSTAND = Position(17, 8)
PARK = Position(17, 5)
TARGET = Position(17, 4)

AMMO_LOW = 30
AMMO_TOP = 60
REPORT = 800

S_PLACED, S_HEALS, S_OURS, S_THEIRS, S_EMPTY, S_FIRSTHOLD = 0, 1, 2, 3, 4, 5

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
        self.st = 0
        self.note = ""
        self.placed = 0
        self.heals = 0
        self.ours = 0
        self.theirs = 0
        self.empty = 0
        self.firsthold = 0
        # sentinel
        self.fires = 0
        self.kills = 0
        self.prev_bid = None

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
            if self.spawned == 1:
                if ct.can_spawn(WAR_SPAWN):
                    ct.spawn_builder(WAR_SPAWN)
                    self.spawned = 2
                return
            if ct.get_global_ammo() < AMMO_LOW:
                want = AMMO_TOP - ct.get_global_ammo()
                while want > 0 and not ct.can_convert_ammo(want):
                    want -= 5
                if want > 0:
                    ct.convert_ammo(want)
            return

        if et == EntityType.BUILDER_BOT:
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

            if self.st == 0:
                if p == SENSTAND:
                    self.st = 1
                else:
                    self.walk(ct, p, SENSTAND)
                    return
            if self.st == 1:
                if ct.can_build_sentinel(SENPOS, Direction.NORTH):
                    ct.build_sentinel(SENPOS, Direction.NORTH)
                    self.st = 2
                return
            if self.st == 2:
                if p != PARK:
                    self.walk(ct, p, PARK)
                    return
                self.st = 3
            if self.st == 3:
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
                ct.write_store(S_PLACED, self.placed)
                ct.write_store(S_HEALS, self.heals)
                ct.write_store(S_OURS, self.ours)
                ct.write_store(S_THEIRS, self.theirs)
                ct.write_store(S_EMPTY, self.empty)
                ct.write_store(S_FIRSTHOLD, self.firsthold)
            return

        if et == EntityType.SENTINEL:
            bid = ct.get_tile_building_id(TARGET)
            if self.prev_bid is not None and bid != self.prev_bid:
                self.kills += 1
            self.prev_bid = bid
            if bid is not None and ct.get_team(bid) != ct.get_team():
                if ct.can_fire(TARGET):
                    ct.fire(TARGET)
                    self.fires += 1
            if r >= REPORT:
                ct.resign(
                    "SBOCC r=%d senfires=%d ammoTi=%d tilechanges=%d | builder: placed=%d "
                    "heals=%d ours=%d theirs=%d empty=%d firsthold=%d | a_ti=%d ammo=%d "
                    "scale=%d n=%s"
                    % (r, self.fires, self.fires * 10, self.kills,
                       ct.read_store(S_PLACED), ct.read_store(S_HEALS),
                       ct.read_store(S_OURS), ct.read_store(S_THEIRS),
                       ct.read_store(S_EMPTY), ct.read_store(S_FIRSTHOLD),
                       ct.get_global_resources(), ct.get_global_ammo(),
                       int(ct.get_scale_percent()), self.note))
            return
