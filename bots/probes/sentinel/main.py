"""Probe G15 on 2.3.3: the Sentinel's attack pattern.

G15 (2.2.0) says a Sentinel fires a 3-row band of 17 tiles, not a single-tile line, and has no
get_sentinel_target(). The 2.3.3 docs say the Sentinel fires a "single-tile-wide straight facing
line ... same width as Gunner, but longer and unblockable" with attack r^2=32.

Arena `openfield`: Sentinel at (8,9) facing EAST. Reports the raw attack pattern shape, and the
Gunner pattern from the same square for comparison.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(7, 9)
SENT = Position(8, 9)


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:24]


def shape(tiles, origin):
    dys = sorted(set(t.y - origin.y for t in tiles))
    dxs = sorted(set(t.x - origin.x for t in tiles))
    md2 = max((t.x - origin.x) ** 2 + (t.y - origin.y) ** 2 for t in tiles) if tiles else -1
    return "n=%d dy=%s dxrange=%d..%d maxd2=%d" % (
        len(tiles), dys, dxs[0], dxs[-1], md2)


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.built = False
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
                self.spawned = True
            return
        if et == EntityType.BUILDER_BOT:
            pos = ct.get_position()
            if self.built:
                return
            if pos != HOME:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                return
            if ct.can_build_sentinel(SENT, Direction.EAST):
                ct.build_sentinel(SENT, Direction.EAST)
                self.built = True
            return
        if et != EntityType.SENTINEL or self.done:
            return
        self.done = True
        me = ct.get_position()
        self.n.append("SENT " + shape(ct.get_attackable_tiles(), me))
        self.n.append("GUNfrom " + shape(
            ct.get_attackable_tiles_from(me, Direction.EAST, EntityType.GUNNER), me))
        try:
            t = ct.get_gunner_target()
            self.n.append("gunner_target_on_sentinel=%s" % (t,))
        except Exception as exc:
            self.n.append("gunner_target_on_sentinel " + e(exc))
        ct.resign(" | ".join(self.n[:6]))
