"""LAUNCHER Q6/Q8: throw an enemy into a SEALED TERRAIN POCKET -- permanent removal?

Arena: maps/lab/glbox.map26 -- glopen plus a one-tile EMPTY pocket at (12,2)
walled in on all four sides by map TERRAIN ((12,1),(11,2),(13,2),(12,3)), and its
rot180 twin at (13,11).  Terrain walls cannot be shot down, so unlike a barrier
cell this prison has no chew-out.

Launcher at (10,6); d^2 to the pocket is 4+16 = 20 <= 26, so the pocket is a
legal throw target even though it is unreachable on foot (G48: the throw arcs).

    python tools/runprobe.py gl_pocket --map lab/glbox --vs gl_atk1
    python tools/runprobe.py gl_pocket --map lab/glbox --vs gl_atkd
"""

from fcode import Controller, Direction, EntityType, Position

L = Position(10, 6)
POCKET = Position(12, 2)
RING = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
SPAWN = Position(3, 6)
REPORT = 995

PLAN = (("go", 9, 6), ("launcher", 10, 6), ("go", 8, 8), ("go", 5, 10))


class Player:
    def __init__(self):
        self.spawned = False
        self.k = 0
        self.seen = set()
        self.leak = 0
        self.legal = "?"
        self.potted = None
        self.pot_round = -1
        self.pot_rounds = 0
        self.pot_lost = -1
        self.escaped = 0
        self.rew = 0
        self.dxsum = 0
        self.hp0 = -1
        self.hp1 = -1
        self.built = -1
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("gl_pocket TOP %s:%s" % (type(exc).__name__, str(exc)[:40]))
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
        ct.write_store(2, ct.get_hp())
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
        myhp = ct.get_hp()
        corehp = ct.read_store(2)
        if (myhp <= 6 or (corehp and corehp < 160)) and not self.done:
            self.done = True
            ct.resign(("POCKET-DEAD r%d lhp=%d corehp=%d legal=%s potrounds=%d "
                       "escaped=%d rew=%d breach=%d leak=%d") % (
                r, myhp, corehp, self.legal, self.pot_rounds, self.escaped,
                self.rew, ct.read_store(0), ct.read_store(1))[:495])
            return
        me = ct.get_team()

        if self.potted is not None:
            where = None
            try:
                where = ct.get_position(self.potted)
            except Exception:
                where = None
            if where is None:
                if self.pot_lost < 0:
                    self.pot_lost = r
            elif where == POCKET:
                self.pot_rounds += 1
                self.hp1 = ct.get_hp(self.potted)
            else:
                self.escaped += 1
                self.potted = None

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
            src = found[0]
            bid = ct.get_tile_builder_bot_id(src)
            if self.legal == "?":
                try:
                    self.legal = "T" if ct.can_launch(src, POCKET) else "F"
                except Exception as exc:
                    self.legal = type(exc).__name__
            free = True
            try:
                free = ct.get_tile_builder_bot_id(POCKET) is None
            except Exception:
                free = self.potted is None
            if self.potted is None and free and self.legal == "T" and ct.can_launch(src, POCKET):
                self.hp0 = ct.get_hp(bid)
                ct.launch(src, POCKET)
                self.potted = bid
                self.pot_round = r
                self.hp1 = ct.get_hp(bid)
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
                        if ok and (best is None or q.x > best.x):
                            best = q
                if best is not None:
                    ct.launch(src, best)
                    self.rew += 1
                    self.dxsum += best.x - src.x

        if r >= REPORT and not self.done:
            self.done = True
            ct.resign(("POCKET r%d built=%d legal=%s potted=%s potround=%d "
                       "potrounds=%d lostvision=%d escaped=%d hp %d->%d "
                       "rew=%d dxavg=%.2f breach=%d leak=%d") % (
                r, self.built, self.legal, str(self.potted), self.pot_round,
                self.pot_rounds, self.pot_lost, self.escaped, self.hp0, self.hp1,
                self.rew, float(self.dxsum) / max(1, self.rew),
                ct.read_store(0), ct.read_store(1))[:495])
