"""SABOTAGE Q1b -- what a GUNNER pays to shoot down 20 HP conveyors, on 2.3.6.

Arena `dopen.map26` (20x12 open, Core A anchor (2,5)), vs noop.  One builder plants a GUNNER at
(10,8) facing WEST -- its 3-tile ray is (9,8)(8,8)(7,8) -- then parks at (8,9) and replants a
conveyor on (8,8) every time the tile goes empty.  (9,8) stays empty so it never blocks the line.

Ammo attribution is exact: the Core converts EXACTLY ONE fixed block of titanium into ammo at
round 3 and never again, so `fires` against `ammo left` measures GUNNER_AMMO_COST directly
instead of trusting the constant.  The gunner counts its own shots, the HP ladder of the first
kill, and how many conveyors it killed before running dry.  It resigns with the lot (G29).
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
SPAWN = Position(4, 7)
GUNPOS = Position(10, 8)
GUNSTAND = Position(10, 9)
TGT = Position(8, 8)
STAND = Position(8, 9)
AMMO = 120
REPORT = 240


class Player:
    def __init__(self):
        self.spawned = False
        self.converted = False
        self.st = 0
        self.note = ""
        self.gcost = None
        # gunner side
        self.fires = 0
        self.kills = 0
        self.hps = []
        self.firerounds = []
        self.ammo0 = None
        self.first_kill_fires = None
        self.prev_bid = None
        self.pattern = None
        self.rebuilds = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:8] + ":" + str(exc)[:40]

    def step(self, ct, pos, tgt):
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
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
                return
            if r >= 3 and not self.converted and ct.can_convert_ammo(AMMO):
                ct.convert_ammo(AMMO)
                self.converted = True
            return

        if et == EntityType.BUILDER_BOT:
            p = ct.get_position()
            if self.st == 0:
                if p == GUNSTAND:
                    self.st = 1
                else:
                    self.step(ct, p, GUNSTAND)
                    return
            if self.st == 1:
                self.gcost = ct.get_gunner_cost()
                if ct.can_build_gunner(GUNPOS, Direction.WEST):
                    ct.build_gunner(GUNPOS, Direction.WEST)
                    self.st = 2
                return
            if self.st == 2:
                if p != STAND:
                    self.step(ct, p, STAND)
                    return
                if ct.get_tile_building_id(TGT) is None and ct.can_build_conveyor(TGT, Direction.NORTH):
                    ct.build_conveyor(TGT, Direction.NORTH)
                    self.rebuilds += 1
                return
            return

        if et == EntityType.GUNNER:
            if self.ammo0 is None:
                self.ammo0 = ct.get_global_ammo()
                self.pattern = len(ct.get_attackable_tiles())
            bid = ct.get_tile_building_id(TGT)
            if bid is not None and self.prev_bid is not None and bid != self.prev_bid:
                self.kills += 1
                if self.first_kill_fires is None:
                    self.first_kill_fires = self.fires
            if bid is None and self.prev_bid is not None:
                self.kills += 1
                if self.first_kill_fires is None:
                    self.first_kill_fires = self.fires
            self.prev_bid = bid
            if bid is not None:
                hp = ct.get_hp(bid)
                if self.kills == 0 and (not self.hps or self.hps[-1] != hp):
                    self.hps.append(hp)
                if ct.can_fire(TGT):
                    ct.fire(TGT)
                    self.fires += 1
                    if len(self.firerounds) < 10:
                        self.firerounds.append(r)
            if r >= REPORT:
                gaps = []
                for i in range(1, len(self.firerounds)):
                    g = self.firerounds[i] - self.firerounds[i - 1]
                    if g not in gaps:
                        gaps.append(g)
                ct.resign(
                    "SBGKILL gcost=%s pattern=%s ammo %s->%s fires=%d kills=%d "
                    "firstkillfires=%s hpladder=%s gaps=%s rebuilds=? ti=%d n=%s"
                    % (self.gcost, self.pattern, self.ammo0, ct.get_global_ammo(),
                       self.fires, self.kills, self.first_kill_fires, self.hps,
                       sorted(gaps), ct.get_global_resources(), self.note))
            return
