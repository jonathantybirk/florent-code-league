"""A4FORT3 -- seal your own Core ring, then run an economy through a hot-swapped gate.

Two measured mechanics, and nothing else:

 1. RING DENIAL (bots/probes/a4ring, arena ringlab)
      ring 0/12 occupied -> 38 board tiles can site a Gunner with a legal shot at our Core
      ring 12/12         -> 0.
    Every Gunner or Sentinel line onto a 2x2 footprint passes through one of the 12 tiles that
    touch it, and a building both blocks the line and absorbs the shot. Twelve Barriers ~= 60 Ti.

 2. FREE HOT SWAP (bots/probes/a4swap)
      cd0=0 can_destroy=True | cd_after_destroy=0 built_same_turn=yes cd_after_build=1 occ=True
    `destroy()` on an allied building costs NO action cooldown, so a sealed ring tile can be turned
    into the conveyor terminal a scoring chain needs (G02) in ONE turn, with zero open frames.

Roles: the first four builders take ring cycle seats 0/3/6/9 and close all twelve tiles before the
opponent's first Gunner lands (measured: it lands on our ring at round 8). Once the opening is done
everyone but the two menders goes mining.
"""

from fcode import Controller, Direction, Environment, EntityType, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
DELTA = {Direction.NORTH: (0, -1), Direction.EAST: (1, 0),
         Direction.SOUTH: (0, 1), Direction.WEST: (-1, 0)}

S_X, S_Y, S_ORD = 0, 1, 2
S_CLAIM0, N_CLAIMS = 4, 6

N_BUILDERS = 7
MENDERS = 4
CYCLE = ((-1, -1), (0, -1), (1, -1), (2, -1), (2, 0), (2, 1),
         (2, 2), (1, 2), (0, 2), (-1, 2), (-1, 1), (-1, 0))
SEATS = (0, 3, 6, 9, 1, 4, 7, 10)
# ring cycle indices that are ORTHOGONALLY adjacent to a footprint tile -- the only ring tiles a
# scoring conveyor may terminate on (G02). The four corners are not.
EDGE_IDX = (1, 2, 4, 5, 7, 8, 10, 11)


def foot_of(a):
    return ((a[0], a[1]), (a[0] + 1, a[1]), (a[0], a[1] + 1), (a[0] + 1, a[1] + 1))


def cycle_of(a, w, h):
    out = []
    for dx, dy in CYCLE:
        t = (a[0] + dx, a[1] + dy)
        out.append(t if (0 <= t[0] < w and 0 <= t[1] < h) else None)
    return out


def pack(t):
    return ((t[0] + 1) << 8) | (t[1] + 1)


def unpack(v):
    if v <= 0:
        return None
    return ((v >> 8) - 1, (v & 0xFF) - 1)


class Player:
    def __init__(self):
        self.spawned = 0
        self.ordinal = None
        self.core = None
        self.cyc = None
        self.rset = frozenset()
        self.fset = frozenset()
        self.home = None
        self.stage = 0
        self.role = None            # "mend" or "econ"
        # economy
        self.phase = "seek"
        self.ore = None
        self.known_ore = set()
        self.walls = set()
        self.blocked = set()
        self.owed = None
        self.owed_final = False
        self.stuck = 0
        self.last = None
        self.nav = None
        self.nav_key = None
        self.nav_n = -1

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

    # ================================================================== CORE
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
            if ct.get_global_resources() < ct.get_builder_bot_cost():
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

    # =============================================================== BUILDER
    def _builder(self, ct):
        pos = ct.get_position()
        if self.ordinal is None:
            try:
                self.ordinal = ct.read_store(S_ORD)
            except Exception:
                self.ordinal = 0
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
        self._observe(ct)
        if self.last is not None and self.last == (pos.x, pos.y):
            self.stuck += 1
        else:
            self.stuck = 0
        self.last = (pos.x, pos.y)

        try:
            can_act = ct.get_action_cooldown() == 0
        except Exception:
            can_act = False

        # the opening always comes first, whatever the role
        if self.home is not None and self.stage < 4:
            if self._evict(ct, pos, can_act):
                return
            if self._opening(ct, pos, can_act):
                return
        if self.role is None:
            self.role = "mend" if (self.ordinal or 0) < MENDERS else "econ"
        if self.role == "mend":
            self._mend(ct, pos, can_act)
        else:
            self._econ(ct, pos, can_act)

    # --------------------------------------------------------------- vision
    def _observe(self, ct):
        try:
            tiles = ct.get_nearby_tiles()
        except Exception:
            return
        for t in tiles:
            key = (t.x, t.y)
            b = None
            try:
                b = ct.get_tile_building_id(t)
            except Exception:
                b = None
            if b is None:
                self.blocked.discard(key)
            else:
                self.blocked.add(key)
            if key in self.walls or key in self.known_ore:
                continue
            try:
                if not ct.is_in_vision(t):
                    continue
                env = ct.get_tile_env(t)
            except Exception:
                continue
            if env == Environment.WALL:
                self.walls.add(key)
            elif env == Environment.ORE_TITANIUM:
                self.known_ore.add(key)

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

    # -------------------------------------------------------------- opening
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

    # ----------------------------------------------------------------- mend
    def _mend(self, ct, pos, can_act):
        if self._evict(ct, pos, can_act):
            return
        if can_act and self._brick_adjacent(ct, pos):
            return
        if can_act and self._heal(ct, pos):
            return
        holes = [t for t in self.cyc if t is not None and self._bldg(ct, t) is None]
        here = (pos.x, pos.y)
        if here in self.rset and holes:
            if self._step_out(ct, pos):
                return
        if holes:
            goal = self._stand_for(ct, pos, holes)
            if goal is not None and self._walk_to(ct, pos, goal):
                return
        if here in self.rset:
            self._step_out(ct, pos)

    def _evict(self, ct, pos, can_act):
        """Shoot ANY enemy building we can reach.

        Two targets matter and they are the same code. An enemy building that has taken a ring tile
        is a hole we can never brick while it stands. An enemy GUNNER parked on the shell tile just
        outside a ring tile is worse: it grinds that Barrier down every three rounds AND it occupies
        the only stand tile a mender could rebuild from, which is exactly how a4fort3 lost hive --
        indices 4 and 5 went empty at r35 and were never put back while five builders stood idle
        with 270 titanium in the bank. A builder's attack is 2 damage for 2 Ti (G13 reversed); 40 HP
        of Gunner is 20 actions, which two menders finish in ten rounds.
        """
        if not can_act:
            return False
        for d in CARD:
            t = pos.add(d)
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

    # -------------------------------------------------------------- economy
    def _econ(self, ct, pos, can_act):
        if self._settle_owed(ct, pos, can_act):
            return
        if self.phase == "belt":
            if self._belt_step(ct, pos, can_act):
                return
        if self.phase == "seek":
            if self.ore is None:
                self.ore = self._pick_ore(ct, pos)
                if self.ore is not None:
                    try:
                        ct.write_store(S_CLAIM0 + (self.ordinal % N_CLAIMS), pack(self.ore))
                    except Exception:
                        pass
            if self.ore is not None:
                if self._try_harvester(ct, pos, can_act):
                    return
                if self._walk_to(ct, pos, self.ore):
                    return
                self.stuck += 1
                if self.stuck > 6:
                    self._abandon()
                return
        self._explore(ct, pos)

    def _abandon(self):
        self.ore = None
        self.phase = "seek"
        self.owed = None
        self.owed_final = False
        self.stuck = 0

    def _pick_ore(self, ct, pos):
        claimed = set()
        for i in range(N_CLAIMS):
            if i == (self.ordinal % N_CLAIMS):
                continue
            try:
                o = unpack(ct.read_store(S_CLAIM0 + i))
            except Exception:
                o = None
            if o is not None:
                claimed.add(o)
        best, best_d = None, None
        for t in self.known_ore:
            if t in claimed or t in self.blocked:
                continue
            d = abs(t[0] - pos.x) + abs(t[1] - pos.y)
            if best_d is None or d < best_d:
                best_d, best = d, t
        return best

    def _try_harvester(self, ct, pos, can_act):
        t = self.ore
        if abs(t[0] - pos.x) + abs(t[1] - pos.y) != 1:
            return False
        if self._bldg(ct, t) is not None:
            self._abandon()
            return False
        if not can_act:
            return True
        try:
            if ct.get_global_resources() < ct.get_harvester_cost() + 12:
                return True
            if ct.can_build_harvester(Position(t[0], t[1])):
                ct.build_harvester(Position(t[0], t[1]))
                self.phase = "belt"
                return True
        except Exception:
            self._abandon()
        return True

    def _gate_dir(self, ct, pos):
        """If an EDGE ring tile is orthogonally adjacent to us, return (tile, dir into the core)."""
        for d in CARD:
            t = (pos.x + DELTA[d][0], pos.y + DELTA[d][1])
            if t not in self.rset:
                continue
            if self.cyc.index(t) not in EDGE_IDX:
                continue
            for d2 in CARD:
                f = (t[0] + DELTA[d2][0], t[1] + DELTA[d2][1])
                if f in self.fset:
                    return t, d, d2
        return None

    def _belt_step(self, ct, pos, can_act):
        g = self._gate_dir(ct, pos)
        if g is not None:
            tile, _tod, into = g
            eid = self._bldg(ct, tile)
            if eid is not None and self._mine(ct, eid):
                try:
                    et = ct.get_entity_type(eid)
                except Exception:
                    et = None
                if et == EntityType.CONVEYOR:
                    # terminal already exists: cap our own tile and go back to mining
                    return self._cap(ct, pos, tile)
                if not can_act:
                    return True
                # HOT SWAP: destroy costs no action cooldown, so the barrier becomes the
                # conveyor terminal in a single turn with the ring never open (a4swap).
                try:
                    if ct.can_destroy(Position(tile[0], tile[1])):
                        ct.destroy(Position(tile[0], tile[1]))
                except Exception:
                    return True
                try:
                    if ct.can_build_conveyor(Position(tile[0], tile[1]), into):
                        ct.build_conveyor(Position(tile[0], tile[1]), into)
                except Exception:
                    return True
                return True
            if eid is None:
                if not can_act:
                    return True
                try:
                    if ct.can_build_conveyor(Position(tile[0], tile[1]), into):
                        ct.build_conveyor(Position(tile[0], tile[1]), into)
                        return True
                except Exception:
                    return True
            return self._cap(ct, pos, tile)
        # keep walking home, owing a belt on every tile we vacate
        target = self._nearest_shell(ct, pos)
        if target is None:
            self._abandon()
            return False
        step = self._step_toward(ct, pos, target)
        if step is None:
            self.stuck += 1
            if self.stuck > 6:
                self._abandon()
            return False
        try:
            ct.move(step)
        except Exception:
            return False
        if (pos.x, pos.y) not in self.known_ore:
            self.owed = ((pos.x, pos.y), step)
            self.owed_final = False
        return True

    def _cap(self, ct, pos, tile):
        """Step aside and owe a conveyor on the tile we vacate, facing the gate."""
        d = None
        for c in CARD:
            if (pos.x + DELTA[c][0], pos.y + DELTA[c][1]) == tile:
                d = c
        if d is None:
            self._abandon()
            return False
        if self._bldg(ct, (pos.x, pos.y)) is not None:
            self._abandon()
            return False
        try:
            if ct.get_move_cooldown() != 0:
                return True
        except Exception:
            return False
        for m in CARD:
            if m == d:
                continue
            n = pos.add(m)
            if (n.x, n.y) in self.fset or (n.x, n.y) in self.rset:
                continue
            try:
                if ct.can_move(m):
                    self.owed = ((pos.x, pos.y), d)
                    self.owed_final = True
                    ct.move(m)
                    return True
            except Exception:
                continue
        return False

    def _settle_owed(self, ct, pos, can_act):
        if self.owed is None:
            return False
        t, facing = self.owed
        if abs(t[0] - pos.x) + abs(t[1] - pos.y) != 1:
            self.owed = None
            self._abandon()
            return False
        if self._bldg(ct, t) is not None:
            self.owed = None
            if self.owed_final:
                self._abandon()
            return False
        if not can_act:
            return True
        try:
            if ct.can_build_conveyor(Position(t[0], t[1]), facing):
                ct.build_conveyor(Position(t[0], t[1]), facing)
                self.owed = None
                if self.owed_final:
                    self._abandon()
                return True
        except Exception:
            self.owed = None
        return False

    def _nearest_shell(self, ct, pos):
        """Nearest tile just OUTSIDE the ring next to an edge ring tile -- where a chain ends."""
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return None
        best, best_d = None, None
        for i in EDGE_IDX:
            t = self.cyc[i]
            if t is None:
                continue
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                s = (t[0] + dx, t[1] + dy)
                if s in self.rset or s in self.fset or s in self.walls:
                    continue
                if not (0 <= s[0] < w and 0 <= s[1] < h):
                    continue
                d = abs(s[0] - pos.x) + abs(s[1] - pos.y)
                if best_d is None or d < best_d:
                    best_d, best = d, s
        return best

    # ------------------------------------------------------------- movement
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
                # An OCCUPIED stand tile is not a stand tile. Accepting one deadlocks the mender:
                # it walks to a tile it can never enter, `can_move` refuses every round, and the
                # hole beside it stays open for the rest of the match.
                if self._bldg(ct, s) is not None or s in self.walls:
                    continue
                d = abs(s[0] - pos.x) + abs(s[1] - pos.y)
                if best_d is None or d < best_d:
                    best_d, best = d, s
        return best

    def _field(self, ct, goal):
        n = len(self.walls) + len(self.blocked)
        if self.nav is not None and self.nav_key == goal and self.nav_n == n:
            return self.nav
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return None
        dist = {goal: 0}
        frontier = [goal]
        step = 0
        while frontier:
            step += 1
            nxt = []
            for x, y in frontier:
                for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if nb in dist or not (0 <= nb[0] < w and 0 <= nb[1] < h):
                        continue
                    if nb in self.walls or nb in self.blocked or nb in self.fset:
                        continue
                    dist[nb] = step
                    nxt.append(nb)
            frontier = nxt
        self.nav, self.nav_key, self.nav_n = dist, goal, n
        return dist

    def _step_toward(self, ct, pos, goal):
        field = self._field(ct, goal)
        here = None if field is None else field.get((pos.x, pos.y))
        best, best_d = None, None
        if field is not None:
            for d in CARD:
                n = pos.add(d)
                nd = field.get((n.x, n.y))
                if nd is None:
                    continue
                if here is not None and nd >= here:
                    continue
                try:
                    if not ct.can_move(d):
                        continue
                except Exception:
                    continue
                if best_d is None or nd < best_d:
                    best_d, best = nd, d
            if best is not None:
                return best
        cur = abs(goal[0] - pos.x) + abs(goal[1] - pos.y)
        for d in CARD:
            n = pos.add(d)
            if abs(goal[0] - n.x) + abs(goal[1] - n.y) >= cur:
                continue
            try:
                if ct.can_move(d):
                    return d
            except Exception:
                continue
        return None

    def _walk_to(self, ct, pos, goal):
        try:
            if ct.get_move_cooldown() != 0:
                return True
        except Exception:
            return False
        if (pos.x, pos.y) == goal:
            return False
        step = self._step_toward(ct, pos, goal)
        if step is None:
            return False
        try:
            ct.move(step)
        except Exception:
            return False
        return True

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

    def _explore(self, ct, pos):
        try:
            if ct.get_move_cooldown() != 0:
                return
        except Exception:
            return
        cx, cy = self.core if self.core else (pos.x, pos.y)
        away = []
        if pos.x >= cx:
            away.append(Direction.EAST)
        else:
            away.append(Direction.WEST)
        if pos.y >= cy:
            away.append(Direction.SOUTH)
        else:
            away.append(Direction.NORTH)
        order = away + [d for d in CARD if d not in away]
        k = (self.ordinal or 0) % len(order)
        for i in range(len(order)):
            d = order[(i + k) % len(order)]
            n = pos.add(d)
            if (n.x, n.y) in self.fset or (n.x, n.y) in self.rset:
                continue
            try:
                if ct.can_move(d):
                    ct.move(d)
                    return
            except Exception:
                continue

    # ================================================================ TURRET
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
