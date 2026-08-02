"""Q5 part 1: do Barriers and Walls actually block LINE OF SIGHT (vision), or only movement/fire?

game-objects item 16 claims "Barriers block line of sight, so they blind vision as well as stopping
movement". This tests it directly: one Builder Bot stands at (10,7), reads its vision of the four
tiles east of it, drops a barrier at (11,7), and reads them again. Any tile that stops being visible
was blinded by the barrier.

`get_tile_env` raises on a tile outside vision (G23), so both the boolean `is_in_vision` and the
raising `get_tile_env` are recorded -- they could disagree. `get_nearby_tiles()` counts are taken
before and after: a shadow-casting vision model must shrink the set.

On `maps/lab/ggwall.map26` the tile (12,7) is a WALL, so the same run also answers the wall case
without building anything.

Row format:  <tag> v=<is_in_vision for +1..+5 east> e=<get_tile_env ok for +1..+5> n=<nearby count>
Run:  python tools/runprobe.py gg_los --map lab/ggopen
      python tools/runprobe.py gg_los --map lab/ggwall
"""

from fcode import Controller, Direction, EntityType, Position

STAND = Position(10, 7)
BAR = Position(11, 7)
SPAWN = Position(3, 6)


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
            self.n.append("T:" + type(exc).__name__ + ":" + str(exc)[:18])

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        if ct.get_current_round() > 90:
            self.done = True
            ct.resign("LOS TIMEOUT s=%d" % self.s)
            return
        self._step(ct)

    def scan(self, ct, tag):
        pos = ct.get_position()
        v = ""
        e = ""
        for k in range(1, 6):
            p = Position(pos.x + k, pos.y)
            v += "1" if ct.is_in_vision(p) else "0"
            try:
                ct.get_tile_env(p)
                e += "1"
            except Exception:
                e += "0"
        self.n.append("%s v=%s e=%s n=%d" % (tag, v, e, len(ct.get_nearby_tiles())))

    def _step(self, ct):
        pos = ct.get_position()
        if self.s == 0:
            if pos != STAND:
                best = None
                for d in (Direction.EAST, Direction.WEST, Direction.NORTH, Direction.SOUTH):
                    nxt = pos.add(d)
                    sc = nxt.distance_squared(STAND)
                    if ct.can_move(d) and (best is None or sc < best[0]):
                        best = (sc, d)
                if best is not None and best[0] < pos.distance_squared(STAND):
                    ct.move(best[1])
                return
            self.s = 1
            return
        if self.s == 1:
            self.scan(ct, "base")
            self.s = 2
            return
        if self.s == 2:
            if ct.can_build_barrier(BAR):
                ct.build_barrier(BAR)
                self.s = 3
            else:
                self.n.append("nobar")
                self.s = 3
            return
        if self.s == 3:
            self.scan(ct, "bar")
            self.n.append("cff=%s" % (
                "1" if ct.can_fire_from(Position(9, 7), Direction.EAST,
                                        EntityType.GUNNER, Position(12, 7)) else "0"))
            self.s = 4
            return
        self.done = True
        ct.resign(" | ".join(self.n)[:495])
