"""LAUNCHER Q1/Q2/Q3/Q5: the GOBBLE PEN, rebuilt, reporting through ct.resign.

Arena: maps/lab/glopen.map26 (26x14 open ground; nothing on the map can help
either side).  Run:

    python tools/runprobe.py gl_pen3 --map lab/glopen --vs gl_atk1
    python tools/runprobe.py gl_pen3 --map lab/glopen --vs gl_atk4

           (9,5)B
    (8,6)B (9,6)CELL (10,6)LAUNCHER
           (9,7)B

The CELL's four cardinal neighbours are 3 barriers plus the Launcher, so a bot
thrown into it has no legal move.  The Launcher's other five ring tiles stay
open as bait.  Policy: enemy in the pickup ring -> throw into the CELL if the
CELL is free, else REWIND (throw to the legal target with the largest x, i.e.
back toward the enemy Core) and log the displacement.

The CORE is a second sensor: it counts enemies that reach x<=5 and relays the
counts to the Launcher through store slots 0/1 (1-round lag, G20).
"""

from fcode import Controller, Direction, EntityType, Position

L = Position(10, 6)
CELL = Position(9, 6)
BARR = (Position(9, 5), Position(8, 6), Position(9, 7))
RING = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
SPAWN = Position(3, 6)
REPORT = 995

PLAN = (
    ("go", 9, 6), ("launcher", 10, 6),
    ("go", 8, 6), ("go", 8, 5),
    ("barrier", 9, 5), ("barrier", 8, 6),
    ("go", 7, 5), ("go", 7, 6), ("go", 7, 7), ("go", 8, 7),
    ("barrier", 9, 7),
    ("go", 6, 7), ("go", 5, 10),
)


class Player:
    def __init__(self):
        self.spawned = False
        self.k = 0
        # core sensor
        self.seen = set()
        self.leak = 0
        # launcher counters
        self.gob = 0
        self.gobids = set()
        self.esc = 0
        self.holdsum = 0
        self.holdmax = 0
        self.escwhere = {}
        self.rew = 0
        self.dxsum = 0
        self.dxmax = -9
        self.dxmin = 9
        self.dxhist = {}
        self.prisoner = None
        self.since = 0
        self.penrounds = 0
        self.built = -1
        self.sealed_at = -1
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("gl_pen3 TOP %s:%s" % (type(exc).__name__, str(exc)[:40]))
            except Exception:
                pass

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            self._core(ct)
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct, r)

    def _core(self, ct):
        if not self.spawned and ct.can_spawn(SPAWN):
            ct.spawn_builder(SPAWN)
            self.spawned = True
        me = ct.get_team()
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == me:
                continue
            if ct.get_position(uid).x <= 5:
                self.seen.add(uid)
                self.leak += 1
        ct.write_store(0, len(self.seen))
        ct.write_store(1, min(self.leak, 4000000000))

    def _builder(self, ct):
        if self.k >= len(PLAN):
            return
        op, x, y = PLAN[self.k]
        p = Position(x, y)
        pos = ct.get_position()
        if op == "go":
            if pos == p:
                self.k += 1
                return
            self._step(ct, pos, p)
            return
        if op == "launcher":
            if ct.can_build_launcher(p):
                ct.build_launcher(p)
                self.k += 1
            return
        if ct.can_build_barrier(p):
            ct.build_barrier(p)
            self.k += 1

    def _step(self, ct, pos, goal):
        dx = goal.x - pos.x
        dy = goal.y - pos.y
        opts = []
        if abs(dx) >= abs(dy):
            if dx:
                opts.append(Direction.EAST if dx > 0 else Direction.WEST)
            if dy:
                opts.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
        else:
            if dy:
                opts.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
            if dx:
                opts.append(Direction.EAST if dx > 0 else Direction.WEST)
        for d in opts:
            if ct.can_move(d):
                ct.move(d)
                return

    def _sealed(self, ct, c):
        n = 0
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = Position(c.x + dx, c.y + dy)
            if q.x < 0 or q.y < 0 or q.x >= ct.get_map_width() or q.y >= ct.get_map_height():
                n += 1
                continue
            try:
                if not ct.is_tile_passable(q):
                    n += 1
            except Exception:
                n += 1
        return n == 4

    def _launcher(self, ct, r):
        if self.built < 0:
            self.built = r
        me = ct.get_team()

        if self.prisoner is not None:
            gone = False
            try:
                p = ct.get_position(self.prisoner)
            except Exception:
                gone = True
                p = None
            if gone:
                self.esc += 1
                self.holdsum += r - self.since
                self.holdmax = max(self.holdmax, r - self.since)
                self.escwhere["dead"] = self.escwhere.get("dead", 0) + 1
                self.prisoner = None
            elif p != CELL:
                self.esc += 1
                self.holdsum += r - self.since
                self.holdmax = max(self.holdmax, r - self.since)
                key = "%d%d" % (p.x - CELL.x, p.y - CELL.y)
                self.escwhere[key] = self.escwhere.get(key, 0) + 1
                self.prisoner = None
            else:
                self.penrounds += 1

        src = None
        for dx, dy in RING:
            q = Position(L.x + dx, L.y + dy)
            if q == CELL:
                continue
            try:
                bid = ct.get_tile_builder_bot_id(q)
            except Exception:
                continue
            if bid is not None and ct.get_team(bid) != me:
                src = q
                break

        if src is not None:
            free = False
            try:
                free = ct.get_tile_builder_bot_id(CELL) is None
            except Exception:
                free = False
            sealed = self._sealed(ct, CELL)
            if sealed and self.sealed_at < 0:
                self.sealed_at = r
            bid = ct.get_tile_builder_bot_id(src)
            if free and sealed and ct.can_launch(src, CELL):
                ct.launch(src, CELL)
                self.gob += 1
                self.gobids.add(bid)
                self.prisoner = bid
                self.since = r
            else:
                best = None
                for dy in range(-5, 6):
                    for dx in range(-5, 6):
                        if dx * dx + dy * dy > 26:
                            continue
                        q = Position(L.x + dx, L.y + dy)
                        if q.x < 0 or q.y < 0:
                            continue
                        ok = False
                        try:
                            ok = ct.can_launch(src, q)
                        except Exception:
                            ok = False
                        if ok and (best is None or q.x > best.x
                                   or (q.x == best.x and abs(q.y - src.y) < abs(best.y - src.y))):
                            best = q
                if best is not None:
                    ct.launch(src, best)
                    d = best.x - src.x
                    self.rew += 1
                    self.dxsum += d
                    self.dxmax = max(self.dxmax, d)
                    self.dxmin = min(self.dxmin, d)
                    self.dxhist[d] = self.dxhist.get(d, 0) + 1

        if r >= REPORT and not self.done:
            self.done = True
            self._report(ct, r)

    def _report(self, ct, r):
        bh = []
        for b in BARR:
            try:
                i = ct.get_tile_building_id(b)
                bh.append(str(ct.get_hp(i)) if i is not None else "X")
            except Exception:
                bh.append("?")
        ew = ",".join("%s:%d" % (k, v) for k, v in sorted(self.escwhere.items())[:6])
        dh = ",".join("%d:%d" % (k, v) for k, v in sorted(self.dxhist.items())[:8])
        msg = ("PEN3 r%d built=%d sealed=%d gob=%d distinct=%d esc=%d holdmax=%d holdavg=%.2f "
               "penrnds=%d rew=%d dxavg=%.2f dxmax=%d dxmin=%d barrHP=%s "
               "breach=%d leak=%d ESC[%s] DX[%s]") % (
            r, self.built, self.sealed_at, self.gob, len(self.gobids), self.esc, self.holdmax,
            float(self.holdsum) / max(1, self.esc), self.penrounds, self.rew,
            float(self.dxsum) / max(1, self.rew), self.dxmax, self.dxmin,
            "/".join(bh), ct.read_store(0), ct.read_store(1), ew, dh)
        ct.resign(msg[:495])
