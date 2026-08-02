"""Q3: the EXACT firing footprint of a Gunner and a Sentinel, tile by tile, in all 8 facings.

`get_attackable_tiles_from(position, direction, turret_type)` is a pure query -- it ignores ammo,
cooldown and occupancy -- and G34 says it is callable from a Builder Bot. So no turret has to be
built at all: one builder walks to an open station with >=5 clear tiles in every direction and
enumerates the raw pattern for GUNNER, SENTINEL and LAUNCHER over N/NE/E/SE/S/SW/W/NW + CENTRE.

Arena `maps/lab/ggopen.map26` (28x16, empty except two ore tiles at (5,1)/(22,14)). Station (10,7)
has 7 tiles of clearance N, 8 S, 17 E, 10 W -- no in-bounds truncation for any pattern up to 5.

Reports, per type: the tile count for each of the 8 facings, whether every returned tile is exactly
k*delta from the turret (a pure straight ray), and the maximum d^2 seen.

Run:  python tools/runprobe.py gg_geo --map lab/ggopen
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = (Direction.NORTH, Direction.NORTHEAST, Direction.EAST, Direction.SOUTHEAST,
        Direction.SOUTH, Direction.SOUTHWEST, Direction.WEST, Direction.NORTHWEST)
TYPES = (("G", EntityType.GUNNER), ("S", EntityType.SENTINEL), ("L", EntityType.LAUNCHER))
STATION = Position(10, 7)


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__ + ":" + str(exc)[:24])

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned:
                for d in (Direction.EAST, Direction.NORTH, Direction.SOUTH):
                    p = ct.get_position().add(d).add(Direction.EAST)
                    if ct.can_spawn(p):
                        ct.spawn_builder(p)
                        self.spawned = True
                        return
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        pos = ct.get_position()
        if pos != STATION:
            if r > 60:
                self.done = True
                ct.resign("GEO STUCK at %d,%d" % (pos.x, pos.y))
                return
            for d in (Direction.EAST, Direction.SOUTH, Direction.NORTH, Direction.WEST):
                q = pos.add(d)
                if q.distance_squared(STATION) < pos.distance_squared(STATION) and ct.can_move(d):
                    ct.move(d)
                    return
            return

        self.done = True
        for (tag, ty) in TYPES:
            counts = []
            pure = 0
            md2 = 0
            for i, d in enumerate(DIRS):
                try:
                    tiles = ct.get_attackable_tiles_from(pos, d, ty)
                except Exception:
                    counts.append("X")
                    continue
                n = len(tiles)
                counts.append(str(n) if n < 10 else "%d" % n)
                dx, dy = d.delta()
                want = set()
                for k in range(1, n + 1):
                    want.add((pos.x + k * dx, pos.y + k * dy))
                got = set((t.x, t.y) for t in tiles)
                if got == want:
                    pure |= (1 << i)
                for t in tiles:
                    md2 = max(md2, t.distance_squared(pos))
            try:
                nc = len(ct.get_attackable_tiles_from(pos, Direction.CENTRE, ty))
            except Exception as exc:
                nc = "!" + type(exc).__name__[:4]
            self.n.append("%s n=%s pure=%d/8 md2=%d C=%s" % (
                tag, ",".join(counts), bin(pure).count("1"), md2, nc))
        # Full offset dump for the two cardinal + two diagonal cases that matter.
        for (tag, ty, d) in (("GE", EntityType.GUNNER, Direction.EAST),
                             ("GNE", EntityType.GUNNER, Direction.NORTHEAST),
                             ("SE", EntityType.SENTINEL, Direction.EAST),
                             ("SNE", EntityType.SENTINEL, Direction.NORTHEAST)):
            tiles = ct.get_attackable_tiles_from(pos, d, ty)
            off = sorted((t.x - pos.x, t.y - pos.y) for t in tiles)
            self.n.append("%s[%s]" % (tag, ";".join("%d,%d" % o for o in off)))
        ct.resign(" | ".join(self.n)[:495])
