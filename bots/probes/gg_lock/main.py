"""Spawn-ring lockout: fill all 12 tiles of the ENEMY Core's spawn ring with our barriers.

Arena `close` (14x11): Core A anchor (1,5), Core B anchor (8,5) with footprint
(8,5)(9,5)(8,6)(9,6). The enemy spawn ring is the 4x4 block x in 7..10, y in 4..7
minus that footprint -- 12 tiles, every one of them on the block's boundary and so
reachable from OUTSIDE the block. The walk order below never steps inside the block,
so our own barriers can never trap the builder.

If `can_spawn` gates on the tile being free, the opponent (`gg_spam`, which spawns every
round it legally can) stops producing builders the moment the last barrier lands.
`b_units` in the result dict is the measurement.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

# (stand, build) -- walked in order, clockwise around the outside of the ring
JOBS = [
    (Position(7, 3), Position(7, 4)),
    (Position(8, 3), Position(8, 4)),
    (Position(9, 3), Position(9, 4)),
    (Position(10, 3), Position(10, 4)),
    (Position(11, 5), Position(10, 5)),
    (Position(11, 6), Position(10, 6)),
    (Position(11, 7), Position(10, 7)),
    (Position(9, 8), Position(9, 7)),
    (Position(8, 8), Position(8, 7)),
    (Position(7, 8), Position(7, 7)),
    (Position(6, 6), Position(7, 6)),
    (Position(6, 5), Position(7, 5)),
]


class Player:
    def __init__(self):
        self.spawned = False
        self.i = 0
        self.stuck = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("GGPROBE|EXC %s %s" % (type(exc).__name__, str(exc)[:30]))

    def step(self, ct, pos, tgt):
        best = None
        for d in CARD:
            if not ct.can_move(d):
                continue
            s = pos.add(d).distance_squared(tgt)
            if best is None or s < best[0]:
                best = (s, d)
        if best is not None and best[0] < pos.distance_squared(tgt):
            ct.move(best[1])
            return True
        return False

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 4)):
                ct.spawn_builder(Position(3, 4))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        pos = ct.get_position()

        if self.i >= len(JOBS):
            if r % 200 == 0:
                print("GGPROBE|SEALED r=%d ti=%d scale=%.1f" % (
                    r, ct.get_global_resources(), ct.get_scale_percent()))
            return

        stand, site = JOBS[self.i]
        if ct.get_tile_building_id(site) is not None:
            print("GGPROBE|SKIP %d,%d already occupied r=%d" % (site.x, site.y, r))
            self.i += 1
            return
        if pos != stand:
            if not self.step(ct, pos, stand):
                self.stuck += 1
                if self.stuck > 25:
                    print("GGPROBE|STUCK i=%d at=%d,%d want=%d,%d r=%d" % (
                        self.i, pos.x, pos.y, stand.x, stand.y, r))
                    self.stuck = 0
                    self.i += 1
            return
        self.stuck = 0
        if ct.can_build_barrier(site):
            ct.build_barrier(site)
            print("GGPROBE|BAR %d/%d at=%d,%d r=%d ti=%d scale=%.1f" % (
                self.i + 1, len(JOBS), site.x, site.y, r,
                ct.get_global_resources(), ct.get_scale_percent()))
            self.i += 1
