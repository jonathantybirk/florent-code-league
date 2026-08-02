"""AREA 1 / probe 6: the GOBBLE PEN, built correctly, with throughput counting.

`glopen` (26x14, NO terrain at all). Core A anchor (1,6), Core B anchor (22,6).

        (9,5)B
   (8,6)B  (9,6)CELL  (10,6)LAUNCHER
        (9,7)B

The CELL's four cardinal neighbours are 3 barriers + the Launcher, so a bot
thrown into it cannot move at all. The Launcher's other 5 ring tiles stay open
as bait. Counts GOBBLEs, REWINDs, and BREACHes (enemy reaching x<=5).

An explicit waypoint PLAN replaces the greedy walk that failed in gl_pen: the
barriers wall off the greedy route, so the builder must be told to go round.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

LPOS = Position(10, 6)
CELL = Position(9, 6)
RING = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

PLAN = [
    ("go", 9, 6),
    ("launcher", 10, 6),
    ("go", 8, 6),
    ("go", 8, 5),
    ("barrier", 9, 5),
    ("barrier", 8, 6),
    ("go", 7, 5),
    ("go", 7, 6),
    ("go", 7, 7),
    ("go", 8, 7),
    ("barrier", 9, 7),
    ("go", 6, 7),
    ("go", 5, 10),
]


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:26]


class Player:
    def __init__(self):
        self.spawned = False
        self.k = 0
        self.gobbles = 0
        self.rewinds = 0
        self.sumdx = 0
        self.prisoner = None
        self.locked_since = 0
        self.breached = set()
        self.penned = set()

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("LP|TOP %s" % en(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 6)):
                ct.spawn_builder(Position(3, 6))
                self.spawned = True
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct, r)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct, r)

    def _builder(self, ct, r):
        if self.k >= len(PLAN):
            return
        op, x, y = PLAN[self.k]
        p = Position(x, y)
        pos = ct.get_position()
        if op == "go":
            if pos == p:
                self.k += 1
                return
            d = pos.cardinal_direction_to(p)
            if ct.can_move(d):
                ct.move(d)
            return
        if op == "launcher":
            if ct.can_build_launcher(p):
                ct.build_launcher(p)
                self.k += 1
                print("LP|r%d LAUNCHER up at %s,%s" % (r, x, y))
            return
        if op == "barrier":
            if ct.can_build_barrier(p):
                ct.build_barrier(p)
                self.k += 1
                print("LP|r%d BARRIER %s,%s (%d/3)" % (r, x, y, self.k))
            return

    def _launcher(self, ct, r):
        me = ct.get_team()
        if self.prisoner is not None:
            try:
                p = ct.get_position(self.prisoner)
                if p != CELL:
                    print("LP|r%d PRISONER id%d ESCAPED after %d rounds to %s,%s" % (
                        r, self.prisoner, r - self.locked_since, p.x, p.y))
                    self.prisoner = None
            except Exception:
                print("LP|r%d PRISONER id%d gone after %d rounds" % (
                    r, self.prisoner, r - self.locked_since))
                self.prisoner = None

        for eid in ct.get_nearby_units():
            if ct.get_team(eid) == me:
                continue
            if ct.get_position(eid).x <= 5 and eid not in self.breached:
                self.breached.add(eid)
                print("LP|r%d BREACH id%d total=%d" % (r, eid, len(self.breached)))

        src = None
        for dx, dy in RING:
            q = Position(LPOS.x + dx, LPOS.y + dy)
            if q == CELL:
                continue
            try:
                bid = ct.get_tile_builder_bot_id(q)
            except Exception:
                continue
            if bid is None or ct.get_team(bid) == me:
                continue
            src = q
            break
        if src is None:
            return

        cell_free = False
        try:
            cell_free = ct.get_tile_builder_bot_id(CELL) is None
        except Exception:
            cell_free = False
        if cell_free and ct.can_launch(src, CELL):
            bid = ct.get_tile_builder_bot_id(src)
            ct.launch(src, CELL)
            self.gobbles += 1
            self.prisoner = bid
            self.locked_since = r
            self.penned.add(bid)
            print("LP|r%d GOBBLE id%d %s,%s -> CELL (gobbles=%d distinct=%d)" % (
                r, bid, src.x, src.y, self.gobbles, len(self.penned)))
            return

        best = None
        for dy in range(-5, 6):
            for dx in range(-5, 6):
                if dx * dx + dy * dy > 26:
                    continue
                q = Position(LPOS.x + dx, LPOS.y + dy)
                if q.x < 0 or q.y < 0:
                    continue
                try:
                    ok = ct.can_launch(src, q)
                except Exception:
                    continue
                if ok and (best is None or q.x > best.x):
                    best = q
        if best is None:
            return
        bid = ct.get_tile_builder_bot_id(src)
        ct.launch(src, best)
        self.rewinds += 1
        self.sumdx += best.x - src.x
        if self.rewinds % 25 == 1:
            print("LP|r%d REWIND id%d %s,%s -> %s,%s dx=+%d (n=%d avgdx=%.2f)" % (
                r, bid, src.x, src.y, best.x, best.y, best.x - src.x,
                self.rewinds, float(self.sumdx) / self.rewinds))
        if r > 995:
            print("LP|r%d TOTALS gobbles=%d distinct_penned=%d rewinds=%d avgdx=%.2f breaches=%d" % (
                r, self.gobbles, len(self.penned), self.rewinds,
                float(self.sumdx) / max(1, self.rewinds), len(self.breached)))
