"""A4FORT2 -- win the race for the twelve tiles that touch your own Core.

WHAT v1 TAUGHT US (bots/probes/a4fort, telemetry in bots/cand/a4fortd):
    atoll r6  ring=BBUBBUBB....   -- 6 of our Barriers up
    atoll r8  ring=BBUBBUBBb...   gun=2,-1SO      <- lowercase b = an ENEMY building on OUR ring
    atoll r16 ring=BBUBBUBBbbbb   gun=2,-1SO,2,0WE,2,1WE,2,2NO
AutistimusPrime built FOUR Gunners on our own Core ring, at range 1, and ground the Core from
500 to 10. Its planner charges STANDOFF_PENALTY = 6 rounds per tile of standoff, so range 1 is what
it always wants -- and range 1 onto a 2x2 footprint is, by definition, a ring tile.

So the ring is contested ground and the whole game is who occupies it first. Their first Gunner
lands on it at round 8. This build closes all twelve before round 8:

  * the twelve ring tiles form a closed ORTHOGONAL CYCLE, so consecutive tiles are build-adjacent;
  * a builder spawned on cycle index i bricks i-1, then i+1, then steps outward and bricks i --
    three tiles from one body, and four bodies spawned on 0, 3, 6, 9 cover all twelve;
  * the Core spawns them onto those four tiles deliberately instead of in raster order (v1 spawned
    down the west column while the attack came from the east).

Anything that survives that opening is mended: a Gunner needs 3 shots (6 Ti, 3 rounds) to clear a
30 HP Barrier and we put it back for one action and ~5 Ti, so the exchange runs 2:1 our way. Enemy
buildings that DO get onto the ring are chewed with the builder's own 2 damage / 2 Ti attack (G13
reversed), which is the only thing that can evict them.
"""

from fcode import Controller, Direction, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)

S_X, S_Y, S_ORD = 0, 1, 2

N_BUILDERS = 5
SPAWN_RESERVE = 0
# Clockwise closed cycle of the 12 tiles around a 2x2 footprint anchored at (0,0).
# Consecutive entries are ORTHOGONALLY adjacent, which is what makes the "brick my two
# neighbours, step out, brick my own tile" pattern legal (G59).
CYCLE = ((-1, -1), (0, -1), (1, -1), (2, -1), (2, 0), (2, 1),
         (2, 2), (1, 2), (0, 2), (-1, 2), (-1, 1), (-1, 0))
SEATS = (0, 3, 6, 9, 1, 4, 7, 10)


def foot_of(a):
    return ((a[0], a[1]), (a[0] + 1, a[1]), (a[0], a[1] + 1), (a[0] + 1, a[1] + 1))


def cycle_of(a, w, h):
    """The 12 ring tiles in cycle order, with off-map entries replaced by None (G64a)."""
    out = []
    for dx, dy in CYCLE:
        t = (a[0] + dx, a[1] + dy)
        out.append(t if (0 <= t[0] < w and 0 <= t[1] < h) else None)
    return out


class Player:
    def __init__(self):
        self.spawned = 0
        self.seat = 0
        self.core = None
        self.cyc = None
        self.rset = frozenset()
        self.fset = frozenset()
        self.home = None
        self.stage = 0

    def run(self, ct: Controller) -> None:
        try:
            et = ct.get_entity_type()
        except Exception:
            return
        try:
            if et == EntityType.CORE:
                self._core(ct)
            elif et == EntityType.BUILDER_BOT:
                self._builder(ct)
            elif et == EntityType.GUNNER:
                self._gunner(ct)
        except Exception:
            return

    # ------------------------------------------------------------------
    def _core(self, ct):
        p = ct.get_position()
        ct.write_store(S_X, p.x + 1)
        ct.write_store(S_Y, p.y + 1)
        a = (p.x, p.y)
        if self.spawned >= N_BUILDERS:
            return
        try:
            if ct.get_action_cooldown() != 0:
                return
            if ct.get_global_resources() < ct.get_builder_bot_cost() + SPAWN_RESERVE:
                return
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return
        cyc = cycle_of(a, w, h)
        order = [cyc[i] for i in SEATS if cyc[i] is not None]
        order += [t for t in cyc if t is not None and t not in order]
        for t in order:
            tp = Position(t[0], t[1])
            try:
                if ct.can_spawn(tp):
                    ct.spawn_builder(tp)
                    self.spawned += 1
                    ct.write_store(S_ORD, ct.read_store(S_ORD) + 1)
                    return
            except Exception:
                continue

    # ------------------------------------------------------------------
    def _builder(self, ct):
        pos = ct.get_position()
        if self.core is None:
            try:
                x, y = ct.read_store(S_X), ct.read_store(S_Y)
                w, h = ct.get_map_width(), ct.get_map_height()
            except Exception:
                return
            if x <= 0 or y <= 0:
                return
            self.core = (x - 1, y - 1)
            self.cyc = cycle_of(self.core, w, h)
            self.rset = frozenset(t for t in self.cyc if t is not None)
            self.fset = frozenset(foot_of(self.core))
            here = (pos.x, pos.y)
            if here in self.rset:
                self.home = self.cyc.index(here)
        self._act(ct, pos)

    def _bldg(self, ct, t):
        try:
            return ct.get_tile_building_id(Position(t[0], t[1]))
        except Exception:
            return None

    def _mine(self, ct, eid):
        try:
            return ct.get_team(eid) == ct.get_team()
        except Exception:
            return True

    def _act(self, ct, pos):
        try:
            can_act = ct.get_action_cooldown() == 0
        except Exception:
            can_act = False

        # 0. an ENEMY building standing on our own ring is the only thing that can hurt the Core.
        #    A builder's 2 damage / 2 Ti orthogonal attack (G13 reversed) is the one tool that
        #    evicts it -- `destroy` only works on allied buildings.
        if can_act and self._evict(ct, pos):
            return

        # 1. the opening: brick i-1, brick i+1, step out, brick i.
        if self.home is not None and self.stage < 4:
            if self._opening(ct, pos, can_act):
                return

        # 2. mend anything missing, from wherever we are
        if can_act and self._brick_adjacent(ct, pos):
            return
        if can_act and self._heal(ct, pos):
            return

        # 3. reposition toward the nearest hole
        holes = self._holes(ct)
        here = (pos.x, pos.y)
        if here in self.rset and holes:
            if self._step_out(ct, pos):
                return
        if holes:
            goal = self._stand_for(ct, pos, holes)
            if goal is not None and self._step_to(ct, pos, goal):
                return
        if here in self.rset:
            self._step_out(ct, pos)

    def _holes(self, ct):
        out = []
        for t in self.cyc:
            if t is None:
                continue
            if self._bldg(ct, t) is None:
                out.append(t)
        return out

    def _opening(self, ct, pos, can_act):
        i = self.home
        n = len(self.cyc)
        seq = (self.cyc[(i - 1) % n], self.cyc[(i + 1) % n], None, self.cyc[i])
        while self.stage < 4:
            t = seq[self.stage]
            if self.stage == 2:
                if (pos.x, pos.y) not in self.rset:
                    self.stage = 3
                    continue
                if self._step_out(ct, pos):
                    self.stage = 3
                    return True
                self.stage = 3
                continue
            if t is None or self._bldg(ct, t) is not None:
                self.stage += 1
                continue
            if abs(t[0] - pos.x) + abs(t[1] - pos.y) != 1:
                if self.stage == 3:
                    self.stage = 4
                    return False
                self.stage += 1
                continue
            if not can_act:
                return True
            try:
                if ct.can_build_barrier(Position(t[0], t[1])):
                    ct.build_barrier(Position(t[0], t[1]))
                    self.stage += 1
                    return True
            except Exception:
                self.stage += 1
                continue
            return True
        return False

    def _evict(self, ct, pos):
        for d in CARD:
            t = pos.add(d)
            if (t.x, t.y) not in self.rset:
                continue
            eid = self._bldg(ct, (t.x, t.y))
            if eid is None or self._mine(ct, eid):
                continue
            try:
                if ct.can_fire(t):
                    ct.fire(t)
                    return True
            except Exception:
                continue
        return False

    def _brick_adjacent(self, ct, pos):
        try:
            if ct.get_global_resources() < ct.get_barrier_cost():
                return False
        except Exception:
            return False
        for d in CARD:
            t = pos.add(d)
            if (t.x, t.y) not in self.rset:
                continue
            if self._bldg(ct, (t.x, t.y)) is not None:
                continue
            try:
                if ct.can_build_barrier(t):
                    ct.build_barrier(t)
                    return True
            except Exception:
                continue
        return False

    def _heal(self, ct, pos):
        for d in CARD:
            t = pos.add(d)
            try:
                if ct.can_heal(t):
                    ct.heal(t)
                    return True
            except Exception:
                continue
        return False

    def _step_out(self, ct, pos):
        try:
            if ct.get_move_cooldown() != 0:
                return True
        except Exception:
            return False
        for d in CARD:
            n = pos.add(d)
            if (n.x, n.y) in self.rset or (n.x, n.y) in self.fset:
                continue
            try:
                if ct.can_move(d):
                    ct.move(d)
                    return True
            except Exception:
                continue
        return False

    def _stand_for(self, ct, pos, holes):
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return None
        best, best_d = None, None
        for t in holes:
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                s = (t[0] + dx, t[1] + dy)
                if s in self.fset:
                    continue
                if not (0 <= s[0] < w and 0 <= s[1] < h):
                    continue
                if s in self.rset and self._bldg(ct, s) is not None:
                    continue
                d = abs(s[0] - pos.x) + abs(s[1] - pos.y)
                if best_d is None or d < best_d:
                    best_d, best = d, s
        return best

    def _step_to(self, ct, pos, goal):
        try:
            if ct.get_move_cooldown() != 0:
                return True
        except Exception:
            return False
        if (pos.x, pos.y) == goal:
            return False
        best, best_d = None, abs(goal[0] - pos.x) + abs(goal[1] - pos.y)
        for d in CARD:
            n = pos.add(d)
            nd = abs(goal[0] - n.x) + abs(goal[1] - n.y)
            if nd >= best_d:
                continue
            try:
                if not ct.can_move(d):
                    continue
            except Exception:
                continue
            best, best_d = d, nd
        if best is None:
            for d in CARD:
                n = pos.add(d)
                if (n.x, n.y) in self.fset:
                    continue
                try:
                    if ct.can_move(d):
                        best = d
                        break
                except Exception:
                    continue
        if best is None:
            return False
        try:
            ct.move(best)
        except Exception:
            return False
        return True

    # ------------------------------------------------------------------
    def _gunner(self, ct):
        try:
            target = ct.get_gunner_target()
        except Exception:
            return
        if target is None:
            return
        occ = None
        try:
            occ = ct.get_tile_building_id(target)
            if occ is None:
                occ = ct.get_tile_builder_bot_id(target)
        except Exception:
            return
        if occ is None or self._mine(ct, occ):
            return
        try:
            if ct.can_fire(target):
                ct.fire(target)
        except Exception:
            return
