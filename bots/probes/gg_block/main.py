"""Q7: what BLOCKS a gunner's firing line, and what is TARGETABLE on it?

Uses `can_fire_from(pos, dir, turret_type, target)` -- a pure query that ignores ammo and
cooldown but reads live occupancy -- so nothing has to be built except the blockers themselves.
One Builder Bot does the whole experiment and resigns with the matrix (M07).

Hypothetical Gunner GP=(10,7) facing EAST. Its ray is (11,7),(12,7),(13,7).
  V = (13,7)  a permanent barrier: the "victim" at the far end of the ray.
  B = (11,7)  the blocker slot, one tile in front of the gunner.
  M = (12,7)  the middle tile. On arena `ggore` it is an ORE tile (so a Harvester can go there);
              on `ggwall` it is a WALL.

For each blocker we record V=can_fire(victim behind it) and B=can_fire(the blocker itself).
V=0 means "blocks the line", B=1 means "is itself a legal target".

Phase 0 additionally asks whether a CORE is targetable: hypothetical gunner at (5,7) facing WEST,
ray (4,7),(3,7),(2,7); (2,7) is our own Core's footprint.

Run:  python tools/runprobe.py gg_block --map lab/ggore
      python tools/runprobe.py gg_block --map lab/ggwall
"""

from fcode import Controller, Direction, EntityType, Environment, Position

GP = Position(10, 7)
V = Position(13, 7)
B = Position(11, 7)
M = Position(12, 7)
E = Direction.EAST
W = Direction.WEST
N = Direction.NORTH
G = EntityType.GUNNER

CORE_GP = Position(5, 7)
CORE_T = Position(2, 7)
CORE_MID = Position(3, 7)

SPAWN = Position(3, 6)
ST_CORE = Position(4, 6)
ST_V = Position(13, 6)
ST_B = Position(11, 6)
ST_M = Position(12, 6)


def q(ct, gp, d, tgt):
    try:
        return "1" if ct.can_fire_from(gp, d, G, tgt) else "0"
    except Exception:
        return "X"


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.s = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP" + str(self.s) + ":" + type(exc).__name__ + ":" + str(exc)[:20])
            self.s += 1

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        r = ct.get_current_round()
        if r > 200:
            self.done = True
            ct.resign(("TIMEOUT s=%d | " % self.s) + " | ".join(self.n)[:460])
            return
        self._step(ct)

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

    def row(self, ct, tag, gp, d, victim, blocker):
        self.n.append("%s V%s B%s" % (tag, q(ct, gp, d, victim), q(ct, gp, d, blocker)))

    def _step(self, ct):
        s = self.s
        if s == 0:
            if self.goto(ct, ST_CORE):
                self.s = 1
            return
        if s == 1:
            self.n.append("core t3=%s t2=%s mid=%s" % (
                q(ct, CORE_GP, W, CORE_T),
                q(ct, Position(4, 7), W, CORE_T),
                q(ct, CORE_GP, W, CORE_MID)))
            self.s = 2
            return
        if s == 2:
            if self.goto(ct, ST_V):
                self.s = 3
            return
        if s == 3:
            if ct.get_tile_building_id(V) is not None:
                self.s = 4
            elif ct.can_build_barrier(V):
                ct.build_barrier(V)
            return
        if s == 4:
            if self.goto(ct, ST_B):
                self.s = 5
            return
        if s == 5:
            self.row(ct, "clr", GP, E, V, B)
            self.n.append("mid%s" % q(ct, GP, E, M))
            self.s = 6
            return
        # blocker cycle: build at B, query, destroy.
        if s == 6:
            if ct.can_build_conveyor(B, E):
                ct.build_conveyor(B, E)
                self.s = 7
            return
        if s == 7:
            self.row(ct, "cnv", GP, E, V, B)
            self.s = 8
            return
        if s == 8:
            if ct.can_destroy(B):
                ct.destroy(B)
            self.s = 9
            return
        if s == 9:
            if ct.can_build_splitter(B, E):
                ct.build_splitter(B, E)
                self.s = 10
            return
        if s == 10:
            self.row(ct, "spl", GP, E, V, B)
            self.s = 11
            return
        if s == 11:
            if ct.can_destroy(B):
                ct.destroy(B)
            self.s = 12
            return
        if s == 12:
            if ct.can_build_barrier(B):
                ct.build_barrier(B)
                self.s = 13
            return
        if s == 13:
            self.row(ct, "bar", GP, E, V, B)
            self.s = 14
            return
        if s == 14:
            if ct.can_destroy(B):
                ct.destroy(B)
            self.s = 15
            return
        if s == 15:
            if ct.can_build_gunner(B, N):
                ct.build_gunner(B, N)
                self.s = 16
            return
        if s == 16:
            self.row(ct, "gun", GP, E, V, B)
            self.s = 17
            return
        if s == 17:
            self.n.append("gunDestroy=%s" % ("1" if ct.can_destroy(B) else "0"))
            if ct.can_destroy(B):
                ct.destroy(B)
            self.s = 18
            return
        if s == 18:
            if ct.get_tile_env(M) != Environment.ORE_TITANIUM:
                self.n.append("hv n/a")
                self.s = 21
                return
            if self.goto(ct, ST_M):
                self.s = 19
            return
        if s == 19:
            if ct.can_build_harvester(M):
                ct.build_harvester(M)
                self.s = 20
            else:
                self.n.append("hv nobuild")
                self.s = 21
            return
        if s == 20:
            self.n.append("hrv V%s M%s" % (q(ct, GP, E, V), q(ct, GP, E, M)))
            if ct.can_destroy(M):
                ct.destroy(M)
            self.s = 21
            return
        if s == 21:
            if self.goto(ct, ST_B):
                self.s = 22
            return
        if s == 22:
            if ct.can_move(Direction.SOUTH):
                ct.move(Direction.SOUTH)
                self.s = 23
            return
        if s == 23:
            self.n.append("bot V%s B%s" % (q(ct, GP, E, V), q(ct, GP, E, B)))
            self.s = 24
            return
        self.done = True
        ct.resign(" | ".join(self.n)[:495])
