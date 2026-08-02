"""Q7/Q8: seal an ENEMY Builder Bot into a 1x1 pocket and see whether the engine ever removes it.

Opponent must be `sit2`, which spawns exactly one Builder Bot on the first legal tile of its own
spawn ring and never moves it again.  On `lab/ringtight` (Core A (2,4), Core B (8,4)) that tile is
VICTIM (7,3), whose four orthogonal neighbours are (7,2) (6,3) (8,3) (7,4).

Our single builder tours the outside of that pocket and lays four barriers.  A Builder Bot moves
cardinally only (G62) and barriers block movement, so four barriers is a complete seal on an enemy
body just as much as on a friendly one -- nothing in can_build_barrier looks at whose unit is next
door (see `ringlock`, which builds on the enemy Core's own spawn ring).

Our CORE reports.  (7,3) is d^2=26 from anchor (2,4), inside CORE_VISION_RADIUS_SQ=36, so the Core
can watch the enemy body for the whole game.  Read `b_units` out of run_game's result dict to
confirm the trapped body is still occupying one of the opponent's 50 unit slots at the end.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

CARD = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
SPAWN = Position(4, 4)
VICTIM = Position(7, 3)
BARS = (Position(7, 2), Position(6, 3), Position(8, 3), Position(7, 4))
PLAN = ((Position(7, 1), Position(7, 2)),
        (Position(6, 2), Position(6, 3)),
        (Position(8, 2), Position(8, 3)),
        (Position(6, 4), Position(7, 4)))
SAMPLES = (20, 60, 120, 250, 400)
REPORT = 420


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.step = 0
        self.sealed = -1

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
            self._jailer(ct)

    def _core(self, ct):
        r = ct.get_current_round()
        if not self.spawned:
            if ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return

        nb = 0
        for b in BARS:
            try:
                nb += int(ct.get_tile_building_id(b) is not None)
            except GameError:
                continue
        if nb == 4 and self.sealed < 0:
            self.sealed = r

        if r in SAMPLES:
            vid = -1
            hp = -1
            try:
                v = ct.get_tile_builder_bot_id(VICTIM)
                if v is not None:
                    vid = v
                    hp = ct.get_hp(v)
            except GameError:
                vid = -2
            self.n.append("%d:v%dhp%db%d" % (r, vid, hp, nb))

        if r == REPORT:
            ct.resign(("KBE|seal=%d uc=%d ti=%d sc=%.0f %s" % (
                self.sealed, ct.get_unit_count(), ct.get_global_resources(),
                ct.get_scale_percent(), " ".join(self.n)))[:495])

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
        banned = {(VICTIM.x, VICTIM.y)}
        for b in BARS:
            banned.add((b.x, b.y))
        seen = {(start.x, start.y): None}
        frontier = [(start.x, start.y)]
        for _ in range(60):
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
