"""Q1/Q2: ray jamming as a weapon -- does a 3 Ti barrier neutralise a 10 Ti Gunner, and for how long?

Everything about turret targeting is team-blind (G10), so a friendly jammer and an enemy jammer are
the same experiment. This builds OUR Gunner at (10,7) facing EAST and OUR barriers on all three
tiles of its ray, (11,7),(12,7),(13,7), then meters what it takes to clear them.

Arena `maps/lab/ggopen.map26` (28x16, empty). Timeline, driven off the round counter so the two
sub-interpreters stay in step (G20/M07 -- only the Gunner reports):

  r0..~r20  builder walks the y=6 lane, builds the gunner then the three barriers.
  r34       PRE   : target + can_fire_from on each ray tile with the ammo pool still empty.
  r35       builder DESTROYS the near barrier (11,7) itself -- no shot fired.
  r36       DEL   : did the target advance to (12,7)? (tests "the jam is permanent" claim)
  r37       builder rebuilds (11,7).
  r38       REB   : did the target fall back to (11,7)?
  r50       Core converts 40 ammo.
  r51+      the Gunner fires at get_gunner_target() every round; each barrier death is logged
            with the round and the remaining ammo.

Run:  python tools/runprobe.py gg_jam --map lab/ggopen
"""

from fcode import Controller, Direction, EntityType, Position

GUN = Position(10, 7)
R1 = Position(11, 7)
R2 = Position(12, 7)
R3 = Position(13, 7)
RAY = (R1, R2, R3)
E = Direction.EAST
G = EntityType.GUNNER
SPAWN = Position(3, 6)

# (station, action) -- action is None for a pure walk step.
SCRIPT = [
    (Position(10, 6), ("gun", GUN)),
    (Position(11, 6), ("bar", R1)),
    (Position(12, 6), ("bar", R2)),
    (Position(13, 6), ("bar", R3)),
    (Position(11, 6), None),
]


def ts(p):
    return "-" if p is None else "%d,%d" % (p.x, p.y)


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.s = 0
        self.alive = [True, True, True]
        self.shots = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T:" + type(exc).__name__ + ":" + str(exc)[:20])

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
                return
            if r == 50 and ct.can_convert_ammo(40):
                ct.convert_ammo(40)
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct, r)
            return
        if et == EntityType.GUNNER:
            self._gunner(ct, r)

    def goto(self, ct, tgt):
        pos = ct.get_position()
        if pos == tgt:
            return True
        best = None
        for d in (Direction.EAST, Direction.WEST, Direction.NORTH, Direction.SOUTH):
            nxt = pos.add(d)
            sc = nxt.distance_squared(tgt)
            if ct.can_move(d) and (best is None or sc < best[0]):
                best = (sc, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])
        return False

    def _builder(self, ct, r):
        if self.s < len(SCRIPT):
            station, act = SCRIPT[self.s]
            if not self.goto(ct, station):
                return
            if act is None:
                self.s += 1
                return
            kind, p = act
            if ct.get_tile_building_id(p) is not None:
                self.s += 1
                return
            if kind == "gun" and ct.can_build_gunner(p, E):
                ct.build_gunner(p, E)
                self.s += 1
            elif kind == "bar" and ct.can_build_barrier(p):
                ct.build_barrier(p)
                self.s += 1
            return
        if r == 35 and ct.can_destroy(R1):
            ct.destroy(R1)
            return
        if r == 37 and ct.can_build_barrier(R1):
            ct.build_barrier(R1)
            return

    def _gunner(self, ct, r):
        if self.done:
            return
        if r == 34:
            self.n.append("PRE t=%s cff=%s%s%s cf1=%d ammo=%d hp=%s" % (
                ts(ct.get_gunner_target()),
                "1" if ct.can_fire_from(GUN, E, G, R1) else "0",
                "1" if ct.can_fire_from(GUN, E, G, R2) else "0",
                "1" if ct.can_fire_from(GUN, E, G, R3) else "0",
                1 if ct.can_fire(R1) else 0, ct.get_global_ammo(),
                "/".join(str(ct.get_hp(ct.get_tile_building_id(p))) for p in RAY)))
        if r == 36:
            self.n.append("DEL t=%s cff2=%s" % (
                ts(ct.get_gunner_target()),
                "1" if ct.can_fire_from(GUN, E, G, R2) else "0"))
        if r == 38:
            self.n.append("REB t=%s" % ts(ct.get_gunner_target()))
        if r > 50:
            t = ct.get_gunner_target()
            if t is not None and ct.can_fire(t):
                ct.fire(t)
                self.shots += 1
            for i, p in enumerate(RAY):
                if self.alive[i] and ct.get_tile_building_id(p) is None:
                    self.alive[i] = False
                    self.n.append("k%d r%d sh%d am%d" % (
                        i + 1, r, self.shots, ct.get_global_ammo()))
        if r == 75:
            self.done = True
            self.n.append("END t=%s sh=%d am=%d" % (
                ts(ct.get_gunner_target()), self.shots, ct.get_global_ammo()))
            ct.resign(" | ".join(self.n)[:495])
