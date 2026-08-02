"""DEFENCE Q1/Q5 -- a SENTINEL's real damage rate against a Core, measured not assumed.

Arena `maps/lab/dopen.map26`, vs noop.  Core A anchor (2,5).  A builder walks to (7,6) and
builds a SENTINEL at (7,5) facing WEST; r^2<=32 gives a 5-tile line (6,5)(5,5)(4,5)(3,5)(2,5),
and (3,5)/(2,5) are our own Core footprint (turret APIs are team-blind, G10).

`SENTINEL_FIRE_COOLDOWN = 3` and `SENTINEL_DAMAGE = 18`, but "cooldown 3" could mean a shot
every 3rd or every 4th round -- a 33% difference in sustained damage.  The CORE is the
reporter: it times its own HP drops.
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
ROUTE = [(5, 7), (6, 7), (7, 7), (7, 6)]
SENT = Position(7, 5)
TARGET = Position(3, 5)
REPORT = 70


class Player:
    def __init__(self):
        self.spawned = False
        self.leg = 0
        self.built = False
        self.hp = None
        self.first = -1
        self.last = -1
        self.hits = 0
        self.tot = 0
        self.dset = []
        self.gaps = []

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            hp = ct.get_hp()
            if self.hp is None:
                self.hp = hp
            elif hp != self.hp:
                if self.first < 0:
                    self.first = r
                else:
                    self.gaps.append(r - self.last)
                self.last = r
                self.hits += 1
                self.tot += self.hp - hp
                if (self.hp - hp) not in self.dset:
                    self.dset.append(self.hp - hp)
                self.hp = hp
            if not self.spawned:
                if ct.can_spawn(Position(4, 7)):
                    ct.spawn_builder(Position(4, 7))
                    self.spawned = True
                return
            if r >= 2 and ct.get_global_ammo() < 100 and ct.can_convert_ammo(200):
                ct.convert_ammo(200)
                return
            if r == REPORT:
                gs = []
                for g in self.gaps:
                    if g not in gs:
                        gs.append(g)
                ct.resign("DSENT first=%d last=%d hits=%d tot=%d hp=%d dmgset=%s gapset=%s "
                          "ammo=%d ti=%d"
                          % (self.first, self.last, self.hits, self.tot, self.hp,
                             sorted(self.dset), sorted(gs), ct.get_global_ammo(),
                             ct.get_global_resources()))
            return

        if et == EntityType.BUILDER_BOT:
            if self.built:
                return
            p = ct.get_position()
            if self.leg < len(ROUTE):
                if (p.x, p.y) == ROUTE[self.leg]:
                    self.leg += 1
                    return
                t = ROUTE[self.leg]
                d = DIRS.get((t[0] - p.x, t[1] - p.y))
                if d is not None and ct.can_move(d):
                    ct.move(d)
                return
            if ct.can_build_sentinel(SENT, Direction.WEST):
                ct.build_sentinel(SENT, Direction.WEST)
                self.built = True
            return

        if et == EntityType.SENTINEL:
            if ct.can_fire(TARGET):
                ct.fire(TARGET)
            return
