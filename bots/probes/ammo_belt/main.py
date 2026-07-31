"""Probe: does a conveyor still deliver anything to a turret in 2.3.3?

Arena `belt` (20x12): Core A anchor (1,5); ore at (5,5).
Scripted build: harvester(5,5) -> conveyor(6,5) facing EAST -> gunner(7,5) facing EAST -> barrier(8,5).

The GUNNER is the reporter (it sees the whole chain: r^2=13 vision).
  B1 does the conveyor's stored stack ever move on (id changes) or does it jam forever (id constant)?
  B2 does global ammo rise while the belt runs? (Core converts nothing until round 40.)
  B3 can a gunner fire at ammo 0?
  B4 does a shot deduct exactly GUNNER_AMMO_COST=2 from the global pool?
  B5 does get_stored_resource() on a turret raise?
  B6 team-blindness re-test: gunner faces EAST at our OWN barrier at (8,5).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

CONV = Position(6, 5)
GUN = Position(7, 5)
BAR = Position(8, 5)
HARV = Position(5, 5)

# (kind, arg1, arg2) executed one per round by the builder.
SCRIPT = [
    ("mv", Direction.EAST, None),           # (3,5) -> (4,5)
    ("harv", HARV, None),
    ("mv", Direction.NORTH, None),          # (4,5) -> (4,4)
    ("mv", Direction.EAST, None),           # -> (5,4)
    ("mv", Direction.EAST, None),           # -> (6,4)
    ("conv", CONV, Direction.EAST),
    ("mv", Direction.EAST, None),           # -> (7,4)
    ("gun", GUN, Direction.EAST),
    ("mv", Direction.EAST, None),           # -> (8,4)
    ("bar", BAR, None),
    ("mv", Direction.NORTH, None),          # step out of the way
]


def err(exc):
    return type(exc).__name__ + ":" + str(exc)[:40]


class Player:
    def __init__(self):
        self.n = []
        self.step = 0
        self.spawned = False
        self.first_fill = None
        self.first_id = None
        self.ids = []
        self.shots = 0
        self.fired_at0 = None
        self.tgt = None
        self.storeraise = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + err(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            self._core(ct, r)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)
        elif et == EntityType.GUNNER:
            self._gunner(ct, r)

    def _core(self, ct, r):
        if not self.spawned:
            p = Position(3, 5)
            if ct.can_spawn(p):
                ct.spawn_builder(p)
                self.spawned = True
            return
        # Deliberately leave ammo at 0 until round 40 so B2/B3 are clean.
        if r == 40 and ct.can_convert_ammo(20):
            ct.convert_ammo(20)

    def _builder(self, ct):
        if self.step >= len(SCRIPT):
            return
        kind, a, b = SCRIPT[self.step]
        ok = False
        if kind == "mv":
            if ct.can_move(a):
                ct.move(a)
                ok = True
        elif kind == "harv":
            if ct.can_build_harvester(a):
                ct.build_harvester(a)
                ok = True
        elif kind == "conv":
            if ct.can_build_conveyor(a, b):
                ct.build_conveyor(a, b)
                ok = True
        elif kind == "gun":
            if ct.can_build_gunner(a, b):
                ct.build_gunner(a, b)
                ok = True
        elif kind == "bar":
            if ct.can_build_barrier(a):
                ct.build_barrier(a)
                ok = True
        if ok:
            self.step += 1

    def _gunner(self, ct, r):
        # B5: storage on a turret
        if self.storeraise is None:
            try:
                ct.get_stored_resource()
                self.storeraise = "NO-RAISE"
            except Exception as exc:
                self.storeraise = err(exc)

        # B1: conveyor stack identity over time
        sid = None
        try:
            sid = ct.get_stored_resource_id(ct.get_tile_building_id(CONV))
        except Exception:
            sid = "ERR"
        if isinstance(sid, int):
            if self.first_fill is None:
                self.first_fill = r
                self.first_id = sid
            if not self.ids or self.ids[-1] != sid:
                if len(self.ids) < 6:
                    self.ids.append(sid)

        ammo = ct.get_global_ammo()

        # B3: try to fire at ammo 0 before the Core ever converts
        if self.fired_at0 is None and r < 40:
            t = ct.get_gunner_target()
            self.tgt = None if t is None else (t.x, t.y)
            cf = ct.can_fire(t) if t is not None else "no-target"
            try:
                if t is not None:
                    ct.fire(t)
                    self.fired_at0 = "FIRED@ammo%d" % ammo
                else:
                    self.fired_at0 = "notgt"
            except Exception as exc:
                self.fired_at0 = "blocked:" + err(exc)
            self.n.append("B3 r%d ammo=%d tgt=%s canfire=%s %s" % (
                r, ammo, self.tgt, cf, self.fired_at0))

        # B4: fire with ammo available and measure the deduction
        if r > 40 and self.shots < 3:
            t = ct.get_gunner_target()
            if t is not None and ct.can_fire(t):
                hp0 = ct.get_hp(ct.get_tile_building_id(t))
                ct.fire(t)
                self.shots += 1
                self.n.append("B4 shot%d tgt=%d,%d ammo %d->%d hp %s->%s" % (
                    self.shots, t.x, t.y, ammo, ct.get_global_ammo(),
                    hp0, ct.get_hp(ct.get_tile_building_id(t))))

        if r == 39:
            self.n.append("B2 r39 ammo=%d convfill=%s id0=%s" % (
                ammo, self.first_fill, self.first_id))
        if r == 90:
            self.n.append("B1 convids=%s ti=%d" % (self.ids, ct.get_global_resources()))
            self.n.append("B5 turret_store=%s" % self.storeraise)
            ct.resign(" | ".join(self.n[:12]))
