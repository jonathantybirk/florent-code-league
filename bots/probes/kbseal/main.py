"""Q7/Q8 KILL BOX: can a Builder Bot be sealed into a 1x1 pocket, and what happens to it?

Arena `lab/kboxopen` (16x12, no terrain, Core A anchor (2,5)).  Two builders:

    VICTIM  walks to CELL (6,5) and then does NOTHING for the rest of the game.
    JAILER  tours the OUTSIDE of the cell and lays four 3-Ti barriers on the cell's four
            orthogonal neighbours (6,4) (7,5) (6,6) (5,5) -- a builder moves cardinally only
            (G62) and barriers block movement, so four barriers is a complete seal.

CELL is 4 tiles from the Core anchor, so it stays inside CORE_VISION_RADIUS_SQ=36 and the Core can
read the victim's HP for the whole game.

The victim publishes, every round, through the 16-slot store (G20 -- module globals are not shared
between units, the store is; 1-round write lag):

    slot 2  = 1 + number of legal cardinal moves      (0 legal moves == sealed)
    slot 3  = 1 + 2*can_fire(an adjacent own barrier) + 4*(hp < max_hp)

so the Core can answer "is it sealed", "can it shoot its way out through its OWN barrier", and
"is it taking any damage from being enclosed".

The CORE reports (M07) HP / unit count / store flags sampled across 900 rounds, which answers:
does a sealed unit die, starve, sit forever -- and does it still count against MAX_TEAM_UNITS=50?
"""

from fcode import Controller, Direction, EntityType, GameError, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
CELL = Position(6, 5)
VSPAWN = Position(4, 5)
JSPAWN = Position(4, 4)
BARS = (Position(6, 4), Position(7, 5), Position(6, 6), Position(5, 5))
# (stand tile, barrier tile) in tour order; every stand tile is outside the cell and outside BARS
PLAN = ((Position(6, 3), Position(6, 4)),
        (Position(7, 4), Position(7, 5)),
        (Position(7, 6), Position(6, 6)),
        (Position(5, 6), Position(5, 5)))
VPATH = (Position(5, 5), Position(6, 5))
SAMPLES = (30, 60, 120, 300, 600, 900)
REPORT = 940


class Player:
    def __init__(self):
        self.n = []
        self.spawned = 0
        self.vid = -1
        self.step = 0
        self.vi = 0
        self.sealed = -1
        self.role = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + type(exc).__name__ + ":" + str(exc)[:16])

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            self._core(ct)
        elif et == EntityType.BUILDER_BOT:
            self._builder(ct)

    # ---------------- core ----------------
    def _core(self, ct):
        r = ct.get_current_round()
        if self.spawned == 0 and ct.can_spawn(VSPAWN):
            self.vid = ct.spawn_builder(VSPAWN)
            ct.write_store(0, self.vid + 1)
            self.spawned = 1
            return
        if self.spawned == 1 and ct.can_spawn(JSPAWN):
            ct.write_store(0, self.vid + 1)
            ct.spawn_builder(JSPAWN)
            self.spawned = 2
            return
        ct.write_store(0, self.vid + 1)

        if r in SAMPLES:
            hp = -1
            alive = 0
            try:
                hp = ct.get_hp(self.vid)
                alive = 1
            except GameError:
                alive = 0
            mv = ct.read_store(2) - 1
            fl = ct.read_store(3) - 1
            here = 0
            try:
                here = int(ct.get_tile_builder_bot_id(CELL) == self.vid)
            except GameError:
                here = 0
            if mv == 0 and self.sealed < 0:
                self.sealed = r
            self.n.append("%d:a%dhp%dmv%df%dc%d" % (r, alive, hp, mv, fl, here))

        if r == REPORT:
            nb = 0
            for b in BARS:
                try:
                    nb += int(ct.get_tile_building_id(b) is not None)
                except GameError:
                    continue
            ct.resign(("KB|seal=%d bars=%d/4 uc=%d ti=%d %s" % (
                self.sealed, nb, ct.get_unit_count(), ct.get_global_resources(),
                " ".join(self.n)))[:495])

    # ---------------- builders ----------------
    def _builder(self, ct):
        v = ct.read_store(0) - 1
        if v < 0:
            return
        if self.role == 0:
            self.role = 1 if ct.get_id() == v else 2
        if self.role == 1:
            self._victim(ct)
        else:
            self._jailer(ct)

    def _victim(self, ct):
        pos = ct.get_position()
        mv = 0
        for d in CARD:
            try:
                if ct.can_move(d):
                    mv += 1
            except GameError:
                continue
        fire = 0
        for b in BARS:
            if abs(b.x - pos.x) + abs(b.y - pos.y) != 1:
                continue
            try:
                if ct.can_fire(b):
                    fire = 1
            except GameError:
                continue
        hurt = 0
        try:
            hurt = int(ct.get_hp() < ct.get_max_hp())
        except GameError:
            hurt = 0
        ct.write_store(2, mv + 1)
        ct.write_store(3, 1 + 2 * fire + 4 * hurt)

        if self.vi < len(VPATH):
            tgt = VPATH[self.vi]
            if pos == tgt:
                self.vi += 1
                return
            try:
                d = pos.cardinal_direction_to(tgt)
                if ct.can_move(d):
                    ct.move(d)
            except GameError:
                return
        # at CELL: do nothing, ever

    def _jailer(self, ct):
        if self.step >= len(PLAN):
            return
        pos = ct.get_position()
        stand, bar = PLAN[self.step]
        if pos == stand:
            try:
                if ct.can_build_barrier(bar):
                    ct.build_barrier(bar)
                    self.step += 1
            except GameError:
                return
            return
        d = self._bfs(ct, pos, stand)
        if d is None:
            return
        try:
            if ct.can_move(d):
                ct.move(d)
        except GameError:
            return

    def _bfs(self, ct, start, goal):
        w, h = ct.get_map_width(), ct.get_map_height()
        banned = {(CELL.x, CELL.y)}
        for b in BARS:
            banned.add((b.x, b.y))
        seen = {(start.x, start.y): None}
        frontier = [(start.x, start.y)]
        for _ in range(40):
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
                    if n == (goal.x, goal.y):
                        cur = n
                        while seen[cur] is not None and seen[cur] != (start.x, start.y):
                            cur = seen[cur]
                        return start.cardinal_direction_to(Position(cur[0], cur[1]))
                    nxt.append(n)
            frontier = nxt
            if not frontier:
                return None
        return None
