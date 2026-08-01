"""Probe: dump the Gunner raw attack pattern + Core spawn ring via the resign message channel.

print() does not reach stdout (G29) but run_game returns resign_message, so that is our wire.
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = [
    ("N", Direction.NORTH), ("NE", Direction.NORTHEAST),
    ("E", Direction.EAST), ("SE", Direction.SOUTHEAST),
    ("S", Direction.SOUTH), ("SW", Direction.SOUTHWEST),
    ("W", Direction.WEST), ("NW", Direction.NORTHWEST),
]


class Player:
    def __init__(self):
        self.done = False

    def run(self, ct: Controller) -> None:
        if self.done:
            return
        try:
            if ct.get_entity_type() != EntityType.CORE:
                return
        except Exception:
            return
        self.done = True
        out = []
        p = ct.get_position()
        out.append("core=%d,%d" % (p.x, p.y))
        out.append("map=%dx%d" % (ct.get_map_width(), ct.get_map_height()))

        # 1. raw gunner pattern, relative offsets, from a tile well away from the core
        origin = Position(5, 5)
        for label, d in DIRS:
            try:
                tiles = ct.get_attackable_tiles_from(origin, d, EntityType.GUNNER)
                rel = sorted((t.x - 5, t.y - 5) for t in tiles)
                out.append("G%s=%s" % (label, ";".join("%d,%d" % r for r in rel)))
            except Exception as e:
                out.append("G%s=ERR:%s" % (label, type(e).__name__))

        # 2. spawn ring: can_spawn over the 5x5 block around the core anchor
        ring = []
        for dy in (-2, -1, 0, 1, 2):
            for dx in (-2, -1, 0, 1, 2):
                q = Position(p.x + dx, p.y + dy)
                try:
                    ok = ct.can_spawn(q)
                except Exception:
                    ok = None
                ring.append("1" if ok else ("0" if ok is False else "?"))
        out.append("SPAWN5x5=" + "".join(ring))

        try:
            ct.resign("|".join(out))
        except Exception:
            ct.resign()
