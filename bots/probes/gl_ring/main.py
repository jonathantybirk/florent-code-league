"""LAUNCHER Q1/Q8: measure the exact PICKUP ring, the throw disc, and ore/oob legality.

Arena: maps/lab/glopen.map26 (26x14 open ground, cores (1,6)/(23,6), ore (10,2)/(15,11)).
Run:   python tools/runprobe.py gl_ring --map lab/glopen --vs idle

One builder walks every tile of the 7x7 block centred on our Launcher at (10,6).
The LAUNCHER (the single reporting unit, M07) records for each visited offset
whether can_launch(builder_tile, safe_target) is True.  That is the pickup ring,
measured rather than assumed.

Then, with the builder parked at (10,5):
  * count the legal TARGET disc and its max d^2 (re-check of G48),
  * try to throw onto an ORE tile,
  * try to throw OUT OF BOUNDS in three directions.
Everything is reported through ct.resign (HARNESS: print() is swallowed).
"""

from fcode import Controller, Direction, EntityType, Position

L = Position(10, 6)
T_SAFE = Position(5, 6)          # d^2 = 25 from L, always empty, never visited
ORE = Position(10, 2)            # ore tile, d^2 = 16 from L
PARK = Position(10, 5)
SPAWN = Position(3, 6)

X0, X1, Y0, Y1 = 7, 13, 3, 9     # the 7x7 scan block

SCAN_END = 190
REPORT = 200


def _way():
    w = []
    for x in range(7, 14):
        w.append((x, 3))
    for x in range(13, 6, -1):
        w.append((x, 4))
    for x in range(7, 14):
        w.append((x, 5))
    w += [(13, 6), (12, 6), (11, 6)]
    w += [(11, 7), (10, 7), (9, 7), (9, 6), (8, 6), (7, 6)]
    w += [(7, 7), (8, 7), (12, 7), (13, 7)]
    for x in range(13, 6, -1):
        w.append((x, 8))
    for x in range(7, 14):
        w.append((x, 9))
    w.append((PARK.x, PARK.y))
    return w


WAY = _way()


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:18]


class Player:
    def __init__(self):
        self.spawned = False
        self.k = 0
        self.grid = {}
        self.empty_src = "?"
        self.notes = []
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("gl_ring TOP " + en(exc))
            except Exception:
                pass

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct, r)

    # ---------------- builder: build the launcher, then walk the block --------
    def _builder(self, ct):
        pos = ct.get_position()
        if self.k == 0:
            if pos != Position(9, 6):
                self._step(ct, pos, Position(9, 6))
                return
            if ct.can_build_launcher(L):
                ct.build_launcher(L)
                self.k = 1
            return
        i = self.k - 1
        if i >= len(WAY):
            return
        goal = Position(WAY[i][0], WAY[i][1])
        if pos == goal:
            self.k += 1
            return
        self._step(ct, pos, goal)

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

    # ---------------- launcher: the only reporting unit -----------------------
    def _launcher(self, ct, r):
        if self.empty_src == "?":
            try:
                self.empty_src = "T" if ct.can_launch(Position(13, 3), T_SAFE) else "F"
            except Exception as exc:
                self.empty_src = en(exc)

        if r < SCAN_END:
            me = ct.get_team()
            for y in range(Y0, Y1 + 1):
                for x in range(X0, X1 + 1):
                    q = Position(x, y)
                    if q == L:
                        continue
                    try:
                        bid = ct.get_tile_builder_bot_id(q)
                    except Exception:
                        continue
                    if bid is None or ct.get_team(bid) != me:
                        continue
                    try:
                        ok = ct.can_launch(q, T_SAFE)
                    except Exception:
                        ok = False
                    key = (x - L.x, y - L.y)
                    if self.grid.get(key) != "1":
                        self.grid[key] = "1" if ok else "0"
            return

        if self.done:
            return
        self.done = True

        src = self._find(ct)
        if src is None:
            self.notes.append("NOSRC")
            self._report(ct)
            return

        # --- throw disc: every legal target for this source ---
        n = 0
        maxl = 0
        maxs = 0
        for dy in range(-7, 8):
            for dx in range(-7, 8):
                q = Position(L.x + dx, L.y + dy)
                if q.x < 0 or q.y < 0 or q.x > 25 or q.y > 13:
                    continue
                try:
                    ok = ct.can_launch(src, q)
                except Exception:
                    ok = False
                if ok:
                    n += 1
                    maxl = max(maxl, dx * dx + dy * dy)
                    d2 = (q.x - src.x) ** 2 + (q.y - src.y) ** 2
                    maxs = max(maxs, d2)
        self.notes.append("DISC n=%d d2L=%d d2S=%d" % (n, maxl, maxs))

        # --- out of bounds ---
        oob = []
        for name, x, y in (("w", -1, 6), ("n", 10, -1), ("e", 26, 6)):
            try:
                oob.append(name + "=" + ("T" if ct.can_launch(src, Position(x, y)) else "F"))
            except Exception as exc:
                oob.append(name + "=" + en(exc))
        self.notes.append("OOB " + ",".join(oob))

        # --- ore tile ---
        try:
            pas = ct.is_tile_passable(ORE)
        except Exception as exc:
            pas = en(exc)
        try:
            leg = ct.can_launch(src, ORE)
        except Exception as exc:
            leg = en(exc)
        land = "-"
        if leg is True:
            bid = ct.get_tile_builder_bot_id(src)
            ct.launch(src, ORE)
            p = ct.get_position(bid)
            land = "%d,%d" % (p.x, p.y)
        self.notes.append("ORE pass=%s legal=%s land=%s" % (pas, leg, land))
        self._report(ct)

    def _find(self, ct):
        me = ct.get_team()
        for y in range(Y0, Y1 + 1):
            for x in range(X0, X1 + 1):
                q = Position(x, y)
                if q == L:
                    continue
                try:
                    bid = ct.get_tile_builder_bot_id(q)
                except Exception:
                    continue
                if bid is not None and ct.get_team(bid) == me:
                    return q
        return None

    def _report(self, ct):
        rows = []
        for dy in range(-3, 4):
            s = ""
            for dx in range(-3, 4):
                if dx == 0 and dy == 0:
                    s += "L"
                else:
                    s += self.grid.get((dx, dy), ".")
            rows.append(s)
        msg = "RING " + ",".join(rows) + "|empty_src=" + str(self.empty_src) + "|"
        msg += "|".join(self.notes)
        ct.resign(msg[:495])
