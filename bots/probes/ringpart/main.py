"""Q4 partial denial: identical to `ringlock` but stops after CAP of the 12 ring tiles.

Pair it with `ringobs`, which counts how many builders the strangled Core still gets out
before its own bodies fill the tiles we left open.  With CAP=11 the prediction is exactly
ONE successful spawn and then a permanent lock -- for as long as that body never moves.

Original ringlock docstring follows.

Q2/Q3/Q5: walk ONE builder to the ENEMY Core and brick its whole 12-tile spawn ring.

The builder finds its own Core by scanning its spawn neighbourhood, infers the enemy anchor from
the three editor symmetries (rot180 first, then mirror-x, then mirror-y; the candidate produced by
the most transforms wins, and it is confirmed by sight once the enemy Core comes into vision), and
then tours the OUTSIDE of the enemy ring laying 3-Ti barriers.

It never steps onto a ring or footprint tile: a builder cannot build the tile it stands on (G59),
and barriers block movement, so a builder that walks into the ring bricks itself in.

Q2 diagnostics are taken the first time it stands next to a ring tile: can_build_barrier on the
ring tile, on an enemy FOOTPRINT tile, and can_build_gunner on the ring tile -- i.e. is there any
no-build exclusion zone around an enemy Core at all?

The BUILDER resigns (M07: whichever unit holds the notes must be the one that resigns).
Set REPORT high and pair it with an opponent that resigns earlier when you want the defender's
side of the measurement instead.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
FOOT = ((0, 0), (1, 0), (0, 1), (1, 1))
REPORT = 350
CAP = 11


def ring_of(a, w, h):
    out = []
    for dy in range(-1, 3):
        for dx in range(-1, 3):
            if (dx, dy) in FOOT:
                continue
            t = (a[0] + dx, a[1] + dy)
            if 0 <= t[0] < w and 0 <= t[1] < h:
                out.append(t)
    return out


def foot_of(a):
    return [(a[0] + dx, a[1] + dy) for dx, dy in FOOT]


class Player:
    def __init__(self):
        self.n = []
        self.mine = None
        self.cands = None
        self.enemy = None
        self.confirmed = 0
        self.targets = None
        self.built = 0
        self.first = -1
        self.last = -1
        self.arrive = -1
        self.q2 = 0
        self.ti0 = -1
        self.heals = 0
        self.minhp = 99
        self.bodyblk = 0
        self.spawned = False
        self.stuck = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__ + ":" + str(exc)[:20])

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned:
                a = ct.get_position()
                w, h = ct.get_map_width(), ct.get_map_height()
                for t in ring_of((a.x, a.y), w, h):
                    p = Position(t[0], t[1])
                    try:
                        if ct.can_spawn(p):
                            ct.spawn_builder(p)
                            self.spawned = True
                            return
                    except GameError:
                        continue
            return
        if et != EntityType.BUILDER_BOT:
            return
        self._builder(ct, r)

    # ---------------- builder ----------------
    def _builder(self, ct, r):
        w, h = ct.get_map_width(), ct.get_map_height()
        pos = ct.get_position()
        if self.ti0 < 0:
            self.ti0 = ct.get_global_resources()
        if self.mine is None:
            self.mine = self._find_core(ct, pos, w, h)
            if self.mine is None:
                return
            ax, ay = self.mine
            order = [(w - 2 - ax, h - 2 - ay), (w - 2 - ax, ay), (ax, h - 2 - ay)]
            order = [c for c in order if c != self.mine]
            best = None
            for c in order:
                if best is None or order.count(c) > order.count(best):
                    best = c
            self.cands = [best] + [c for c in order if c != best]
            self.enemy = self.cands[0]
            self.n.append("m=%d,%d e=%d,%d" % (ax, ay, self.enemy[0], self.enemy[1]))

        self._verify(ct)
        if self.targets is None or self.targets[0] != self.enemy:
            self.targets = (self.enemy, ring_of(self.enemy, w, h))

        ring = self.targets[1]
        rset = set(ring)
        fset = set(foot_of(self.enemy))
        todo = [t for t in ring if self._free(ct, t)]
        if self.built >= CAP:
            todo = []

        if r >= REPORT:
            self._report(ct, r, ring)
            return

        # --- maintenance: the ring is complete, so keep the weakest barrier alive ---
        if not todo and self.arrive >= 0:
            self._maintain(ct, pos, ring, rset, fset, w, h)
            return

        # An enemy BODY parked on a ring tile holds that tile open and blocks the barrier.
        # Count it, skip it, and go do the other tiles -- never wait on it.
        open_now = []
        for t in todo:
            if self._bot_on(ct, t):
                self.bodyblk += 1
            else:
                open_now.append(t)
        if not open_now:
            return

        # --- act: brick any orthogonally adjacent unfinished ring tile ---
        acted = False
        if ct.get_action_cooldown() == 0:
            for t in open_now:
                if abs(t[0] - pos.x) + abs(t[1] - pos.y) != 1:
                    continue
                if self.arrive < 0:
                    self.arrive = r
                    self._probe_q2(ct, t)
                p = Position(t[0], t[1])
                try:
                    if ct.can_build_barrier(p):
                        ct.build_barrier(p)
                        self.built += 1
                        if self.first < 0:
                            self.first = r
                        self.last = r
                        acted = True
                        break
                except GameError:
                    continue

        # --- move: commit to the NEAREST unfinished ring tile and walk to a tile beside it ---
        if ct.get_move_cooldown() != 0 or acted:
            return
        # Try ring tiles nearest-first and take the first one with a REACHABLE stand tile.  A
        # single fixed target deadlocks whenever its stand tiles are walled off (showdown), and a
        # ring tile flush against the map border (duel, longship) has no stand tile outside the
        # ring at all -- so standing inside the ring is allowed as a fallback.  A body inside the
        # ring closes that spawn tile exactly like a barrier would.
        order = sorted(open_now, key=lambda t: abs(t[0] - pos.x) + abs(t[1] - pos.y))
        for tgt in order[:8]:
            outside = set()
            inside = set()
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                s = (tgt[0] + dx, tgt[1] + dy)
                if s in fset or not (0 <= s[0] < w and 0 <= s[1] < h):
                    continue
                (inside if s in rset else outside).add(s)
            for goals in (outside, inside):
                if not goals or (pos.x, pos.y) in goals:
                    continue
                d = self._bfs(ct, pos, goals, fset, w, h)
                if d is None:
                    continue
                try:
                    if ct.can_move(d):
                        ct.move(d)
                        return
                except GameError:
                    return
        self.stuck += 1

    def _bot_on(self, ct, t):
        p = Position(t[0], t[1])
        try:
            if not ct.is_in_vision(p):
                return False
            return ct.get_tile_builder_bot_id(p) is not None
        except GameError:
            return False

    def _maintain(self, ct, pos, ring, rset, fset, w, h):
        weak = None
        weakhp = 999
        for t in ring:
            p = Position(t[0], t[1])
            try:
                b = ct.get_tile_building_id(p)
                if b is None:
                    continue
                hp = ct.get_hp(b)
            except GameError:
                continue
            if hp < self.minhp:
                self.minhp = hp
            if hp < ct.get_max_hp(b) and hp < weakhp:
                weak, weakhp = t, hp
        if weak is None:
            return
        if abs(weak[0] - pos.x) + abs(weak[1] - pos.y) == 1:
            p = Position(weak[0], weak[1])
            try:
                if ct.can_heal(p):
                    ct.heal(p)
                    self.heals += 1
            except GameError:
                pass
            return
        if ct.get_move_cooldown() != 0:
            return
        goals = set()
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            s = (weak[0] + dx, weak[1] + dy)
            if s in rset or s in fset:
                continue
            if 0 <= s[0] < w and 0 <= s[1] < h:
                goals.add(s)
        d = self._bfs(ct, pos, goals, rset | fset, w, h)
        if d is None:
            return
        try:
            if ct.can_move(d):
                ct.move(d)
        except GameError:
            return

    def _free(self, ct, t):
        p = Position(t[0], t[1])
        try:
            if not ct.is_in_vision(p):
                return True
            return ct.get_tile_building_id(p) is None
        except GameError:
            return True

    def _verify(self, ct):
        if self.confirmed:
            return
        p = Position(self.enemy[0], self.enemy[1])
        try:
            if not ct.is_in_vision(p):
                return
            b = ct.get_tile_building_id(p)
        except GameError:
            return
        ok = 0
        if b is not None:
            try:
                ok = int(ct.get_entity_type(b) == EntityType.CORE
                         and ct.get_team(b) != ct.get_team())
            except GameError:
                ok = 0
        if ok:
            self.confirmed = 1
            return
        rest = [c for c in self.cands if c != self.enemy]
        if rest:
            self.enemy = rest[0]
            self.cands = rest
            self.n.append("REJ")

    def _probe_q2(self, ct, t):
        if self.q2:
            return
        self.q2 = 1
        p = Position(t[0], t[1])

        def s(label, fn):
            try:
                self.n.append("%s=%s" % (label, str(fn())[:12]))
            except Exception as exc:
                self.n.append("%s!%s" % (label, str(exc)[:18]))

        s("emp", lambda: ct.is_tile_empty(p))
        s("bar", lambda: ct.can_build_barrier(p))
        s("gun", lambda: ct.can_build_gunner(p, Direction.NORTH))
        # an enemy FOOTPRINT tile, if one happens to be orthogonally adjacent
        me = ct.get_position()
        for f in foot_of(self.enemy):
            if abs(f[0] - me.x) + abs(f[1] - me.y) == 1:
                s("foot", lambda: ct.can_build_barrier(Position(f[0], f[1])))
                break

    def _report(self, ct, r, ring):
        occ = ""
        for t in ring:
            p = Position(t[0], t[1])
            try:
                b = ct.get_tile_building_id(p)
                u = ct.get_tile_builder_bot_id(p)
            except GameError:
                occ += "?"
                continue
            occ += "B" if b is not None else ("u" if u is not None else "-")
        ct.resign(("RL|%s n=%d cf=%d built=%d arr=%d f=%d l=%d ti %d->%d sc=%.0f "
                   "stk=%d hl=%d mhp=%d bb=%d occ=%s r=%d" % (
                       " ".join(self.n), len(ring), self.confirmed, self.built, self.arrive,
                       self.first, self.last, self.ti0, ct.get_global_resources(),
                       ct.get_scale_percent(), self.stuck, self.heals, self.minhp, self.bodyblk, occ, r))[:495])

    # ---------------- helpers ----------------
    def _find_core(self, ct, pos, w, h):
        me = ct.get_team()
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                x, y = pos.x + dx, pos.y + dy
                if not (0 <= x < w and 0 <= y < h):
                    continue
                try:
                    b = ct.get_tile_building_id(Position(x, y))
                    if b is None:
                        continue
                    if ct.get_entity_type(b) != EntityType.CORE or ct.get_team(b) != me:
                        continue
                    q = ct.get_position(b)
                    return (q.x, q.y)
                except GameError:
                    continue
        return None

    def _bfs(self, ct, start, goals, banned, w, h):
        seen = {(start.x, start.y): None}
        frontier = [(start.x, start.y)]
        while frontier:
            nxt = []
            for (x, y) in frontier:
                for d in CARD:
                    dx, dy = d.delta()
                    n = (x + dx, y + dy)
                    if n in seen or n in banned:
                        continue
                    if not (0 <= n[0] < w and 0 <= n[1] < h):
                        continue
                    ok = True
                    try:
                        if ct.is_in_vision(Position(n[0], n[1])):
                            ok = ct.is_tile_passable(Position(n[0], n[1]))
                    except GameError:
                        ok = True
                    if not ok:
                        continue
                    seen[n] = (x, y)
                    if n in goals:
                        cur = n
                        while seen[cur] is not None and seen[cur] != (start.x, start.y):
                            cur = seen[cur]
                        return start.cardinal_direction_to(Position(cur[0], cur[1]))
                    nxt.append(n)
            frontier = nxt
        return None
