"""ADVERSARY: one builder bot with a real BFS pathfinder, walking at our Core.

Used as the `--vs` opponent for the launcher-defence probes. It never resigns, so
the defending probe keeps the one resign_message channel to itself (M07/G29).

  NATT   how many attackers the core spawns
  AVOID  if True the pathfinder treats the 8-tile pickup ring of every enemy
         Launcher it has seen as impassable -- the worst case for a gobble pen.

Vision-limited memory: a tile is only remembered as blocked once the bot has
actually seen it (`is_tile_empty` is False). Builder bots are NOT treated as
obstacles, so attackers path through each other and simply lose the round.
Attackers do not attack; they walk to a goal beside our Core and sit, so the
match always reaches round 1000 and the defender's report survives.
"""

from fcode import Controller, Direction, EntityType, Position

NATT = 1
AVOID = False
GOALS = ((4, 6), (4, 4), (4, 8), (4, 5), (3, 6), (3, 7))
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIRS = (Direction.EAST, Direction.WEST, Direction.SOUTH, Direction.NORTH)


class Player:
    def __init__(self):
        self.spawned = 0
        self.blocked = set()
        self.soft = set()
        self.goal = None
        self.stuck = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            pass

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct)

    def _core(self, ct):
        if self.spawned >= NATT:
            return
        a = ct.get_position()
        for dy in (-1, 0, 1, 2):
            for dx in (-1, 0, 1, 2):
                if 0 <= dx <= 1 and 0 <= dy <= 1:
                    continue
                p = Position(a.x + dx, a.y + dy)
                if p.x < 0 or p.y < 0:
                    continue
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned += 1
                    return

    def _builder(self, ct):
        w = ct.get_map_width()
        h = ct.get_map_height()
        pos = ct.get_position()
        if self.goal is None:
            g = GOALS[ct.get_id() % len(GOALS)]
            self.goal = Position(min(g[0], w - 1), min(g[1], h - 1))
        me = ct.get_team()

        for p in ct.get_nearby_tiles():
            t = (p.x, p.y)
            if ct.is_tile_empty(p):
                self.blocked.discard(t)
            else:
                self.blocked.add(t)
        if AVOID:
            for bid in ct.get_nearby_buildings():
                if ct.get_team(bid) == me:
                    continue
                if ct.get_entity_type(bid) != EntityType.LAUNCHER:
                    continue
                lp = ct.get_position(bid)
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        self.soft.add((lp.x + dx, lp.y + dy))

        if pos == self.goal:
            return
        d = self._bfs(pos, w, h, self.soft)
        if d is None:
            d = self._bfs(pos, w, h, set())
        if d is not None and ct.can_move(d):
            ct.move(d)
            self.stuck = 0
            return
        self.stuck += 1
        for k in range(4):
            alt = DIRS[(self.stuck + k) % 4]
            if ct.can_move(alt):
                ct.move(alt)
                return

    def _bfs(self, pos, w, h, soft):
        start = (pos.x, pos.y)
        goal = (self.goal.x, self.goal.y)
        seen = {start: None}
        q = [start]
        head = 0
        found = False
        while head < len(q):
            cur = q[head]
            head += 1
            if cur == goal:
                found = True
                break
            for dx, dy in STEPS:
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt in seen:
                    continue
                if not (0 <= nxt[0] < w and 0 <= nxt[1] < h):
                    continue
                if nxt != goal and (nxt in self.blocked or nxt in soft):
                    continue
                seen[nxt] = cur
                q.append(nxt)
        if not found:
            return None
        cur = goal
        while seen[cur] is not None and seen[cur] != start:
            cur = seen[cur]
        if seen[cur] is None:
            return None
        dx = cur[0] - start[0]
        dy = cur[1] - start[1]
        for i in range(4):
            if STEPS[i] == (dx, dy):
                return DIRS[i]
        return None
