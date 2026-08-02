"""DEFENCE Q3 -- seal our own Core's 12-tile ring with barriers and count what can still shoot it.

Arena `maps/lab/dopen.map26`, vs noop.  Core A anchor (2,5); footprint (2,5)(3,5)(2,6)(3,6);
the ring is the 12 tiles of the 4x4 block minus the footprint (G63).

`can_fire_from(pos, dir, turret_type, target)` is a hypothetical query that respects current
occupancy and walls but ignores ammo and cooldown, and it is callable from a plain Builder Bot.
So one builder can enumerate EVERY tile from which a Gunner or a Sentinel could legally shoot a
Core footprint tile -- first with an open ring, then after walking the outside of the ring and
barriering all twelve tiles.  If the post-seal count is 0, a Core behind 12 barriers cannot be
shot at all until one of those barriers is cleared.

The BUILDER is the reporter (M07).
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
CARD8 = (Direction.NORTH, Direction.NORTHEAST, Direction.EAST, Direction.SOUTHEAST,
         Direction.SOUTH, Direction.SOUTHWEST, Direction.WEST, Direction.NORTHWEST)
FOOT = ((2, 5), (3, 5), (2, 6), (3, 6))
RING = ((1, 4), (2, 4), (3, 4), (4, 4), (1, 5), (4, 5),
        (1, 6), (4, 6), (1, 7), (2, 7), (3, 7), (4, 7))
ROUTE = [(5, 7), (5, 6), (5, 5), (5, 4), (5, 3), (4, 3), (3, 3), (2, 3), (1, 3),
         (0, 3), (0, 4), (0, 5), (0, 6), (0, 7), (0, 8), (1, 8), (2, 8), (3, 8)]


class Player:
    def __init__(self):
        self.spawned = False
        self.leg = 0
        self.pre = None
        self.post = None
        self.err = 0
        self.last = []
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def count(self, ct, et):
        hits = 0
        self.last = []
        for x in range(0, 10):
            for y in range(0, 12):
                if (x, y) in FOOT:
                    continue
                ok = False
                for d in CARD8:
                    for f in FOOT:
                        try:
                            if ct.can_fire_from(Position(x, y), d, et,
                                                Position(f[0], f[1])):
                                ok = True
                        except Exception:
                            self.err += 1
                if ok:
                    hits += 1
                    self.last.append((x, y))
        return hits

    def sealed(self, ct):
        n = 0
        for t in RING:
            try:
                if ct.get_tile_building_id(Position(t[0], t[1])) is not None:
                    n += 1
            except Exception:
                self.err += 1
        return n

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(4, 7)):
                ct.spawn_builder(Position(4, 7))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return

        p = ct.get_position()
        if self.pre is None:
            self.pre = (self.count(ct, EntityType.GUNNER),
                        self.count(ct, EntityType.SENTINEL))
            return

        for t in RING:
            tp = Position(t[0], t[1])
            if abs(t[0] - p.x) + abs(t[1] - p.y) != 1:
                continue
            if ct.get_tile_building_id(tp) is not None:
                continue
            if ct.can_build_barrier(tp):
                ct.build_barrier(tp)
                return

        if self.leg < len(ROUTE):
            if (p.x, p.y) == ROUTE[self.leg]:
                self.leg += 1
            if self.leg < len(ROUTE):
                t = ROUTE[self.leg]
                d = DIRS.get((t[0] - p.x, t[1] - p.y))
                if d is not None and ct.can_move(d):
                    ct.move(d)
                return

        self.done = True
        n = self.sealed(ct)
        gpost = self.count(ct, EntityType.GUNNER)
        gwhere = list(self.last)
        self.post = (gpost, self.count(ct, EntityType.SENTINEL))
        onring = 0
        for t in gwhere:
            if t in RING:
                onring += 1
        ct.resign("DRING sealed=%d/12 gun_pos %d->%d (of which on the ring itself: %d) "
                  "sent_pos %d->%d err=%d ti=%d barrier=%d scale=%.0f r=%d"
                  % (n, self.pre[0], self.post[0], onring, self.pre[1], self.post[1],
                     self.err, ct.get_global_resources(), ct.get_barrier_cost(),
                     ct.get_scale_percent(), ct.get_current_round()))
