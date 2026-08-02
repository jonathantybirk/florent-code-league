"""The FULL raw attack pattern of Gunner, Sentinel and Launcher in all eight facings.

get_attackable_tiles_from() is callable from a Builder Bot (G34), so no construction is
needed. Arena `openfield` (24x20), Core A anchor (1,9); the builder is spawned on the ring
and reports from wherever it is standing, well clear of every edge.

Prints, per direction, the offset list relative to the hypothetical turret position.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

DIRS = [("N", Direction.NORTH), ("NE", Direction.NORTHEAST),
        ("E", Direction.EAST), ("SE", Direction.SOUTHEAST),
        ("S", Direction.SOUTH), ("SW", Direction.SOUTHWEST),
        ("W", Direction.WEST), ("NW", Direction.NORTHWEST)]
TYPES = [("G", EntityType.GUNNER), ("S", EntityType.SENTINEL),
         ("L", EntityType.LAUNCHER)]
HOME = Position(11, 9)
CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


class Player:
    def __init__(self):
        self.spawned = False
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("GGPROBE|EXC %s %s" % (type(exc).__name__, str(exc)[:50]))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        pos = ct.get_position()
        if pos != HOME:
            best = None
            for d in CARD:
                if not ct.can_move(d):
                    continue
                sc = pos.add(d).distance_squared(HOME)
                if best is None or sc < best[0]:
                    best = (sc, d)
            if best is not None and best[0] < pos.distance_squared(HOME):
                ct.move(best[1])
            return
        self.done = True
        for (tn, ty) in TYPES:
            for (dn, d) in DIRS:
                try:
                    ts = ct.get_attackable_tiles_from(pos, d, ty)
                    offs = sorted((t.x - pos.x, t.y - pos.y) for t in ts)
                    md = max([(o[0] ** 2 + o[1] ** 2) for o in offs]) if offs else -1
                    print("GGPROBE|%s %s n=%d maxd2=%d %s" % (
                        tn, dn, len(offs), md,
                        ",".join("%d:%d" % o for o in offs[:40])))
                except Exception as exc:
                    print("GGPROBE|%s %s ERR %s %s" % (
                        tn, dn, type(exc).__name__, str(exc)[:40]))
        ct.resign("GGP|arcs2 done")
