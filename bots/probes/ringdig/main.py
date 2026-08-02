"""Q6 defender: an opponent that gets its builders OUT before the ring closes, then digs back in.

This is the realistic case.  A real bot spawns builders on round 0, so by the time an attacker
walks over (round 20-50 depending on the map) there are already bodies outside the ring, and a
Builder Bot attacks an adjacent building for BUILDER_BOT_ATTACK_DAMAGE=2 at BUILDER_BOT_ATTACK_COST=2
titanium.  A 30 HP barrier therefore costs 15 hits = 30 Ti to clear -- against a barrier that cost
the attacker 3 Ti.  This probe measures whether that exchange rate actually holds in play, and
whether a ring lock survives an opponent that is actively trying to break it.

DEFENDERS builders spawn immediately, walk clear of their own ring so they do not block it
themselves, and then attack the nearest visible enemy building, preferring one on their own ring.

The CORE reports (M07): ring occupancy, minimum ring-barrier HP, spawnable ring tiles, titanium,
and how much titanium the team burnt, sampled every 50 rounds.  Resigns at REPORT.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
FOOT = ((0, 0), (1, 0), (0, 1), (1, 1))
N_BUILDERS = 3
STAGE = 4          # Chebyshev distance from the anchor the builders idle at
REPORT = 300   # keep BELOW ringlock's REPORT to read the defender's side;
               # raise it above to read the attacker's side instead


class Player:
    def __init__(self):
        self.n = []
        self.ring = None
        self.spawned = 0
        self.anchor = None
        self.hits = 0
        self.kills = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__)

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)

    # ---------------- core: spawner + reporter ----------------
    def _core(self, ct):
        r = ct.get_current_round()
        a = ct.get_position()
        w, h = ct.get_map_width(), ct.get_map_height()
        ct.write_store(0, a.x + 1)
        ct.write_store(1, a.y + 1)
        if self.ring is None:
            self.ring = []
            for dy in range(-1, 3):
                for dx in range(-1, 3):
                    if (dx, dy) in FOOT:
                        continue
                    t = Position(a.x + dx, a.y + dy)
                    if 0 <= t.x < w and 0 <= t.y < h:
                        self.ring.append(t)

        if self.spawned < N_BUILDERS and ct.get_action_cooldown() == 0:
            for t in self.ring:
                try:
                    if ct.can_spawn(t):
                        ct.spawn_builder(t)
                        self.spawned += 1
                        break
                except GameError:
                    continue

        if r % 50 == 0 and r <= REPORT:
            occ = 0
            free = 0
            mn = 99
            for t in self.ring:
                try:
                    b = ct.get_tile_building_id(t)
                    if b is not None:
                        occ += 1
                        hp = ct.get_hp(b)
                        if hp < mn:
                            mn = hp
                    if ct.can_spawn(t):
                        free += 1
                except GameError:
                    continue
            self.n.append("%d:%d/%dh%dt%d" % (r, occ, free, mn, ct.get_global_resources()))

        if r == REPORT:
            ct.resign(("DIG|sp=%d u=%d ring=%d %s" % (
                self.spawned, ct.get_unit_count(), len(self.ring),
                " ".join(self.n)))[:495])

    # ---------------- builders: clear the ring, then grind barriers ----------------
    def _builder(self, ct):
        pos = ct.get_position()
        w, h = ct.get_map_width(), ct.get_map_height()
        if self.anchor is None:
            x, y = ct.read_store(0), ct.read_store(1)
            if x <= 0 or y <= 0:
                return
            self.anchor = (x - 1, y - 1)
        a = self.anchor
        me = ct.get_team()

        # 1. attack an orthogonally adjacent ENEMY building
        if ct.get_action_cooldown() == 0:
            for d in CARD:
                q = pos.add(d)
                if not (0 <= q.x < w and 0 <= q.y < h):
                    continue
                try:
                    b = ct.get_tile_building_id(q)
                    if b is None or ct.get_team(b) == me:
                        continue
                    if not ct.can_fire(q):
                        continue
                    hp0 = ct.get_hp(b)
                    ct.fire(q)
                    self.hits += 1
                    if hp0 <= 2:
                        self.kills += 1
                    return
                except GameError:
                    continue

        if ct.get_move_cooldown() != 0:
            return

        # 2. walk to a stand tile next to the nearest visible enemy building
        goals = set()
        for b in ct.get_nearby_buildings():
            try:
                if ct.get_team(b) == me:
                    continue
                q = ct.get_position(b)
            except GameError:
                continue
            for d in CARD:
                s = q.add(d)
                if 0 <= s.x < w and 0 <= s.y < h:
                    goals.add((s.x, s.y))
        if goals:
            d = self._bfs(ct, pos, goals, w, h)
            if d is not None:
                try:
                    if ct.can_move(d):
                        ct.move(d)
                except GameError:
                    return
            return

        # 3. idle clear of our own ring so we never block it ourselves
        cheb = max(abs(pos.x - a[0]), abs(pos.y - a[1]))
        if cheb >= STAGE:
            return
        best = None
        for d in CARD:
            q = pos.add(d)
            if not (0 <= q.x < w and 0 <= q.y < h):
                continue
            c2 = max(abs(q.x - a[0]), abs(q.y - a[1]))
            if c2 <= cheb:
                continue
            try:
                if ct.can_move(d):
                    best = d
                    break
            except GameError:
                continue
        if best is not None:
            try:
                ct.move(best)
            except GameError:
                return

    def _bfs(self, ct, start, goals, w, h):
        seen = {(start.x, start.y): None}
        frontier = [(start.x, start.y)]
        for _ in range(40):
            nxt = []
            for (x, y) in frontier:
                for d in CARD:
                    dx, dy = d.delta()
                    n = (x + dx, y + dy)
                    if n in seen or not (0 <= n[0] < w and 0 <= n[1] < h):
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
            if not frontier:
                return None
        return None
