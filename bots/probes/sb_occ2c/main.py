"""SABOTAGE Q3b -- CUT-THEN-OCCUPY, with the occupier acting AFTER its own killer.

sb_occ failed with placed=0 / empty=0: the occupying builder never once saw tile (17,4) empty.
The cause is turn order, not a rule.  Within a round every unit of team A acts before any unit of
team B, and inside a team they act in ENTITY-ID order.  In sb_occ the war builder was spawned
before the sentinel it built, so its id was lower: each round it inspected (17,4) BEFORE the
sentinel fired, and by its next turn the victim had already replanted the link.

The fix is scheduling.  This probe spawns a THIRD builder only after the sentinel exists, so the
occupier holds the highest entity id on the team and acts LAST:

    ... econ builder ... war builder ... SENTINEL fires and kills (17,4) ... OCCUPIER sees the
    tile empty in the SAME round and drops a 3 Ti barrier on it ... only then does team B run.

If that lands, the victim's chain is cut by a building it cannot destroy() (allied-only), and
clearing it costs turret ammo it does not have in sb_vic.

Same arena, same sentinel at (17,9) facing NORTH, same park tile (17,5).  The occupier publishes
through store slots 0..5 and the SENTINEL resigns at round 800 with both halves.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
SABOTAGE = False

ECON_SPAWN = Position(4, 3)
WAR_SPAWN = Position(4, 6)
OCC_SPAWN = Position(4, 5)
OCC_ROUND = 60

HARV = Position(6, 4)
MID = Position(5, 4)
TERM = Position(4, 4)

SENPOS = Position(17, 9)
SENSTAND = Position(17, 8)
RETREAT = Position(16, 8)
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
            if self.spawned == 2 and r >= OCC_ROUND:
                if ct.can_spawn(OCC_SPAWN):
                    ct.spawn_builder(OCC_SPAWN)
                    self.spawned = 3
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
                if p == ECON_SPAWN:
                    self.role = "econ"
                elif p == WAR_SPAWN:
                    self.role = "war"
                else:
                    self.role = "occ"

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

            if self.role == "war":
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
                if self.st == 2 and p != RETREAT:
                    self.walk(ct, p, RETREAT)
                return

            # occupier -- highest entity id, therefore acts after the sentinel
            if p != PARK:
                self.walk(ct, p, PARK)
                return
            bid = ct.get_tile_building_id(TARGET)
            if bid is None:
                self.empty += 1
                if SABOTAGE and ct.can_build_barrier(TARGET):
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
            if SABOTAGE and bid is not None and ct.get_team(bid) != ct.get_team():
                if ct.can_fire(TARGET):
                    ct.fire(TARGET)
                    self.fires += 1
            if r >= REPORT:
                ct.resign(
                    "SBOCC2C r=%d senfires=%d ammoTi=%d tilechanges=%d | occ: placed=%d "
                    "heals=%d ours=%d theirs=%d empty=%d firsthold=%d | a_ti=%d ammo=%d "
                    "scale=%d n=%s"
                    % (r, self.fires, self.fires * 10, self.kills,
                       ct.read_store(S_PLACED), ct.read_store(S_HEALS),
                       ct.read_store(S_OURS), ct.read_store(S_THEIRS),
                       ct.read_store(S_EMPTY), ct.read_store(S_FIRSTHOLD),
                       ct.get_global_resources(), ct.get_global_ammo(),
                       int(ct.get_scale_percent()), self.note))
            return
