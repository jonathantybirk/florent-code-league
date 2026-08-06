"""SABOTAGE Q4c -- what a SENTINEL pays to shoot down 30 HP BARRIERs, on 2.3.6.

Same arena and same accounting as sb_gkill, with a SENTINEL at (12,8) facing WEST instead of a
gunner.  Sentinel reach is 5 cardinal tiles (r^2=32) and its shots are not blocked, so the target
sits at (10,8), two tiles out, with a builder parked at (10,9) replanting it.

The Core converts exactly one fixed ammo block at round 3 and never again, so fires-vs-ammo-left
measures SENTINEL_AMMO_COST directly.  The sentinel also dumps len(get_attackable_tiles()) and
its own fire cadence, since SENTINEL_FIRE_COOLDOWN=2 predicts a shot every other round and that
halves its effective sabotage rate.  Resigns with the lot (G29).
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
SPAWN = Position(4, 7)
SENPOS = Position(12, 8)
SENSTAND = Position(12, 9)
TGT = Position(10, 8)
STAND = Position(10, 9)
AMMO = 120
REPORT = 240


class Player:
    def __init__(self):
        self.spawned = False
        self.converted = False
        self.st = 0
        self.note = ""
        self.scost = None
        self.fires = 0
        self.kills = 0
        self.hps = []
        self.firerounds = []
        self.ammo0 = None
        self.first_kill_fires = None
        self.prev_bid = None
        self.pattern = None

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
                if p == SENSTAND:
                    self.st = 1
                else:
                    self.step(ct, p, SENSTAND)
                    return
            if self.st == 1:
                self.scost = ct.get_sentinel_cost()
                if ct.can_build_sentinel(SENPOS, Direction.WEST):
                    ct.build_sentinel(SENPOS, Direction.WEST)
                    self.st = 2
                return
            if self.st == 2:
                if p != STAND:
                    self.step(ct, p, STAND)
                    return
                if ct.get_tile_building_id(TGT) is None and ct.can_build_barrier(TGT):
                    ct.build_barrier(TGT)
                return
            return

        if et == EntityType.SENTINEL:
            if self.ammo0 is None:
                self.ammo0 = ct.get_global_ammo()
                self.pattern = len(ct.get_attackable_tiles())
            bid = ct.get_tile_building_id(TGT)
            if self.prev_bid is not None and bid != self.prev_bid:
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
                    "SBBARS scost=%s pattern=%s ammo %s->%s fires=%d kills=%d "
                    "firstkillfires=%s hpladder=%s gaps=%s ti=%d n=%s"
                    % (self.scost, self.pattern, self.ammo0, ct.get_global_ammo(),
                       self.fires, self.kills, self.first_kill_fires, self.hps,
                       sorted(gaps), ct.get_global_resources(), self.note))
            return
