"""DEFENCE Q4/Q6/Q8 -- REBUILDING a wall versus HEALING it, priced per round.

`d_heal` showed three menders (+12 HP/round, 3 Ti/round) pin a barrier at full HP against one
Gunner forever.  The cheaper-looking alternative is to let the wall die and replace it: a
barrier is 3 Ti and absorbs exactly three Gunner shots (d_los), so replacement costs 1 Ti/round
and ONE builder instead of 3 Ti/round and three builders.  The catch is the gap: on the round
the wall falls, the Gunner may reach the thing behind it before the builder re-plugs the hole.

Arena `maps/lab/dopen.map26`, vs noop.  Core A anchor (2,5).  GUNNER at (6,5) facing WEST, ray
(5,5)(4,5)(3,5); the barrier sits at (5,5) and OUR OWN CORE is the thing behind it at (3,5).
One builder at (5,6) -- outside the ray -- replants the barrier whenever the tile is empty.
Gunner fires every round from r30 to r230.  The CORE reports its own HP, so leakage through the
wall is measured directly rather than argued about.
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
GUN = Position(6, 5)
BARR = Position(5, 5)
SPAWNS = (Position(4, 7), Position(4, 6))
ROUTES = {(4, 7): [(5, 7), (6, 7), (7, 7), (7, 6), (7, 5), (7, 4), (6, 4)],
          (4, 6): [(5, 6)]}
RACE0, RACE1, REPORT = 30, 230, 235


class Player:
    def __init__(self):
        self.spawned = 0
        self.home = None
        self.route = None
        self.leg = 0
        self.st = 0
        self.rebuilds = 0
        self.hp = None
        self.hits = 0
        self.tot = 0
        self.ti0 = 0
        self.shots = 0

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
                self.hits += 1
                self.tot += self.hp - hp
                self.hp = hp
            if self.spawned < 2:
                p = SPAWNS[self.spawned]
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned += 1
                return
            if ct.get_global_ammo() < 60 and ct.can_convert_ammo(220):
                ct.convert_ammo(220)
                return
            if r == RACE0:
                self.ti0 = ct.get_global_resources()
            if r == REPORT:
                ct.resign("DREBUILD rounds=%d corehits=%d coredmg=%d hp=%d/500 "
                          "rebuilds=%d ti r30=%d r235=%d ammo=%d"
                          % (RACE1 - RACE0 + 1, self.hits, self.tot, self.hp,
                             ct.read_store(0), self.ti0,
                             ct.get_global_resources(), ct.get_global_ammo()))
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
                if self.leg < len(self.route):
                    t = self.route[self.leg]
                    d = DIRS.get((t[0] - p.x, t[1] - p.y))
                    if d is not None and ct.can_move(d):
                        ct.move(d)
                    return
            if self.home == (4, 7):
                if self.st == 0 and ct.can_build_gunner(GUN, Direction.WEST):
                    ct.build_gunner(GUN, Direction.WEST)
                    self.st = 1
                return
            if ct.get_tile_building_id(BARR) is None and ct.can_build_barrier(BARR):
                ct.build_barrier(BARR)
                self.rebuilds += 1
            ct.write_store(0, self.rebuilds)
            return

        if et != EntityType.GUNNER:
            return
        if RACE0 <= r <= RACE1:
            tgt = ct.get_gunner_target()
            if tgt is not None and ct.can_fire(tgt):
                ct.fire(tgt)
                self.shots += 1
