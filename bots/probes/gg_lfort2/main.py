"""AREA 1 / GobbleGlitch probe: DEFENSIVE LAUNCHER FORT, sited where rivals
actually stand.

gg_lfort put the Launcher on the Core ring tile nearest the map centre and
intercepted NOTHING: measured with gg_scout, rival builders do not come adjacent
to our Core, they stop 3-5 tiles out, because a Gunner only needs r^2<=13 (3
tiles in line) to reach a Core footprint tile.  The scout log's best launcher
tiles are consistently at Chebyshev 3-5 from our own footprint, toward the map
centre.  This version sites the Launcher there.

Roles are self-describing, so no store protocol and no plan agreement problem:
  * the GUNNER knows the cell: it is the tile it faces (get_direction()).
  * the LAUNCHER finds the cell by looking for our Gunner in its own vision.
  * only the Builder Bot holds the full plan, and freezes it once built.

Same skeleton as gg_scout otherwise (no economy, no offence, two builders), so
survival time is directly comparable.
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
        self.anchor = None
        self.L = None
        self.C = None
        self.G = None
        self.B = []
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

    # ---------- helpers ----------
    def _find_anchor(self, ct):
        if self.anchor is not None:
            return self.anchor
        me = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == me and ct.get_entity_type(bid) == EntityType.CORE:
                self.anchor = ct.get_position(bid)
                return self.anchor
        return None

    def _free(self, ct, q, w, h):
        if q.x < 0 or q.y < 0 or q.x >= w or q.y >= h:
            return False
        if not ct.is_in_vision(q):
            return False
        if not ct.is_tile_passable(q):
            return False
        return ct.get_tile_building_id(q) is None

    def _footdist(self, a, q):
        dx = min(abs(q.x - a.x), abs(q.x - a.x - 1))
        dy = min(abs(q.y - a.y), abs(q.y - a.y - 1))
        return max(dx, dy)

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
        a = self._find_anchor(ct)
        if a is None:
            return
        w = ct.get_map_width()
        h = ct.get_map_height()
        cen = Position(w // 2, h // 2)
        pos = ct.get_position()
        me = ct.get_team()

        # (re)acquire an existing launcher
        if self.L is None:
            for bid in ct.get_nearby_buildings():
                if ct.get_team(bid) == me and ct.get_entity_type(bid) == EntityType.LAUNCHER:
                    self.L = ct.get_position(bid)
                    break
        # phase A: site and build the launcher 3-4 tiles out, toward the centre
        if self.L is None or ct.get_tile_building_id(self.L) is None:
            best = None
            for dx in range(-5, 7):
                for dy in range(-5, 7):
                    q = Position(a.x + dx, a.y + dy)
                    fd = self._footdist(a, q)
                    if fd < 3 or fd > 4:
                        continue
                    if not self._free(ct, q, w, h):
                        continue
                    s = d2(q, cen)
                    if best is None or s < best[0]:
                        best = (s, q)
            if best is None:
                self._step(ct, pos, cen)
                return
            L = best[1]
            if abs(pos.x - L.x) + abs(pos.y - L.y) == 1:
                if ct.can_build_launcher(L):
                    print("LP|r%d LAUNCHER id=%d at %d,%d" % (
                        r, ct.build_launcher(L), L.x, L.y))
                    self.L = L
                return
            self._step(ct, pos, L)
            return
        # phase B: choose the cell, behind us, within throw range of the launcher
        if self.C is None:
            cell = None
            for dx in range(-6, 8):
                for dy in range(-6, 8):
                    q = Position(a.x + dx, a.y + dy)
                    dd = d2(self.L, q)
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
                self._step(ct, pos, self.L)
                return
            self.C = cell[1]
            nb = [Position(self.C.x + cx, self.C.y + cy) for cx, cy in CARD]
            nb.sort(key=lambda q: (d2(q, self.L), q.x, q.y))
            self.G = nb[0]
            self.B = nb[1:]
            print("LP|r%d PLAN L=%d,%d C=%d,%d G=%d,%d" % (
                r, self.L.x, self.L.y, self.C.x, self.C.y, self.G.x, self.G.y))
        # phase C: barriers from inside the cell, then the gunner facing it
        need = [b for b in self.B if ct.get_tile_building_id(b) is None]
        if need:
            if pos.x == self.C.x and pos.y == self.C.y:
                if ct.can_build_barrier(need[0]):
                    ct.build_barrier(need[0])
                return
            self._step(ct, pos, self.C)
            return
        if ct.get_tile_building_id(self.G) is None:
            if pos.x == self.C.x and pos.y == self.C.y:
                self._step(ct, pos, self.G)
                return
            if abs(pos.x - self.G.x) + abs(pos.y - self.G.y) == 1:
                dvec = (self.C.x - self.G.x, self.C.y - self.G.y)
                if ct.can_build_gunner(self.G, DIRC[dvec]):
                    print("LP|r%d GUNNER id=%d at %d,%d SEALED" % (
                        r, ct.build_gunner(self.G, DIRC[dvec]), self.G.x, self.G.y))
                return
            self._step(ct, pos, self.G)
            return
        # phase D: keep the fort alive
        for q in [self.L, self.G] + self.B:
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
        # the cell is the tile our own Gunner faces
        cell = None
        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) != me:
                continue
            if ct.get_entity_type(bid) != EntityType.GUNNER:
                continue
            g = ct.get_position(bid)
            dd = ct.get_direction(bid).delta()
            cell = Position(g.x + dd[0], g.y + dd[1])
            break
        if cell is not None and ct.get_tile_builder_bot_id(cell) is None:
            if ct.can_launch(victim, cell):
                ct.launch(victim, cell)
                self.throws += 1
                print("LP|r%d GOBBLE %d,%d -> %d,%d thr=%d" % (
                    r, victim.x, victim.y, cell.x, cell.y, self.throws))
                return
        a = self._find_anchor(ct)
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
        me = ct.get_team()
        p = ct.get_position()
        dd = ct.get_direction().delta()
        cell = Position(p.x + dd[0], p.y + dd[1])
        try:
            bid = ct.get_tile_builder_bot_id(cell)
        except Exception:
            return
        if bid is None or ct.get_team(bid) == me:
            return
        if not ct.can_fire(cell):
            return
        hp0 = ct.get_hp(bid)
        ct.fire(cell)
        self.shots += 1
        try:
            hp1 = ct.get_hp(bid)
            tail = "hp %d->%d" % (hp0, hp1)
        except Exception:
            tail = "hp %d->DEAD" % hp0
            self.kills += 1
        print("LP|r%d SHOT %s kills=%d shots=%d" % (r, tail, self.kills, self.shots))
