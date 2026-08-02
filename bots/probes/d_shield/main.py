"""DEFENCE Q7 -- is a BUILDER BODY a wall?  Does an enemy turret kill it, and does it block LOS?

Arena `maps/lab/dopen.map26`, vs noop.  Core A anchor (2,5).
GUNNER at (6,5) facing WEST, ray (5,5)(4,5)(3,5), (3,5) = our own Core footprint.
A second builder walks onto (5,5) -- the first tile of the ray -- and stands there.

Turret APIs are team-blind (G10), so what our own Gunner does to our own builder is exactly
what an enemy Gunner would do.  The GUNNER is the reporter (M07).
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
GUN = Position(6, 5)
SHIELD = Position(5, 5)
CORE = Position(3, 5)
SPAWNS = (Position(4, 7), Position(4, 6))
ROUTES = {(4, 7): [(5, 7), (6, 7), (7, 7), (7, 6), (7, 5), (7, 4), (6, 4)],
          (4, 6): [(5, 6), (5, 5)]}
FIRE_AT = 14


def pt(p):
    if p is None:
        return "-"
    return "%d,%d" % (p.x, p.y)


class Player:
    def __init__(self):
        self.spawned = 0
        self.home = None
        self.route = None
        self.leg = 0
        self.built = False
        self.pre = None
        self.post = None
        self.seen = False
        self.shots = 0
        self.hpseq = []
        self.gone = -1

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if self.spawned < 2:
                p = SPAWNS[self.spawned]
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned += 1
                return
            if r >= 6 and ct.get_global_ammo() < 30 and ct.can_convert_ammo(60):
                ct.convert_ammo(60)
            return

        if et == EntityType.BUILDER_BOT:
            p = ct.get_position()
            if self.home is None:
                key = (p.x, p.y)
                if key not in ROUTES:
                    return
                self.home = key
                self.route = ROUTES[key]
            if self.leg < len(self.route):
                if (p.x, p.y) == self.route[self.leg]:
                    self.leg += 1
                else:
                    t = self.route[self.leg]
                    d = DIRS.get((t[0] - p.x, t[1] - p.y))
                    if d is not None and ct.can_move(d):
                        ct.move(d)
                    return
            if self.home == (4, 7) and not self.built:
                if ct.can_build_gunner(GUN, Direction.WEST):
                    ct.build_gunner(GUN, Direction.WEST)
                    self.built = True
            return

        if et != EntityType.GUNNER:
            return

        uid = ct.get_tile_builder_bot_id(SHIELD)
        if uid is None and not self.seen:
            self.pre = "%s cfcore=%d" % (pt(ct.get_gunner_target()),
                                         1 if ct.can_fire(CORE) else 0)
            return
        if uid is not None and not self.seen:
            self.seen = True
            self.post = "%s cfcore=%d cfsh=%d hp=%d r=%d" % (
                pt(ct.get_gunner_target()), 1 if ct.can_fire(CORE) else 0,
                1 if ct.can_fire(SHIELD) else 0, ct.get_hp(uid), r)
        if r < FIRE_AT:
            return
        if uid is not None:
            if ct.can_fire(SHIELD):
                ct.fire(SHIELD)
                self.shots += 1
                nid = ct.get_tile_builder_bot_id(SHIELD)
                self.hpseq.append(ct.get_hp(nid) if nid is not None else 0)
            return
        if self.gone < 0:
            self.gone = r
            ct.resign("DSHIELD PRE=%s POST=%s shots=%d hp=%s AFTER=%s cfcore=%d r=%d"
                      % (self.pre, self.post, self.shots, self.hpseq,
                         pt(ct.get_gunner_target()),
                         1 if ct.can_fire(CORE) else 0, r))
