"""SABOTAGE Q2 -- the belt-sniping WAR, priced per round, on 2.3.6.  `maps/lab/sab.map26` vs sb_vic.

Team A runs the SAME one-chain economy as the victim (harvester(6,4) -> conveyor(5,4)W ->
conveyor(4,4)W -> Core foot (3,4)) so the two treasuries are directly comparable, and then pays
for sabotage on top:

  builder #2 walks to (17,8) and plants a GUNNER on (17,7) facing NORTH.  Its 3-tile ray is
  (17,6)(17,5)(17,4); the first two stay empty, so its only legal target is the victim's TERMINAL
  conveyor (17,4).  The builder then retreats to (16,8), out of the ray.

  The Core tops the ammo pool up whenever it drops below AMMO_LOW, so firing is limited by
  INCOME, not by a one-off ammo grant -- which is the whole question.

The gunner is the reporter.  Every round it samples the target tile and accumulates:
  fires, kills, rounds the tile was EMPTY (= denial window), rounds it was OCCUPIED, and the
  rounds on which it was unable to fire for lack of ammo.  Resigns at round 800.

`sb_warc` is the identical bot with the trigger disabled; the difference between the two runs'
`b_titanium_collected` is the titanium this sabotage actually denied.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
FIRE_ENABLED = True

ECON_SPAWN = Position(4, 3)
WAR_SPAWN = Position(4, 6)
HARV = Position(6, 4)
MID = Position(5, 4)
TERM = Position(4, 4)

GUNPOS = Position(17, 7)
GUNSTAND = Position(17, 8)
RETREAT = Position(16, 8)
TARGET = Position(17, 4)

AMMO_LOW = 24
AMMO_TOP = 40
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
        self.st = 0
        self.note = ""
        # gunner counters
        self.fires = 0
        self.kills = 0
        self.empty = 0
        self.occupied = 0
        self.dry = 0
        self.prev_bid = None
        self.first_fire = None
        self.ti_lo = 99999

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
                    want -= 4
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

            # war builder: plant the gunner, then get out of its ray
            if self.st == 0:
                if p == GUNSTAND:
                    self.st = 1
                else:
                    self.walk(ct, p, GUNSTAND)
                    return
            if self.st == 1:
                if ct.can_build_gunner(GUNPOS, Direction.NORTH):
                    ct.build_gunner(GUNPOS, Direction.NORTH)
                    self.st = 2
                return
            if self.st == 2 and p != RETREAT:
                self.walk(ct, p, RETREAT)
            return

        if et == EntityType.GUNNER:
            bid = ct.get_tile_building_id(TARGET)
            if self.prev_bid is not None and bid != self.prev_bid:
                self.kills += 1
            self.prev_bid = bid
            ti = ct.get_global_resources()
            if ti < self.ti_lo:
                self.ti_lo = ti

            if bid is None:
                self.empty += 1
            else:
                self.occupied += 1
                if FIRE_ENABLED:
                    if ct.can_fire(TARGET):
                        ct.fire(TARGET)
                        self.fires += 1
                        if self.first_fire is None:
                            self.first_fire = r
                    elif ct.get_action_cooldown() == 0 and ct.get_global_ammo() < 4:
                        self.dry += 1

            if r >= REPORT:
                ct.resign(
                    "SBWAR fire=%s r=%d fires=%d kills=%d empty=%d occ=%d dry=%d "
                    "firstfire=%s ammoTi=%d a_ti=%d a_ti_lo=%d ammo=%d units=%d scale=%d n=%s"
                    % (FIRE_ENABLED, r, self.fires, self.kills, self.empty, self.occupied,
                       self.dry, self.first_fire, self.fires * 4, ti, self.ti_lo,
                       ct.get_global_ammo(), ct.get_unit_count(),
                       int(ct.get_scale_percent()), self.note))
            return
