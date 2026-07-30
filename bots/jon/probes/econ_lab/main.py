"""Parameterised opening-economy bot used to measure how many builders pay off.

Only engine-verified mechanics are relied on (see analysis/econ/FINDINGS.md):
  * build and move in the same round; build target within Chebyshev 1
  * builders move 8-connected, 1 tile/round
  * conveyors may be built on the builder's own tile -> 1 conveyor laid per round
  * build the harvester FIRST, then lay the line back; the stack chases the bot
  * one conveyor line carries at most 10 Ti/round = 4 harvesters, so lines are
    kept disjoint by default rather than merged into a shared trunk

Knobs (env):
  EL_BUILDERS  max builder bots            EL_REUSE      1 = allow joining a trunk
  EL_ORACLE    file of "x y" ore tiles     EL_SPAWN_GAP  rounds between spawns
  EL_TRACE / EL_DEBUG  logging

Store layout: 0 = builder ticket counter, 1..15 = ore claims packed as 1+x*32+y.
"""
import os
import sys
from collections import deque

from fcode import Controller, Direction, EntityType, Environment, GameError, Position

NB = int(os.environ.get("EL_BUILDERS", 2))
SPAWN_GAP = int(os.environ.get("EL_SPAWN_GAP", 1))
REUSE = int(os.environ.get("EL_REUSE", 0))
ORACLE = os.environ.get("EL_ORACLE", "")
DEBUG = int(os.environ.get("EL_DEBUG", 0))
TRACE = int(os.environ.get("EL_TRACE", 0))

CLAIM_SLOTS = range(1, 16)
D8 = [Direction.NORTH, Direction.NORTHEAST, Direction.EAST, Direction.SOUTHEAST,
      Direction.SOUTH, Direction.SOUTHWEST, Direction.WEST, Direction.NORTHWEST]
D4V = [(0, -1), (1, 0), (0, 1), (-1, 0)]
FACE = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
WALKABLE = (EntityType.CONVEYOR, EntityType.SPLITTER)


def log(*a):
    if DEBUG:
        print(*a, file=sys.stderr, flush=True)


def pack(p):
    return 1 + p[0] * 32 + p[1]


def unpack(v):
    return ((v - 1) // 32, (v - 1) % 32)


class Player:
    def __init__(self):
        self.idx = None
        self.n_spawned = 0
        self.last_spawn = -99
        self.W = self.H = 0
        self.walls = set()
        self.ore = set()
        self.solid = set()          # tiles carrying a non-walkable building
        self.conveyors = {}
        self.core = None
        self.foot = set()
        self.task = None
        self.route = None
        self.li = 0
        self.phase = "scout"
        self.probed = set()

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except GameError:
            pass                    # an escaping GameError destroys the unit

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)

    # ---------------- core ----------------
    def _core(self, ct):
        r = ct.get_current_round()
        if TRACE:
            print(f"T {r} res={ct.get_global_resources()} "
                  f"scale={ct.get_scale_percent():.2f} units={ct.get_unit_count()}",
                  file=sys.stderr, flush=True)
        if self.n_spawned >= NB or r - self.last_spawn < SPAWN_GAP:
            return
        if ct.get_global_resources() < ct.get_builder_bot_cost():
            return
        for p in ct.get_nearby_tiles(2):
            if ct.can_spawn(p):
                ct.spawn_builder(p)
                self.n_spawned += 1
                self.last_spawn = r
                return

    # ---------------- builder ----------------
    def _builder(self, ct):
        if self.idx is None:
            self.idx = ct.read_store(0)
            ct.write_store(0, self.idx + 1)
            self.W, self.H = ct.get_map_width(), ct.get_map_height()
            if ORACLE:
                for ln in open(ORACLE):
                    x, y = ln.split()
                    self.ore.add((int(x), int(y)))
        self._sense(ct)
        if self.core is None:
            return
        if self.phase == "scout":
            self._pick(ct)
        if self.phase == "goto":
            self._goto(ct)
        elif self.phase == "lay":
            self._lay(ct)
        elif self.phase == "scout":
            self._explore(ct)

    def _sense(self, ct):
        for t in ct.get_nearby_tiles():
            k = (t.x, t.y)
            e = ct.get_tile_env(t)
            if e == Environment.WALL:
                self.walls.add(k)
                continue
            if e == Environment.ORE_TITANIUM:
                self.ore.add(k)
            bid = ct.get_tile_building_id(t)
            if bid is None:
                self.conveyors.pop(k, None)
                self.solid.discard(k)
                continue
            bt = ct.get_entity_type(bid)
            mine = ct.get_team(bid) == ct.get_team()
            if bt == EntityType.CORE:
                if mine and self.core is None:
                    self.core = tuple(ct.get_position(bid))
                self.solid.add(k)
            elif bt in WALKABLE:
                self.solid.discard(k)
                if mine:
                    self.conveyors[k] = ct.get_direction(bid)
            else:
                self.solid.add(k)
        if self.core and not self.foot:
            self.foot = {(self.core[0] + dx, self.core[1] + dy)
                         for dx in (0, 1) for dy in (0, 1)}

    # ---------------- task selection ----------------
    def _claims(self, ct):
        return {unpack(v) for v in (ct.read_store(s) for s in CLAIM_SLOTS) if v}

    def _pick(self, ct):
        taken = self._claims(ct) | (self.ore & self.solid)
        free = [o for o in self.ore if o not in taken]
        if not free:
            return
        me = tuple(ct.get_position())
        free.sort(key=lambda o: max(abs(o[0] - me[0]), abs(o[1] - me[1])))
        for o in free[:8]:
            route = self._route(o)
            if route is None:
                continue
            for s in CLAIM_SLOTS:
                if ct.read_store(s) == 0:
                    ct.write_store(s, pack(o))
                    self.task, self.route, self.li = o, route, 0
                    self.phase = "goto"
                    log(f"[{self.idx}] r={ct.get_current_round()} claim {o} "
                        f"line={len(route)}")
                    return
            return

    # ---------------- conveyor routing ----------------
    def _route(self, ore):
        """4-connected route ore -> core. Returns [(tile, facing), ...] or None."""
        blocked = self.walls | self.foot | (self.ore - {ore}) | self.solid
        prev, q = {ore: None}, deque([ore])
        goal = None
        while q and goal is None:
            c = q.popleft()
            for dx, dy in D4V:
                n = (c[0] + dx, c[1] + dy)
                if n in prev or not (0 <= n[0] < self.W and 0 <= n[1] < self.H):
                    continue
                if n in self.foot:
                    prev[n] = c
                    goal = n
                    break
                if n in blocked:
                    continue
                if n in self.conveyors:
                    # joining a trunk shares its 10 Ti/round cap, so only do it
                    # when asked, and never head-on into its output
                    if REUSE and self.conveyors[n].delta() != (-dx, -dy):
                        prev[n] = c
                        goal = n
                        break
                    continue
                prev[n] = c
                q.append(n)
        if goal is None:
            return None
        path, c = [], goal
        while c is not None:
            path.append(c)
            c = prev[c]
        path.reverse()                                    # ore ... goal
        tiles = path[1:-1]
        out = []
        for i, t in enumerate(tiles):
            nxt = tiles[i + 1] if i + 1 < len(tiles) else path[-1]
            out.append((t, FACE[(nxt[0] - t[0], nxt[1] - t[1])]))
        return out

    # ---------------- execution ----------------
    def _goto(self, ct):
        me = ct.get_position()
        tgt = Position(*self.task)
        if 0 < me.distance_squared(tgt) <= 2:
            if ct.can_build_harvester(tgt):
                ct.build_harvester(tgt)
                self.solid.add(self.task)
                self.route = self._route(self.task) or []
                self.phase, self.li = "lay", 0
                if not self.route:
                    self._done(ct)
                return
            if ct.get_tile_building_id(tgt) is not None:
                self.solid.add(self.task)
                self._done(ct)
                return
            return                                        # cannot afford yet: wait
        self._step(ct, me, tgt, exact=False)

    def _lay(self, ct):
        if self.li >= len(self.route):
            self._done(ct)
            return
        me = ct.get_position()
        tile, face = self.route[self.li]
        tp = Position(*tile)
        if me == tp:
            if ct.can_build_conveyor(tp, face):
                ct.build_conveyor(tp, face)
                self.conveyors[tile] = face
            elif ct.get_tile_building_id(tp) is None:
                return                                    # cannot afford yet: wait
            self.li += 1
            if self.li < len(self.route):
                self._step(ct, me, Position(*self.route[self.li][0]), exact=True)
            else:
                self._done(ct)
            return
        self._step(ct, me, tp, exact=True)

    def _done(self, ct):
        if self.task:
            for s in CLAIM_SLOTS:
                if ct.read_store(s) == pack(self.task):
                    ct.write_store(s, 0)                  # free the slot for reuse
                    break
        self.task, self.route, self.li, self.phase = None, None, 0, "scout"

    # ---------------- movement ----------------
    def _step(self, ct, src, dest, exact):
        nxt = self._bfs((src.x, src.y), (dest.x, dest.y), exact)
        if nxt:
            for d in D8:
                if src.add(d) == Position(*nxt) and ct.can_move(d):
                    ct.move(d)
                    return
        best, bd = None, max(abs(src.x - dest.x), abs(src.y - dest.y))
        for d in D8:
            n = src.add(d)
            if not ct.can_move(d):
                continue
            s = max(abs(n.x - dest.x), abs(n.y - dest.y))
            if s < bd:
                best, bd = d, s
        if best:
            ct.move(best)

    def _bfs(self, s, dest, exact):
        goal = {dest} if exact else \
            {(dest[0] + d.delta()[0], dest[1] + d.delta()[1]) for d in D8}
        if s in goal:
            return None
        blocked = self.walls | self.foot | self.solid
        prev, q = {s: None}, deque([s])
        found = None
        while q:
            c = q.popleft()
            if c in goal:
                found = c
                break
            for d in D8:
                dx, dy = d.delta()
                n = (c[0] + dx, c[1] + dy)
                if n in prev or not (0 <= n[0] < self.W and 0 <= n[1] < self.H):
                    continue
                if n in blocked:
                    continue
                prev[n] = c
                q.append(n)
        if found is None:
            return None
        c = found
        while prev[c] != s:
            c = prev[c]
        return c

    # ---------------- exploration ----------------
    def _explore(self, ct):
        me = tuple(ct.get_position())
        step = 4
        pts = [(px, py)
               for py in range(1, self.H, step) for px in range(1, self.W, step)
               if (px, py) not in self.probed and (px, py) not in self.walls
               and (NB <= 1 or ((px // step) + (py // step)) % NB == self.idx % NB)]
        if not pts:
            self.probed.clear()
            return
        tgt = min(pts, key=lambda p: max(abs(p[0] - me[0]), abs(p[1] - me[1])))
        if max(abs(tgt[0] - me[0]), abs(tgt[1] - me[1])) <= 2:
            self.probed.add(tgt)
        self._step(ct, ct.get_position(), Position(*tgt), exact=False)
