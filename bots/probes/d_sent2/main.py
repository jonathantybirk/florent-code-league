"""DEFENCE Q3 -- do SENTINELS shoot OVER a barrier?

`d_ring` sealed all twelve Core-ring tiles with barriers and the count of tiles from which a
GUNNER could legally hit the Core fell 37 -> 12 (the ring tiles themselves, now unbuildable),
but the SENTINEL count did not move at all: 64 -> 64.  Either sentinel lines ignore blockers,
or `can_fire_from` simply does not run the blocking check for sentinels.  A wall that stops
gunners and not sentinels is a completely different defensive proposition, so measure it.

Arena `maps/lab/dopen.map26`, vs noop.  SENTINEL at (7,5) facing WEST -- line (6,5)(5,5)(4,5)
(3,5)(2,5), with (3,5)/(2,5) our own Core footprint.  A BARRIER is planted at (5,5), squarely
between the sentinel and the Core.  The SENTINEL is the reporter: it records `can_fire` on the
Core behind the wall and on the wall itself, fires at whichever is legal, and watches both HP
pools so we know which one actually takes the damage.
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
ROUTE = [(5, 7), (6, 7), (7, 7), (7, 6)]
ROUTE2 = [(6, 6), (5, 6)]
SENT = Position(7, 5)
BARR = Position(5, 5)
CORE = Position(3, 5)
REPORT = 40


class Player:
    def __init__(self):
        self.spawned = False
        self.leg = 0
        self.leg2 = 0
        self.built = False
        self.built2 = False
        self.note = None
        self.shots = 0
        self.chp = []
        self.bhp = []

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def walk(self, ct, p, route, leg):
        if leg < len(route) and (p.x, p.y) == route[leg]:
            leg += 1
        if leg >= len(route):
            return leg, True
        t = route[leg]
        d = DIRS.get((t[0] - p.x, t[1] - p.y))
        if d is not None and ct.can_move(d):
            ct.move(d)
        return leg, False

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if not self.spawned:
                if ct.can_spawn(Position(4, 7)):
                    ct.spawn_builder(Position(4, 7))
                    self.spawned = True
                return
            if ct.get_global_ammo() < 40 and ct.can_convert_ammo(120):
                ct.convert_ammo(120)
            return

        if et == EntityType.BUILDER_BOT:
            p = ct.get_position()
            if not self.built:
                self.leg, done = self.walk(ct, p, ROUTE, self.leg)
                if done and ct.can_build_sentinel(SENT, Direction.WEST):
                    ct.build_sentinel(SENT, Direction.WEST)
                    self.built = True
                return
            if not self.built2:
                self.leg2, done = self.walk(ct, p, ROUTE2, self.leg2)
                if done and ct.can_build_barrier(BARR):
                    ct.build_barrier(BARR)
                    self.built2 = True
                return
            if ct.can_move(Direction.SOUTH):
                ct.move(Direction.SOUTH)
            return

        if et != EntityType.SENTINEL:
            return

        bid = ct.get_tile_building_id(BARR)
        cid = ct.get_tile_building_id(CORE)
        if bid is None:
            return
        if self.note is None:
            ts = ct.get_attackable_tiles()
            self.note = "r%d tiles=%d cfCORE=%d cfBARR=%d" % (
                r, len(ts), 1 if ct.can_fire(CORE) else 0,
                1 if ct.can_fire(BARR) else 0)
        if ct.can_fire(CORE):
            ct.fire(CORE)
            self.shots += 1
        elif ct.can_fire(BARR):
            ct.fire(BARR)
            self.shots += 1
        nb = ct.get_tile_building_id(BARR)
        self.bhp.append(ct.get_hp(nb) if nb is not None else 0)
        self.chp.append(ct.get_hp(cid) if cid is not None else 0)
        if r == REPORT:
            ct.resign("DSENT2 %s shots=%d barrHP=%s coreHP=%s"
                      % (self.note, self.shots, self.bhp[-6:], self.chp[-6:]))
