"""LAUNCHER Q4: REWIND-ONLY launcher sited on a CHOKEPOINT.

Arena: maps/lab/glchoke.map26 -- a double wall band at x=12,13 with a single
one-tile gap at (12,6)/(13,6). The Launcher sits at (11,6), so the gap tile
(12,6) is inside its 8-tile pickup ring and there is NO route around it.
Same code as gl_rew, only the Launcher position differs.  Run:

    python tools/runprobe.py gl_rewc --map lab/glchoke --vs gl_atk1
    python tools/runprobe.py gl_rewc --map lab/glchoke --vs gl_atk4
    python tools/runprobe.py gl_rewc --map lab/glchoke --vs gl_atkr

A single 20 Ti Launcher at (10,6).  Every round it looks at its 8-tile pickup
ring; if an enemy builder is standing there it throws that bot to the legal
target with the largest x (straight back toward the enemy Core) and records the
displacement.  Counts:

  rew        throws made
  ringmax    largest number of DISTINCT enemies standing in the ring at once
             (the Launcher may only throw ONE of them per round -- this is the
             throughput ceiling)
  ringsum    enemy-in-ring observations that could NOT be thrown that round
  breach/leak  relayed from the Core through store slots 0/1: distinct enemies
             that reached x<=5, and total enemy-rounds spent there.
"""

from fcode import Controller, Direction, EntityType, Position

L = Position(11, 6)
RING = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
SPAWN = Position(3, 6)
PARK = Position(5, 10)
REPORT = 995

PLAN = (("go", 10, 6), ("launcher", 11, 6), ("go", 8, 8), ("go", 5, 10))


class Player:
    def __init__(self):
        self.spawned = False
        self.k = 0
        self.seen = set()
        self.leak = 0
        self.rew = 0
        self.ids = set()
        self.ringmax = 0
        self.missed = 0
        self.dxsum = 0
        self.d2sum = 0
        self.dxhist = {}
        self.d2max = 0
        self.built = -1
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("gl_rew TOP %s:%s" % (type(exc).__name__, str(exc)[:40]))
            except Exception:
                pass

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct, ct.get_current_round())

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
        if ct.can_build_launcher(p):
            ct.build_launcher(p)
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

    def _launcher(self, ct, r):
        if self.built < 0:
            self.built = r
        me = ct.get_team()
        found = []
        for dx, dy in RING:
            q = Position(L.x + dx, L.y + dy)
            try:
                bid = ct.get_tile_builder_bot_id(q)
            except Exception:
                continue
            if bid is not None and ct.get_team(bid) != me:
                found.append(q)
        if found:
            self.ringmax = max(self.ringmax, len(found))
            self.missed += len(found) - 1
            src = found[0]
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
                bid = ct.get_tile_builder_bot_id(src)
                ct.launch(src, best)
                d = best.x - src.x
                d2 = (best.x - src.x) ** 2 + (best.y - src.y) ** 2
                self.rew += 1
                self.ids.add(bid)
                self.dxsum += d
                self.d2sum += d2
                self.d2max = max(self.d2max, d2)
                self.dxhist[d] = self.dxhist.get(d, 0) + 1

        if r >= REPORT and not self.done:
            self.done = True
            dh = ",".join("%d:%d" % (k, v) for k, v in sorted(self.dxhist.items())[:9])
            msg = ("REWC r%d built=%d rew=%d ids=%d ringmax=%d missed=%d "
                   "dxavg=%.2f d2avg=%.1f d2max=%d breach=%d leak=%d DX[%s]") % (
                r, self.built, self.rew, len(self.ids), self.ringmax, self.missed,
                float(self.dxsum) / max(1, self.rew), float(self.d2sum) / max(1, self.rew),
                self.d2max, ct.read_store(0), ct.read_store(1), dh)
            ct.resign(msg[:495])
