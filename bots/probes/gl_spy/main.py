"""LAUNCHER Q2/Q5, VICTIM SIDE: an attacker that reports what being thrown feels like.

Same pathfinder as gl_atk1 (one builder, BFS, no ring-avoidance) but this one is
the reporting side: it resigns at round REPORT with its own trace, so run it as
the probe and the launcher bot as `--vs`:

    python tools/runprobe.py gl_spy --map lab/glopen --vs gl_rew
    python tools/runprobe.py gl_spy --map lab/glchoke --vs gl_rewc
    python tools/runprobe.py gl_spy --map lab/glopen --vs gl_pen3

It detects a throw as any between-round position change with Chebyshev distance
> 1, and records the displacement distribution, how many rounds it had no legal
move at all (the true "inescapable" test), and where it spent its time.
"""

from fcode import Controller, Direction, EntityType, Position

GOAL_W = Position(4, 6)
GOAL_E = Position(21, 6)
REPORT = 400
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIRS = (Direction.EAST, Direction.WEST, Direction.SOUTH, Direction.NORTH)


class Player:
    def __init__(self):
        self.spawned = 0
        self.blocked = set()
        self.goal = None
        self.stuck = 0
        self.prev = None
        self.thrown = 0
        self.tdx = {}
        self.td2max = 0
        self.tdsum = 0
        self.minx = 99
        self.maxx = -1
        self.nomove = 0
        self.nomoverun = 0
        self.nomovemax = 0
        self.walked = 0
        self.here = {}
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("gl_spy TOP %s:%s" % (type(exc).__name__, str(exc)[:40]))
            except Exception:
                pass

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if self.spawned < 1:
                a = ct.get_position()
                for dy in (-1, 0, 1, 2):
                    for dx in (-1, 0, 1, 2):
                        if 0 <= dx <= 1 and 0 <= dy <= 1:
                            continue
                        p = Position(a.x + dx, a.y + dy)
                        if p.x >= 0 and p.y >= 0 and ct.can_spawn(p):
                            ct.spawn_builder(p)
                            self.spawned = 1
                            return
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct, ct.get_current_round())

    def _builder(self, ct, r):
        w = ct.get_map_width()
        h = ct.get_map_height()
        pos = ct.get_position()
        if self.goal is None:
            self.goal = GOAL_E if pos.x < w // 2 else GOAL_W

        # --- trace ---
        if self.prev is not None:
            dx = pos.x - self.prev.x
            dy = pos.y - self.prev.y
            if max(abs(dx), abs(dy)) > 1:
                self.thrown += 1
                self.tdx[dx] = self.tdx.get(dx, 0) + 1
                d2 = dx * dx + dy * dy
                self.td2max = max(self.td2max, d2)
                self.tdsum += abs(dx) + abs(dy)
            elif dx or dy:
                self.walked += 1
        self.prev = pos
        self.minx = min(self.minx, pos.x)
        self.maxx = max(self.maxx, pos.x)
        key = (pos.x // 4) * 4
        self.here[key] = self.here.get(key, 0) + 1

        free = False
        for d in DIRS:
            if ct.can_move(d):
                free = True
                break
        if not free:
            self.nomove += 1
            self.nomoverun += 1
            self.nomovemax = max(self.nomovemax, self.nomoverun)
        else:
            self.nomoverun = 0

        if r >= REPORT and not self.done:
            self.done = True
            th = ",".join("%d:%d" % (k, v) for k, v in sorted(self.tdx.items())[:9])
            hh = ",".join("%d:%d" % (k, v) for k, v in sorted(self.here.items())[:8])
            ct.resign(("SPY r%d thrown=%d walked=%d mDisp=%.2f d2max=%d minx=%d maxx=%d "
                       "now=%d,%d nomove=%d nomovemax=%d TDX[%s] X[%s]") % (
                r, self.thrown, self.walked, float(self.tdsum) / max(1, self.thrown),
                self.td2max, self.minx, self.maxx, pos.x, pos.y,
                self.nomove, self.nomovemax, th, hh)[:495])
            return

        for p in ct.get_nearby_tiles():
            t = (p.x, p.y)
            if ct.is_tile_empty(p):
                self.blocked.discard(t)
            else:
                self.blocked.add(t)

        if pos == self.goal:
            return
        d = self._bfs(pos, w, h)
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

    def _bfs(self, pos, w, h):
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
                if nxt != goal and nxt in self.blocked:
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
