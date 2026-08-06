"""SABOTAGE Q1a -- what a BUILDER pays to shoot down one 20 HP conveyor, on 2.3.6.

Arena `maps/lab/../dopen.map26` (20x12 open, Core A anchor (2,5)), vs noop.  A single builder
walks to STAND=(6,9), plants a conveyor on TGT=(6,8) (its own team's -- fire() is team-blind, so
the damage numbers are identical to shooting an enemy's), then fires at it every round until the
tile is empty.  It records the exact HP ladder, the round of every hit, and the treasury delta
across the whole kill so the Ti-per-kill is measured, not derived.

Second half: CHURN.  It rebuilds and destroy()s the same conveyor eight times, sampling
get_conveyor_cost() and get_scale_percent() each cycle.  That answers the question the whole
sabotage economy hinges on -- does a defender who keeps rebuilding a cut link pay a RISING price
(cumulative scale) or a flat 3 Ti (living-count scale)?

Reports with ct.resign() from the builder itself (G29).
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
SPAWN = Position(4, 7)
STAND = Position(6, 9)
TGT = Position(6, 8)
CHURN = 8


class Player:
    def __init__(self):
        self.spawned = False
        self.st = 0
        self.note = ""
        # kill phase
        self.hps = []
        self.fires = 0
        self.firerounds = []
        self.ti_before = None
        self.ti_after = None
        self.ammo_before = None
        self.ammo_after = None
        self.start_r = None
        self.kill_r = None
        self.buildcost = None
        # churn phase
        self.cycles = 0
        self.costs = []
        self.scales = []
        self.churn_ti0 = None

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

        if et != EntityType.BUILDER_BOT:
            return

        p = ct.get_position()

        # ---- walk to the station
        if self.st == 0:
            if p == STAND:
                self.st = 1
            else:
                self.step(ct, p, STAND)
                return

        # ---- plant the victim conveyor
        if self.st == 1:
            c0 = ct.get_conveyor_cost()
            ti0 = ct.get_global_resources()
            if ct.can_build_conveyor(TGT, Direction.NORTH):
                ct.build_conveyor(TGT, Direction.NORTH)
                self.buildcost = (c0, ti0 - ct.get_global_resources())
                self.st = 2
            return

        # ---- shoot it down, counting everything
        if self.st == 2:
            bid = ct.get_tile_building_id(TGT)
            if bid is None:
                self.kill_r = r
                self.ti_after = ct.get_global_resources()
                self.ammo_after = ct.get_global_ammo()
                self.st = 3
                return
            hp = ct.get_hp(bid)
            if not self.hps or self.hps[-1] != hp:
                self.hps.append(hp)
            if self.start_r is None:
                self.start_r = r
                self.ti_before = ct.get_global_resources()
                self.ammo_before = ct.get_global_ammo()
            if ct.can_fire(TGT):
                ct.fire(TGT)
                self.fires += 1
                if len(self.firerounds) < 14:
                    self.firerounds.append(r)
            return

        # ---- churn: rebuild + destroy, watching the price
        if self.st == 3:
            if self.churn_ti0 is None:
                self.churn_ti0 = ct.get_global_resources()
            if self.cycles >= CHURN:
                self.st = 4
                return
            bid = ct.get_tile_building_id(TGT)
            if bid is None:
                self.costs.append(ct.get_conveyor_cost())
                self.scales.append(int(ct.get_scale_percent()))
                if ct.can_build_conveyor(TGT, Direction.NORTH):
                    ct.build_conveyor(TGT, Direction.NORTH)
            else:
                if ct.can_destroy(TGT):
                    ct.destroy(TGT)
                    self.cycles += 1
            return

        if self.st == 4:
            gaps = []
            for i in range(1, len(self.firerounds)):
                g = self.firerounds[i] - self.firerounds[i - 1]
                if g not in gaps:
                    gaps.append(g)
            ct.resign(
                "SBBKILL build=%s hpladder=%s fires=%d r%s->%s gaps=%s "
                "ti %s->%s (d=%s) ammo %s->%s churncost=%s scale=%s churnti=%d->%d n=%s"
                % (self.buildcost, self.hps, self.fires, self.start_r, self.kill_r,
                   sorted(gaps), self.ti_before, self.ti_after,
                   (self.ti_before - self.ti_after) if self.ti_after is not None else None,
                   self.ammo_before, self.ammo_after, self.costs, self.scales,
                   self.churn_ti0 or 0, ct.get_global_resources(), self.note))
            return
