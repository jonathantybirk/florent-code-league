"""LAUNCHER Q6/Q7: CHAIN throws and the launcher FERRY, measured from the passenger.

Arena: maps/lab/glchain.map26 (30x12 open ground, cores (1,5)/(27,5)).
Run:   python tools/runprobe.py gl_chain2 --map lab/glchain --vs idle

Four Launchers on the lane y=4 at x = 7, 13, 19, 25, spaced SIX apart -- the
maximum, because a source tile is Chebyshev 1 from its Launcher and a target is
at most 5 tiles away (d^2<=26), so one Launcher moves a bot exactly +6.

Hop plan, all inside a single round because entities act in ascending id order
and the Launchers were built west to east:

    (6,4) --L(7,4)--> (12,4) --L(13,4)--> (18,4) --L(19,4)--> (24,4) --L(25,4)--> (29,4)

The BUILDER is the reporting unit (M07): it builds all four Launchers, then
shuttles back to (6,4) and rides the chain repeatedly, timing each trip.
"""

from fcode import Controller, Direction, EntityType, Position

LX = (7, 13, 19, 25)
LY = 4
START = Position(6, 4)
END = Position(29, 4)
SPAWN = Position(3, 4)
REPORT = 900

PLAN = (
    ("go", 7, 5), ("launcher", 7, 4),
    ("go", 13, 5), ("launcher", 13, 4),
    ("go", 19, 5), ("launcher", 19, 4),
    ("go", 25, 5), ("launcher", 25, 4),
    ("go", 26, 5), ("go", 26, 3), ("go", 6, 3),
)


class Player:
    def __init__(self):
        self.spawned = False
        self.k = 0
        self.nl = 0
        self.prev = None
        self.jumps = {}
        self.maxjump = 0
        self.trips = 0
        self.walkback = 0
        self.tripstart = -1
        self.triplen = []
        self.riding = False
        self.back = []
        self.bi = 0
        self.done = False
        self.built_at = -1
        self.jumpr = -1

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            try:
                ct.resign("gl_chain2 TOP %s:%s" % (type(exc).__name__, str(exc)[:40]))
            except Exception:
                pass

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct, r)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct)

    # ---- every launcher throws OUR builder six tiles east, once per round ----
    def _launcher(self, ct):
        me = ct.get_team()
        p = ct.get_position()
        src = Position(p.x - 1, LY)
        dst = Position(p.x + 5, LY)
        if dst.x >= ct.get_map_width():
            dst = Position(ct.get_map_width() - 1, LY)
        try:
            bid = ct.get_tile_builder_bot_id(src)
        except Exception:
            return
        if bid is None or ct.get_team(bid) != me:
            return
        if ct.can_launch(src, dst):
            ct.launch(src, dst)

    def _builder(self, ct, r):
        pos = ct.get_position()

        if r >= REPORT and not self.done:
            self.done = True
            jh = ",".join("%d:%d" % (k, v) for k, v in sorted(self.jumps.items())[:8])
            tl = ",".join(str(v) for v in self.triplen[:8])
            ct.resign(("CHAIN r%d nl=%d built=%d maxjump=%d trips=%d walkback=%d "
                       "at=%d,%d firstjump_r=%d JUMPS[%s] TRIPROUNDS[%s]") % (
                r, self.nl, self.built_at, self.maxjump, self.trips,
                self.walkback, pos.x, pos.y, self.jumpr, jh, tl)[:495])
            return

        if self.prev is not None:
            d = max(abs(pos.x - self.prev.x), abs(pos.y - self.prev.y))
            if d > 1:
                j = pos.x - self.prev.x
                self.jumps[j] = self.jumps.get(j, 0) + 1
                self.maxjump = max(self.maxjump, j)
                if self.jumpr < 0:
                    self.jumpr = r
                self.trips += 1
                self.triplen.append(r - self.tripstart if self.tripstart >= 0 else 0)
                self.tripstart = -1
                self.back = []
                self.bi = 0
        self.prev = pos

        if self.k < len(PLAN):
            if self.built_at < 0 and self.nl == len(LX):
                self.built_at = r
            op, x, y = PLAN[self.k]
            p = Position(x, y)
            if op == "go":
                if pos == p:
                    self.k += 1
                    return
                self._step(ct, pos, p)
                return
            if ct.can_build_launcher(p):
                ct.build_launcher(p)
                self.nl += 1
                self.k += 1
            return

        # --- shuttle: sit on START, get flung east, walk back along the y=3 lane ---
        if pos == START:
            if self.tripstart < 0:
                self.tripstart = r
            self.riding = True
            return
        if self.riding:
            self.riding = False
            self.triplen.append(r - self.tripstart)
            self.trips += 1
            self.tripstart = -1
            self.back = [Position(pos.x, 3), Position(START.x, 3), START]
            self.bi = 0
        if not self.back:
            self.back = [Position(pos.x, 3), Position(START.x, 3), START]
            self.bi = 0
        goal = self.back[self.bi]
        if pos == goal:
            if self.bi + 1 < len(self.back):
                self.bi += 1
                goal = self.back[self.bi]
            else:
                return
        self.walkback += 1
        self._step(ct, pos, goal)

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
