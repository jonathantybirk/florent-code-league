"""AREA 1 / GobbleGlitch probe: a map-general DEFENSIVE LAUNCHER FORT.

Same skeleton as gg_scout (no economy, no offence, two Builder Bots) so the two
are directly comparable: any change in survival time is attributable to the fort.

Runtime plan, derived from observed terrain only -- no atlas, no map names:
  L   Launcher on the Core ring tile nearest the map centre.  Enemy builders
      that come to kill our Core must stand next to it, i.e. inside L's
      measured r^2<=2 pickup ring.
  C   CELL: a tile behind the Core, all four cardinal neighbours free, within
      d^2<=26 of L (a legal throw target).
  G   GUNNER on one neighbour of C, facing C.  The other three neighbours get
      BARRIERs.  The cell's occupant then cannot move at all, and the cell is
      the FIRST tile of the Gunner's ray so nothing can block the shot.
      40 HP / 10 dmg = 4 shots = 8 Ti of ammo per enemy Builder Bot removed.
  Until the cell exists, the Launcher REWINDs instead: it throws the intruder to
  the legal target furthest from our Core.

Exfil: 'LP|' lines out of the .replay26.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

RING2 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
CARD = [(0, -1), (0, 1), (-1, 0), (1, 0)]
DIRC = {(0, -1): Direction.NORTH, (0, 1): Direction.SOUTH,
        (-1, 0): Direction.WEST, (1, 0): Direction.EAST}


def en(exc):
    return type(exc).__name__ + ":" + str(exc)[:24]


def d2(a, b):
    return (a.x - b.x) ** 2 + (a.y - b.y) ** 2


class Player:
    def __init__(self):
        self.spawned = 0
        self.role = None
        self.plan = None
        self.kills = 0
        self.throws = 0
        self.shots = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            print("LP|TOP %s" % en(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if r == 0:
                if ct.can_convert_ammo(150):
                    ct.convert_ammo(150)
                p = ct.get_position()
                print("LP|MAP w=%d h=%d core=%d,%d" % (
                    ct.get_map_width(), ct.get_map_height(), p.x, p.y))
            if self.spawned < 2 and r < 40:
                a = ct.get_position()
                for dx in (-1, 0, 1, 2):
                    for dy in (-1, 0, 1, 2):
                        q = Position(a.x + dx, a.y + dy)
                        if q.x < 0 or q.y < 0:
                            continue
                        if ct.can_spawn(q):
                            ct.spawn_builder(q)
                            self.spawned += 1
                            return
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct, r)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct, r)
            return
        if et == EntityType.GUNNER:
            self._gunner(ct, r)
            return

    # ---------- shared plan ----------
    def _anchor(self, ct):
        me = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == me and ct.get_entity_type(bid) == EntityType.CORE:
                return ct.get_position(bid)
        return None

    def _free(self, ct, q, w, h):
        if q.x < 0 or q.y < 0 or q.x >= w or q.y >= h:
            return False
        if not ct.is_in_vision(q):
            return False
        if not ct.is_tile_passable(q):
            return False
        return ct.get_tile_building_id(q) is None

    def _make_plan(self, ct):
        a = self._anchor(ct)
        if a is None:
            return None
        w = ct.get_map_width()
        h = ct.get_map_height()
        cen = Position(w // 2, h // 2)
        foot = [(a.x, a.y), (a.x + 1, a.y), (a.x, a.y + 1), (a.x + 1, a.y + 1)]
        best = None
        for dx in (-1, 0, 1, 2):
            for dy in (-1, 0, 1, 2):
                q = Position(a.x + dx, a.y + dy)
                if (q.x, q.y) in foot:
                    continue
                if not self._free(ct, q, w, h):
                    continue
                s = d2(q, cen)
                if best is None or s < best[0]:
                    best = (s, q)
        if best is None:
            return None
        L = best[1]
        cell = None
        for dx in range(-4, 6):
            for dy in range(-4, 6):
                q = Position(a.x + dx, a.y + dy)
                if (q.x, q.y) in foot:
                    continue
                dd = d2(L, q)
                if dd < 4 or dd > 26:
                    continue
                if not self._free(ct, q, w, h):
                    continue
                ok = True
                for cx, cy in CARD:
                    if not self._free(ct, Position(q.x + cx, q.y + cy), w, h):
                        ok = False
                        break
                if not ok:
                    continue
                s = d2(q, cen)
                if cell is None or s > cell[0]:
                    cell = (s, q)
        if cell is None:
            return (L, None, None, [])
        C = cell[1]
        nb = [Position(C.x + cx, C.y + cy) for cx, cy in CARD]
        nb.sort(key=lambda q: (d2(q, L), q.x, q.y))
        return (L, C, nb[0], nb[1:])

    # ---------- builder ----------
    def _builder(self, ct, r):
        if self.role is None:
            v = ct.read_store(0)
            if v == 0:
                ct.write_store(0, ct.get_id())
                return
            self.role = "fort" if v == ct.get_id() else "idle"
        if self.role == "idle":
            return
        if self.plan is None:
            self.plan = self._make_plan(ct)
            if self.plan is None:
                return
            L, C, G, B = self.plan
            print("LP|PLAN L=%d,%d C=%s G=%s" % (
                L.x, L.y,
                "-" if C is None else "%d,%d" % (C.x, C.y),
                "-" if G is None else "%d,%d" % (G.x, G.y)))
        L, C, G, B = self.plan
        pos = ct.get_position()
        if ct.get_tile_building_id(L) is None:
            if abs(pos.x - L.x) + abs(pos.y - L.y) == 1:
                if ct.can_build_launcher(L):
                    print("LP|r%d LAUNCHER id=%d at %d,%d" % (
                        r, ct.build_launcher(L), L.x, L.y))
                return
            self._step(ct, pos, L)
            return
        if C is None:
            return
        need = [b for b in B if ct.get_tile_building_id(b) is None]
        if need:
            if pos.x == C.x and pos.y == C.y:
                if ct.can_build_barrier(need[0]):
                    ct.build_barrier(need[0])
                return
            self._step(ct, pos, C)
            return
        if ct.get_tile_building_id(G) is None:
            if pos.x == C.x and pos.y == C.y:
                self._step(ct, pos, G)
                return
            if abs(pos.x - G.x) + abs(pos.y - G.y) == 1:
                dvec = (C.x - G.x, C.y - G.y)
                if ct.can_build_gunner(G, DIRC[dvec]):
                    print("LP|r%d GUNNER id=%d at %d,%d SEALED" % (
                        r, ct.build_gunner(G, DIRC[dvec]), G.x, G.y))
                return
            self._step(ct, pos, G)
            return
        for q in [L, G] + B:
            if abs(pos.x - q.x) + abs(pos.y - q.y) != 1:
                continue
            bid = ct.get_tile_building_id(q)
            if bid is not None and ct.get_hp(bid) < ct.get_max_hp(bid):
                if ct.can_heal(q):
                    ct.heal(q)
                    return

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
        opts += [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]
        for d in opts:
            if ct.can_move(d):
                ct.move(d)
                return

    # ---------- launcher ----------
    def _launcher(self, ct, r):
        if self.plan is None:
            self.plan = self._make_plan(ct)
            if self.plan is None:
                return
        L, C, G, B = self.plan
        me = ct.get_team()
        pos = ct.get_position()
        victim = None
        for dx, dy in RING2:
            q = Position(pos.x + dx, pos.y + dy)
            if q.x < 0 or q.y < 0:
                continue
            try:
                bid = ct.get_tile_builder_bot_id(q)
            except Exception:
                continue
            if bid is None or ct.get_team(bid) == me:
                continue
            victim = q
            break
        if victim is None:
            return
        sealed = C is not None and G is not None and ct.get_tile_building_id(G) is not None
        if sealed and ct.get_tile_builder_bot_id(C) is None and ct.can_launch(victim, C):
            ct.launch(victim, C)
            self.throws += 1
            print("LP|r%d GOBBLE %d,%d -> cell thr=%d" % (r, victim.x, victim.y, self.throws))
            return
        a = self._anchor(ct)
        if a is None:
            a = pos
        cands = []
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                dd = dx * dx + dy * dy
                if dd < 16 or dd > 26:
                    continue
                q = Position(pos.x + dx, pos.y + dy)
                if q.x < 0 or q.y < 0:
                    continue
                cands.append((-d2(q, a), q.x, q.y, q))
        cands.sort()
        tried = 0
        for _, _, _, q in cands:
            if tried >= 6:
                break
            tried += 1
            try:
                ok = ct.can_launch(victim, q)
            except Exception:
                continue
            if ok:
                ct.launch(victim, q)
                self.throws += 1
                print("LP|r%d REWIND %d,%d -> %d,%d thr=%d" % (
                    r, victim.x, victim.y, q.x, q.y, self.throws))
                return

    # ---------- gunner ----------
    def _gunner(self, ct, r):
        if self.plan is None:
            self.plan = self._make_plan(ct)
            if self.plan is None:
                return
        L, C, G, B = self.plan
        if C is None:
            return
        me = ct.get_team()
        try:
            bid = ct.get_tile_builder_bot_id(C)
        except Exception:
            return
        if bid is None or ct.get_team(bid) == me:
            return
        if not ct.can_fire(C):
            return
        hp0 = ct.get_hp(bid)
        ct.fire(C)
        self.shots += 1
        try:
            hp1 = ct.get_hp(bid)
            tail = "hp %d->%d" % (hp0, hp1)
        except Exception:
            tail = "hp %d->DEAD" % hp0
            self.kills += 1
        print("LP|r%d SHOT %s kills=%d shots=%d" % (r, tail, self.kills, self.shots))
