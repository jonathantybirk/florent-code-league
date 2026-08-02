"""DEFENCE Q5 -- a LAUNCHER's PICKUP radius: can it rewind an attacker it is not touching?

G49 established that launcher pickup is team-blind, but only ever measured an ADJACENT bot.
That leaves the whole defensive case open: if a Launcher can only grab a bot standing next to
it, an attacker simply walks around it; if it can grab anything inside its r^2<=26 disc, one
20-Ti Launcher rewinds every approach lane for 0 ammo, forever.

Arena `maps/lab/dopen.map26`, vs noop.  LAUNCHER at (6,6).  A second builder ("walker") paces
east along y=6 from (7,6) out to (18,6), so the launcher sees it at d^2 = 1,4,9,...,144 on
successive rounds and records `can_launch` at each distance.  Then the walker returns and one
real launch is performed to price it (titanium delta, landing tile, cooldown).

The LAUNCHER is the reporter (M07).
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
LAUN = Position(6, 6)
THROW = Position(11, 6)
SPAWNS = (Position(4, 7), Position(4, 6))
CROUTE = [(5, 7), (6, 7)]
WOUT = [(5, 6), (5, 5), (6, 5), (7, 5), (7, 6), (8, 6), (9, 6), (10, 6), (11, 6),
        (12, 6), (13, 6), (14, 6), (15, 6), (16, 6), (17, 6), (18, 6)]
WBACK = [(17, 6), (16, 6), (15, 6), (14, 6), (13, 6), (12, 6), (11, 6), (10, 6),
         (9, 6), (8, 6), (7, 6)]
LAUNCH_AT = 20
REPORT = 45


class Player:
    def __init__(self):
        self.spawned = 0
        self.home = None
        self.route = None
        self.leg = 0
        self.back = False
        self.built = False
        self.seen = {}
        self.launched = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def walk(self, ct, p, route):
        if self.leg < len(route) and (p.x, p.y) == route[self.leg]:
            self.leg += 1
        if self.leg >= len(route):
            return True
        t = route[self.leg]
        d = DIRS.get((t[0] - p.x, t[1] - p.y))
        if d is not None and ct.can_move(d):
            ct.move(d)
        return False

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

        if et == EntityType.BUILDER_BOT:
            p = ct.get_position()
            if self.home is None:
                key = (p.x, p.y)
                if key == (4, 7):
                    self.route = CROUTE
                elif key == (4, 6):
                    self.route = WOUT
                else:
                    return
                self.home = key
            done = self.walk(ct, p, self.route)
            if self.home == (4, 7):
                if done and not self.built:
                    if ct.can_build_launcher(LAUN):
                        ct.build_launcher(LAUN)
                        self.built = True
                return
            if done and not self.back:
                self.back = True
                self.leg = 0
                self.route = WBACK
            return

        if et != EntityType.LAUNCHER:
            return

        for x in range(2, 14):
            for y in range(3, 10):
                t = Position(x, y)
                uid = None
                try:
                    uid = ct.get_tile_builder_bot_id(t)
                except Exception:
                    uid = None
                if uid is None:
                    continue
                q = t.distance_squared(LAUN)
                if q == 0 or q in self.seen:
                    continue
                ok = 0
                try:
                    ok = 1 if ct.can_launch(t, THROW) else 0
                except Exception:
                    ok = 9
                self.seen[q] = ok

        if r >= LAUNCH_AT and self.launched is None:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if self.launched is not None or (dx == 0 and dy == 0):
                        continue
                    src = Position(LAUN.x + dx, LAUN.y + dy)
                    uid = None
                    try:
                        uid = ct.get_tile_builder_bot_id(src)
                    except Exception:
                        uid = None
                    if uid is None or not ct.can_launch(src, THROW):
                        continue
                    t0 = ct.get_global_resources()
                    ct.launch(src, THROW)
                    lid = ct.get_tile_builder_bot_id(THROW)
                    self.launched = "%d,%d->%d,%d d=%d ti %d->%d land=%d cd=%d r=%d" % (
                        src.x, src.y, THROW.x, THROW.y, THROW.x - src.x, t0,
                        ct.get_global_resources(), 1 if lid is not None else 0,
                        ct.get_action_cooldown(), r)

        if r == REPORT:
            ks = sorted(self.seen.keys())
            ct.resign("DPICK d2:ok=%s LAUNCH[%s] lcost=%d"
                      % (["%d:%d" % (k, self.seen[k]) for k in ks],
                         self.launched, ct.get_launcher_cost()))
