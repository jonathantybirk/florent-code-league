"""HALF BODYGUARD: only the TWO enemy-facing diagonals (3,5) and (3,8).

Cost/benefit rung below gl_guard -- covers 4 of the 8 Core attack tiles for half
the titanium and half the cost-scale tax. Original gl_guard docstring follows.


gl_rew proved a Launcher in open ground is worthless against a pathfinder that
routes around its 8-tile ring (gl_atkr: 4 breaches, 3892 leak-rounds, 1 throw).
The one place an attacker CANNOT route around is the objective itself: to damage
our Core it must stand on one of the 8 tiles orthogonally adjacent to the 2x2
footprint (G59: builder attacks are orthogonal-only).

Core A on lab/glopen is anchored at (1,6), so the 8 attack tiles are
(0,6),(0,7),(3,6),(3,7),(1,5),(2,5),(1,8),(2,8).  Four Launchers on the four
DIAGONALS of the footprint -- (0,5),(3,5),(0,8),(3,8) -- have all eight of them
inside their pickup rings, and each throws its catch to the legal target
furthest from itself.

The CORE is the reporting unit here (M07): it reads its own HP directly.

    python tools/runprobe.py gl_guard --map lab/glopen --vs gl_atks
    python tools/runprobe.py gl_null  --map lab/glopen --vs gl_atks   (baseline)
"""

from fcode import Controller, Direction, EntityType, Position

LPOS = ((0, 5), (3, 5), (0, 8), (3, 8))
RING = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
SPAWN = Position(2, 5)
REPORT = 995

PLAN = (
    ("launcher", 3, 5),
    ("go", 2, 4), ("go", 4, 4), ("go", 4, 8), ("launcher", 3, 8),
    ("go", 4, 9),
)


class Player:
    def __init__(self):
        self.spawned = False
        self.k = 0
        self.minhp = 500
        self.minr = -1
        self.adj = 0
        self.seen = set()
        self.nl = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("gl_guard TOP %s:%s" % (type(exc).__name__, str(exc)[:40]))
            except Exception:
                pass

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            self._core(ct, r)
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct)

    def _core(self, ct, r):
        if not self.spawned and ct.can_spawn(SPAWN):
            ct.spawn_builder(SPAWN)
            self.spawned = True
        hp = ct.get_hp()
        if hp < self.minhp:
            self.minhp = hp
            self.minr = r
        me = ct.get_team()
        nl = 0
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == me and ct.get_entity_type(bid) == EntityType.LAUNCHER:
                nl += 1
        self.nl = max(self.nl, nl)
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == me:
                continue
            p = ct.get_position(uid)
            self.seen.add(uid)
            if p.x <= 3 and 5 <= p.y <= 8:
                self.adj += 1
        if r >= REPORT and not self.done:
            self.done = True
            ct.resign(("GUARD2 r%d corehp=%d minhp=%d minr=%d launchers=%d "
                       "enemies=%d adjrounds=%d ti=%d scale=%.0f") % (
                r, hp, self.minhp, self.minr, self.nl, len(self.seen), self.adj,
                ct.get_global_resources(), ct.get_scale_percent())[:495])

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
        for d in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
            if d not in opts and ct.can_move(d):
                ct.move(d)
                return

    def _launcher(self, ct):
        me = ct.get_team()
        L = ct.get_position()
        src = None
        for dx, dy in RING:
            q = Position(L.x + dx, L.y + dy)
            if q.x < 0 or q.y < 0:
                continue
            try:
                bid = ct.get_tile_builder_bot_id(q)
            except Exception:
                continue
            if bid is not None and ct.get_team(bid) != me:
                src = q
                break
        if src is None:
            return
        best = None
        bd = -1
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
                if not ok:
                    continue
                d2 = dx * dx + dy * dy
                if d2 > bd:
                    bd = d2
                    best = q
        if best is not None:
            ct.launch(src, best)
