"""AREA 3b: the FULL attack pattern of Gunner and Sentinel in ALL EIGHT facings.

get_attackable_tiles_from() is callable from a Builder Bot (G34), so this needs no construction.
Arena `openfield` (24x20), builder parked well clear of every edge.
Reports, per direction N,NE,E,SE,S,SW,W,NW: tile count and max d^2, for GUNNER then SENTINEL.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

DIRS = [Direction.NORTH, Direction.NORTHEAST, Direction.EAST, Direction.SOUTHEAST,
        Direction.SOUTH, Direction.SOUTHWEST, Direction.WEST, Direction.NORTHWEST]
HOME = Position(11, 9)


class Player:
    def __init__(self):
        self.done = False
        self.spawned = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("GGP|TOP:" + type(exc).__name__ + ":" + str(exc)[:60])
            except Exception:
                pass

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
            d = pos.cardinal_direction_to(HOME)
            if ct.can_move(d):
                ct.move(d)
            return
        self.done = True
        out = []
        for label, ty in (("G", EntityType.GUNNER), ("S", EntityType.SENTINEL),
                          ("L", EntityType.LAUNCHER)):
            row = []
            for d in DIRS:
                try:
                    ts = ct.get_attackable_tiles_from(pos, d, ty)
                    md = max((t.x - pos.x) ** 2 + (t.y - pos.y) ** 2 for t in ts) if ts else -1
                    row.append("%d/%d" % (len(ts), md))
                except Exception as exc:
                    row.append("!" + type(exc).__name__[:4])
            out.append(label + ":" + ",".join(row))
        ct.resign("GGP|" + "|".join(out))
