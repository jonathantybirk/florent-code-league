"""DEFENCE Q8 -- can builders out-heal a Gunner on a barrier, and does healing STACK per round?

Arena `maps/lab/dopen.map26`, vs noop.  Core A anchor (2,5).
A GUNNER at (6,5) facing WEST has ray (5,5)(4,5)(3,5).  A BARRIER sits at (5,5), the first
tile of that ray, so the gunner grinds the barrier and never reaches the Core (see d_los).
Three builders sit on (5,4), (5,6) and (4,5) -- all orthogonally adjacent to the barrier;
(5,4) and (5,6) are OUTSIDE the ray, i.e. menders are safe while the wall tanks.

Routes are hard-coded and pairwise disjoint: greedy stepping deadlocks here, because a
mender parked on (5,6) blocks the only strictly-improving step out of (6,6).

Schedule
  r<20        setup: build gunner, build barrier, take seats
  r20,r21     gunner fires only        -> barrier 30 -> 20 -> 10
  r23         menders heal only        -> proves whether 3 heals stack in ONE round (+12)
  r30..r130   gunner fires AND all three heal every round -- the sustained race
  r135        gunner resigns with the trace

The GUNNER is the reporter (M07); menders relay their heal counts through store slots 0/1/2.
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
GUN = Position(6, 5)
BARR = Position(5, 5)
SPAWNS = (Position(4, 7), Position(4, 6), Position(4, 5))
ROUTES = {(4, 7): [(5, 7), (6, 7), (7, 7), (7, 6), (7, 5), (7, 4), (6, 4)],
          (4, 6): [(5, 6)],
          (4, 5): []}
SLOTS = {(4, 7): 0, (4, 6): 1, (4, 5): 2}
CSEAT = Position(5, 4)
R_FIRE1, R_FIRE2, R_HEAL1 = 20, 21, 23
RACE0, RACE1, REPORT = 30, 130, 135


class Player:
    def __init__(self):
        self.spawned = 0
        self.home = None
        self.route = None
        self.slot = 0
        self.leg = 0
        self.st = 0
        self.heals = 0
        self.hp = {}
        self.hpmin = 99
        self.died = -1
        self.shots = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def goto(self, ct, p, t):
        d = DIRS.get((t[0] - p.x, t[1] - p.y))
        if d is not None and ct.can_move(d):
            ct.move(d)
            return True
        return False

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if self.spawned < 3:
                p = SPAWNS[self.spawned]
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned += 1
                return
            if r >= 8 and ct.get_global_ammo() < 100 and ct.can_convert_ammo(230):
                ct.convert_ammo(230)
            return

        if et == EntityType.BUILDER_BOT:
            p = ct.get_position()
            if self.home is None:
                key = (p.x, p.y)
                if key not in ROUTES:
                    return
                self.home = key
                self.route = ROUTES[key]
                self.slot = SLOTS[key]
            if self.leg < len(self.route):
                if (p.x, p.y) == self.route[self.leg]:
                    self.leg += 1
                else:
                    self.goto(ct, p, self.route[self.leg])
                    return
            if self.home == (4, 7):
                if self.st == 0:
                    if ct.can_build_gunner(GUN, Direction.WEST):
                        ct.build_gunner(GUN, Direction.WEST)
                        self.st = 1
                    return
                if self.st == 1:
                    if p == CSEAT:
                        self.st = 2
                    else:
                        self.goto(ct, p, (CSEAT.x, CSEAT.y))
                        return
                if self.st == 2:
                    if ct.can_build_barrier(BARR):
                        ct.build_barrier(BARR)
                        self.st = 3
                        ct.write_store(3, r)
                    return
            if r == R_HEAL1 or (RACE0 <= r <= RACE1):
                if ct.can_heal(BARR):
                    ct.heal(BARR)
                    self.heals += 1
            ct.write_store(self.slot, self.heals)
            return

        if et != EntityType.GUNNER:
            return

        bid = ct.get_tile_building_id(BARR)
        hp = ct.get_hp(bid) if bid is not None else 0
        if r in (19, 22, 24, 29):
            self.hp[r] = hp
        if RACE0 <= r <= RACE1:
            if hp < self.hpmin:
                self.hpmin = hp
            if hp == 0 and self.died < 0:
                self.died = r
            if r % 40 == 0:
                self.hp[r] = hp
        if r in (R_FIRE1, R_FIRE2) or (RACE0 <= r <= RACE1):
            if bid is not None and ct.can_fire(BARR):
                ct.fire(BARR)
                self.shots += 1
        if r == REPORT:
            ks = sorted(self.hp.keys())
            ct.resign("DHEAL hp=%s shots=%d heals=%d/%d/%d hpmin=%d died=%d ti=%d ammo=%d bR=%d"
                      % (["%d:%d" % (k, self.hp[k]) for k in ks], self.shots,
                         ct.read_store(0), ct.read_store(1), ct.read_store(2),
                         self.hpmin, self.died, ct.get_global_resources(),
                         ct.get_global_ammo(), ct.read_store(3)))
