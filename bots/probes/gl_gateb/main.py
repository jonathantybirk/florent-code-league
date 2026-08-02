"""MIRRORED GATE (team B) -- the mirror-x image of gl_gate on lab/glchoke.

Exists so gl_spy can play the victim and report inescapability from INSIDE the
cell:  python tools/runprobe.py gl_spy --map lab/glchoke --vs gl_gateb

Original gl_gate docstring follows.


Arena: maps/lab/glchoke.map26 (double wall band at x=12,13, one-tile gap at y=6).

    y=0   B(10,0)  CELL(11,0)  #
    y=1   .        B(11,1)     #
    y=2   B(10,2)  CELL(11,2)  #
    y=3   .        B(11,3)     #
    y=4   B(10,4)  CELL(11,4)  #
    y=5   bait     LAUNCHER    #
    y=6   bait     bait        GAP(12,6)  GAP(13,6)

The Launcher sits at (11,5), NOT in the corridor, so the enemy pathfinder still
has a route and keeps coming (gl_rewc showed that plugging the gap itself just
makes the attacker give up and mill about). Corridor tiles (12,6),(11,6),(10,6)
are all inside the 8-tile pickup ring.

Three one-tile cells hang off the wall column at (11,4),(11,2),(11,0); each is
sealed by the map's own WALL on its east side, so the whole prison costs FIVE
barriers.  Policy: enemy on a bait tile -> throw into the lowest free sealed
cell; if every cell is full -> REWIND (throw to the legal target with max x).

    python tools/runprobe.py gl_gate --map lab/glchoke --vs gl_atk1
    python tools/runprobe.py gl_gate --map lab/glchoke --vs gl_atk4
    python tools/runprobe.py gl_gate --map lab/glchoke --vs gl_atkr
"""

from fcode import Controller, Direction, EntityType, Position

L = Position(14, 5)
CELLS = (Position(14, 4), Position(14, 2), Position(14, 0))
RING = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
SPAWN = Position(22, 6)
REPORT = 995

PLAN = (
    ("go", 15, 6), ("go", 15, 5), ("launcher", 14, 5),
    ("barrier", 15, 4),
    ("go", 16, 5), ("go", 16, 4), ("go", 16, 3), ("go", 15, 3),
    ("barrier", 14, 3), ("barrier", 15, 2),
    ("go", 16, 3), ("go", 16, 2), ("go", 16, 1), ("go", 15, 1),
    ("barrier", 14, 1), ("barrier", 15, 0),
    ("go", 16, 1), ("go", 18, 1), ("go", 20, 10),
)


class Player:
    def __init__(self):
        self.spawned = False
        self.k = 0
        self.seen = set()
        self.leak = 0
        self.gob = 0
        self.gobids = set()
        self.esc = 0
        self.holdmax = 0
        self.rew = 0
        self.dxsum = 0
        self.dxhist = {}
        self.hold = {}
        self.since = {}
        self.maxheld = 0
        self.heldrounds = 0
        self.ringmax = 0
        self.missed = 0
        self.built = -1
        self.penready = -1
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("gl_gate TOP %s:%s" % (type(exc).__name__, str(exc)[:40]))
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
            if ct.get_position(uid).x >= 20:
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
        if self.penready < 0:
            ok = True
            for c in CELLS:
                if not self._sealed(ct, c):
                    ok = False
            if ok:
                self.penready = r

        # --- prisoner bookkeeping ---
        held = 0
        for c in CELLS:
            occ = None
            try:
                occ = ct.get_tile_builder_bot_id(c)
            except Exception:
                occ = None
            key = (c.x, c.y)
            if occ is not None and ct.get_team(occ) != me:
                held += 1
                if key not in self.since:
                    self.since[key] = r
            elif key in self.since:
                self.esc += 1
                self.holdmax = max(self.holdmax, r - self.since[key])
                del self.since[key]
        self.maxheld = max(self.maxheld, held)
        self.heldrounds += held

        # --- pickup ---
        found = []
        for dx, dy in RING:
            q = Position(L.x + dx, L.y + dy)
            if q in CELLS:
                continue
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
            bid = ct.get_tile_builder_bot_id(src)
            dest = None
            for c in CELLS:
                if not self._sealed(ct, c):
                    continue
                ok = False
                try:
                    ok = ct.can_launch(src, c)
                except Exception:
                    ok = False
                if ok:
                    dest = c
                    break
            if dest is not None:
                ct.launch(src, dest)
                self.gob += 1
                self.gobids.add(bid)
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
                        if ok and (best is None or q.x < best.x):
                            best = q
                if best is not None:
                    ct.launch(src, best)
                    d = best.x - src.x
                    self.rew += 1
                    self.dxsum += d
                    self.dxhist[d] = self.dxhist.get(d, 0) + 1

        if r >= REPORT and not self.done:
            self.done = True
            dh = ",".join("%d:%d" % (k, v) for k, v in sorted(self.dxhist.items())[:6])
            ct.resign(("GATEB r%d built=%d penready=%d gob=%d distinct=%d esc=%d "
                       "holdmax=%d maxheld=%d heldrnds=%d rew=%d dxavg=%.2f "
                       "ringmax=%d missed=%d breach=%d leak=%d DX[%s]") % (
                r, self.built, self.penready, self.gob, len(self.gobids), self.esc,
                self.holdmax, self.maxheld, self.heldrounds, self.rew,
                float(self.dxsum) / max(1, self.rew), self.ringmax, self.missed,
                ct.read_store(0), ct.read_store(1), dh)[:495])
