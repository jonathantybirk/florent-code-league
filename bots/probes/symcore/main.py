"""Is the ENEMY CORE at (W-2-x, H-2-y) of ours -- derivable at round 0, for zero bits of comms?

The map files say yes on all 15 active maps, but the file's stored w/h and the engine's
get_map_width() need not agree, and the file check is worthless if they don't. So ask the ENGINE.

The Core reports its own position and the map dims immediately, then walks a scout out to find the
enemy Core and reports where it actually was. Run this from BOTH seats.
"""

from fcode import Controller, Direction, EntityType, Position

LAST = 400


class Player:
    def __init__(self):
        self.done = False
        self.n = []
        self.home = None
        self.dims = None
        self.spawned = 0
        self.found = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:%s" % type(exc).__name__)

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._scout(ct)

    def _core(self, ct):
        if self.done:
            return
        r = ct.get_current_round()
        if self.home is None:
            self.home = ct.get_position()
            self.dims = (ct.get_map_width(), ct.get_map_height())
            self.n.append("seat=%s home=(%d,%d) dims=%dx%d pred_w2=(%d,%d) pred_w1=(%d,%d)" % (
                str(ct.get_team()).split(".")[-1], self.home.x, self.home.y,
                self.dims[0], self.dims[1],
                self.dims[0] - 2 - self.home.x, self.dims[1] - 2 - self.home.y,
                self.dims[0] - 1 - self.home.x, self.dims[1] - 1 - self.home.y))
        if self.spawned < 4 and r < 8:
            for q in ct.get_nearby_tiles(2):
                try:
                    if ct.can_spawn(q):
                        ct.spawn_builder(q)
                        self.spawned += 1
                        break
                except Exception:
                    continue
        v = ct.read_store(0)
        if v and self.found is None:
            self.found = (v // 64 - 1, v % 64)
            self.n.append("ENEMY CORE ACTUALLY AT (%d,%d)" % self.found)
        if (self.found is not None and r > 12) or r >= LAST:
            w, h = self.dims
            p = (w - 2 - self.home.x, h - 2 - self.home.y)
            self.n.append("w-2 rule %s" % ("HOLDS" if self.found == p else
                                           ("FAILS pred=(%d,%d)" % p if self.found else "not found")))
            self.done = True
            ct.resign(" | ".join(self.n))

    def _scout(self, ct):
        me = ct.get_team()
        for i in ct.get_nearby_buildings():
            try:
                if ct.get_entity_type(i) == EntityType.CORE and ct.get_team(i) != me:
                    q = ct.get_position(i)
                    ct.write_store(0, (q.x + 1) * 64 + q.y)
                    return
            except Exception:
                continue
        w, h = ct.get_map_width(), ct.get_map_height()
        p = ct.get_position()
        tx = w - 2 - p.x if p.x * 2 < w else 1
        for d in ((Direction.EAST if p.x < w // 2 else Direction.WEST),
                  (Direction.SOUTH if p.y < h // 2 else Direction.NORTH),
                  Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
            try:
                if ct.can_move(d):
                    ct.move(d)
                    return
            except Exception:
                continue
