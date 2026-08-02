"""Q4 (game-objects item 11): rotation economics. Does rotating a Gunner cost a flat 10 Ti at any
cost scale, and does it add NO scale of its own?

The reporter is the GUNNER itself (M07): it can read get_global_resources(), get_scale_percent()
and every cost getter, and it is the only unit that can call rotate(). Each sample is taken
WITHIN A SINGLE TURN -- ti/scale read, rotate, ti/scale read again -- so the +10 Ti passive tick
every 4 rounds cannot contaminate the delta.

The Core inflates the global cost scale in the background by spawning throwaway Builder Bots
(+20 percentage points each, G07). Those extras idle: a Builder Bot whose first observed round is
> 3 does nothing at all.

Arena `maps/lab/ggopen.map26`.

Row format:  r<round> s<scale> gc<gunner_cost> rc<rotate_cost> ds<scale_delta>
Run:  python tools/runprobe.py gg_rot --map lab/ggopen
"""

from fcode import Controller, Direction, EntityType, Position

GUN = Position(10, 7)
STAND = Position(10, 6)
SPAWN0 = Position(3, 6)
E = Direction.EAST
CYCLE = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST,
         Direction.NORTHEAST, Direction.SOUTHEAST, Direction.SOUTHWEST, Direction.NORTHWEST)
BUMP_ROUNDS = (16, 20, 24, 28, 32, 36, 40)
ROT_ROUNDS = (14, 18, 22, 26, 30, 34, 38, 42, 46)
RING = [Position(x, y) for x in range(0, 4) for y in range(6, 10)]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.birth = None
        self.k = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T:" + type(exc).__name__ + ":" + str(exc)[:18])

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN0):
                ct.spawn_builder(SPAWN0)
                self.spawned = True
                return
            if r in BUMP_ROUNDS:
                for p in RING:
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        return
            return
        if et == EntityType.BUILDER_BOT:
            if self.birth is None:
                self.birth = r
            if self.birth > 3:
                return
            self._worker(ct)
            return
        if et == EntityType.GUNNER:
            self._gunner(ct, r)

    def _worker(self, ct):
        pos = ct.get_position()
        if pos != STAND:
            best = None
            for d in (Direction.EAST, Direction.NORTH, Direction.SOUTH, Direction.WEST):
                nxt = pos.add(d)
                sc = nxt.distance_squared(STAND)
                if ct.can_move(d) and (best is None or sc < best[0]):
                    best = (sc, d)
            if best is not None and best[0] < pos.distance_squared(STAND):
                ct.move(best[1])
            return
        if ct.get_tile_building_id(GUN) is None and ct.can_build_gunner(GUN, E):
            ct.build_gunner(GUN, E)

    def _gunner(self, ct, r):
        if self.done:
            return
        if r in ROT_ROUNDS and self.k < len(CYCLE):
            d = CYCLE[self.k % len(CYCLE)]
            if ct.get_direction() == d:
                d = CYCLE[(self.k + 1) % len(CYCLE)]
            ti0 = ct.get_global_resources()
            s0 = ct.get_scale_percent()
            gc = ct.get_gunner_cost()
            if not ct.can_rotate(d):
                self.n.append("r%d s%d NOROT ti%d" % (r, int(s0), ti0))
                self.k += 1
                return
            ct.rotate(d)
            ti1 = ct.get_global_resources()
            s1 = ct.get_scale_percent()
            self.n.append("r%d s%d gc%d rc%d ds%d" % (
                r, int(s0), gc, ti0 - ti1, int(s1 - s0)))
            self.k += 1
        if r == 50:
            self.done = True
            self.n.append("FIN s%d gc%d sc%d bc%d cv%d ti%d" % (
                int(ct.get_scale_percent()), ct.get_gunner_cost(), ct.get_sentinel_cost(),
                ct.get_builder_bot_cost(), ct.get_conveyor_cost(), ct.get_global_resources()))
            ct.resign(" | ".join(self.n)[:495])
