"""gg_wall -- pure defensive probe: brick our own Core ring and nothing else.

HYPOTHESIS (Area 4). Every Gunner firing position that bears on a 2x2 Core footprint at range 1
is EXACTLY one of the twelve ring tiles (footprint tile f minus one of the eight unit deltas,
minus the footprint itself). At range 2 and 3 the ray must PASS THROUGH a ring tile. A Gunner's
shot stops at the first building in the lane. Therefore:

    a building on every one of the twelve ring tiles makes every Gunner position on the map
    either unbuildable (tile occupied) or ballistically blocked (ray absorbed by the barrier).

Cost: twelve Barriers at 3 Ti = 36 Ti and +12 percentage points of global cost scale.
Against a Gunner that is 6 Ti of ammunition per Barrier to re-open one lane, and 3 Ti to us
to close it again.

This probe does NOTHING else -- no economy, no offence -- so the measurement is clean: if the
opponent still kills the Core, the hypothesis is wrong.
"""

from fcode import Controller, Direction, EntityType, Environment, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
CD = ((0, -1), (1, 0), (0, 1), (-1, 0))

S_CX = 0
S_CY = 1
BUILDERS = 3
BRICK_FROM = 4          # let the Core finish spawning onto its own ring first


class Player:
    def __init__(self):
        self.spawned = 0
        self.core = None
        self.walls = set()
        self.ring = None
        self.foot = None
        self.errors = 0

    def run(self, ct: Controller) -> None:
        try:
            etype = ct.get_entity_type()
        except Exception:
            self.errors += 1
            return
        try:
            if etype == EntityType.CORE:
                self._core(ct)
            elif etype == EntityType.BUILDER_BOT:
                self._builder(ct)
        except Exception:
            self.errors += 1

    # -- core ---------------------------------------------------------
    def _core(self, ct):
        pos = ct.get_position()
        ct.write_store(S_CX, pos.x + 1)
        ct.write_store(S_CY, pos.y + 1)
        if self.spawned >= BUILDERS:
            return
        try:
            if ct.get_action_cooldown() != 0:
                return
            if ct.get_global_resources() < ct.get_builder_bot_cost() + 60:
                return
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return
        for dx in range(-1, 3):
            for dy in range(-1, 3):
                t = Position(pos.x + dx, pos.y + dy)
                if not (0 <= t.x < w and 0 <= t.y < h):
                    continue
                try:
                    if ct.can_spawn(t):
                        ct.spawn_builder(t)
                        self.spawned += 1
                        return
                except Exception:
                    continue

    # -- builder ------------------------------------------------------
    def _geom(self, ct):
        if self.core is None:
            try:
                x, y = ct.read_store(S_CX), ct.read_store(S_CY)
            except Exception:
                return False
            if x <= 0 or y <= 0:
                return False
            self.core = (x - 1, y - 1)
        if self.ring is None:
            x0, y0 = self.core
            foot = {(x0, y0), (x0 + 1, y0), (x0, y0 + 1), (x0 + 1, y0 + 1)}
            try:
                w, h = ct.get_map_width(), ct.get_map_height()
            except Exception:
                return False
            ring = []
            for dx in range(-1, 3):
                for dy in range(-1, 3):
                    t = (x0 + dx, y0 + dy)
                    if t in foot or not (0 <= t[0] < w and 0 <= t[1] < h):
                        continue
                    ring.append(t)
            self.foot = foot
            self.ring = tuple(ring)
        return True

    def _see(self, ct):
        try:
            tiles = ct.get_nearby_tiles()
        except Exception:
            return
        for t in tiles:
            key = (t.x, t.y)
            if key in self.walls:
                continue
            try:
                if ct.get_tile_env(t) == Environment.WALL:
                    self.walls.add(key)
            except Exception:
                continue

    def _open_ring(self, ct):
        out = []
        for t in self.ring:
            if t in self.walls:
                continue
            try:
                if ct.get_tile_building_id(Position(t[0], t[1])) is None:
                    out.append(t)
            except Exception:
                continue
        return out

    def _builder(self, ct):
        pos = ct.get_position()
        self._see(ct)
        if not self._geom(ct):
            return
        try:
            rnd = ct.get_current_round()
        except Exception:
            rnd = 0
        if rnd < BRICK_FROM:
            return
        here = (pos.x, pos.y)
        openr = self._open_ring(ct)

        # 1. Build a barrier on any open ring tile we are orthogonally adjacent to, provided we
        #    are not standing ON the ring (a builder inside the shell bricks itself in).
        if openr and here not in self.ring:
            for dx, dy in CD:
                t = (here[0] + dx, here[1] + dy)
                if t not in openr:
                    continue
                if not self._act(ct):
                    return
                try:
                    if ct.can_build_barrier(Position(t[0], t[1])):
                        ct.build_barrier(Position(t[0], t[1]))
                        return
                except Exception:
                    continue

        # 2. Heal a damaged neighbour (a barrier under fire is 4 HP for 1 Ti).
        if self._act(ct):
            for d in CARD:
                n = pos.add(d)
                try:
                    if ct.can_heal(n):
                        ct.heal(n)
                        return
                except Exception:
                    continue

        # 3. Walk to a stand tile beside the most urgent open ring tile.
        if not openr:
            return
        goal = self._pick_stand(ct, openr, here)
        if goal is None or goal == here:
            return
        step = self._step(ct, pos, goal)
        if step is None:
            return
        try:
            if ct.get_move_cooldown() == 0 and ct.can_move(step):
                ct.move(step)
        except Exception:
            return

    def _act(self, ct):
        try:
            return ct.get_action_cooldown() == 0
        except Exception:
            return False

    def _pick_stand(self, ct, openr, here):
        """A tile OUTSIDE the ring orthogonally adjacent to an open ring tile, nearest to us."""
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return None
        best, best_d = None, None
        for t in openr:
            for dx, dy in CD:
                s = (t[0] + dx, t[1] + dy)
                if s in self.ring or s in self.foot or s in self.walls:
                    continue
                if not (0 <= s[0] < w and 0 <= s[1] < h):
                    continue
                try:
                    if s != here and ct.get_tile_building_id(Position(s[0], s[1])) is not None:
                        continue
                except Exception:
                    pass
                d = abs(s[0] - here[0]) + abs(s[1] - here[1])
                if best_d is None or d < best_d or (d == best_d and s < best):
                    best, best_d = s, d
        return best

    def _step(self, ct, pos, goal):
        """BFS over remembered walls; the ring itself is passable only where still open."""
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return None
        src = (goal[0], goal[1])
        dist = {src: 0}
        frontier = [src]
        d = 0
        while frontier:
            d += 1
            nxt = []
            for cx, cy in frontier:
                for dx, dy in CD:
                    n = (cx + dx, cy + dy)
                    if n in dist or not (0 <= n[0] < w and 0 <= n[1] < h):
                        continue
                    if n in self.walls or n in self.foot:
                        continue
                    dist[n] = d
                    nxt.append(n)
            frontier = nxt
        here = dist.get((pos.x, pos.y))
        if here is None:
            return None
        for direction in CARD:
            n = pos.add(direction)
            nd = dist.get((n.x, n.y))
            if nd is not None and nd < here:
                try:
                    if ct.can_move(direction):
                        return direction
                except Exception:
                    continue
        return None
