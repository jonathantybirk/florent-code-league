"""Probe G48 / G46 on 2.3.3: Launcher throw geometry and whether the arc still clears walls.

Arena `wallgap` (24x20): a solid wall column at x=10, rows 3..16. Core A anchor (1,9).
Builder parks at (8,9) and builds a Launcher at (9,9), so the wall is immediately east of the
Launcher and every eastern target is on the far side of it.

  L1 the legal-target set: does it equal {in-bounds, bot-passable, dx^2+dy^2 <= 26 from the LAUNCHER}?
  L2 are targets BEYOND the wall legal (i.e. does the throw arc over it)?
  L3 can a wall tile itself be a target?
  L4 does the thrown bot actually land where it was sent?
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(8, 9)
LAUNCH = Position(9, 9)
FAR = Position(14, 9)      # dx=5 from launcher -> d^2=25 <= 26, and 4 tiles past the wall


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:20]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.built = False
        self.scanned = False
        self.launched = False
        self.landed = None

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
                self.spawned = True
            return
        if et == EntityType.BUILDER_BOT:
            self._builder(ct)
            return
        if et == EntityType.LAUNCHER:
            self._launcher(ct)

    def _builder(self, ct):
        pos = ct.get_position()
        if not self.built:
            if pos != HOME:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                return
            if ct.can_build_launcher(LAUNCH):
                ct.build_launcher(LAUNCH)
                self.built = True
            return
        # After the throw, report where we ended up.
        if self.landed is None and pos != HOME:
            self.landed = (pos.x, pos.y)
            ct.resign("L4 bot landed at %d,%d (sent to %d,%d) | %s" % (
                pos.x, pos.y, FAR.x, FAR.y, " | ".join(self.n[:6])))

    def _launcher(self, ct):
        if not self.scanned:
            self.scanned = True
            lp = ct.get_position()
            legal = []
            expect = 0
            wallhit = "n/a"
            for dy in range(-6, 7):
                for dx in range(-6, 7):
                    q = Position(lp.x + dx, lp.y + dy)
                    if not (0 <= q.x < ct.get_map_width() and 0 <= q.y < ct.get_map_height()):
                        continue
                    d2 = dx * dx + dy * dy
                    try:
                        ok = ct.can_launch(HOME, q)
                    except Exception:
                        ok = False
                    try:
                        passable = ct.is_tile_passable(q)
                    except Exception:
                        passable = False
                    if d2 <= 26 and passable:
                        expect += 1
                    if ok:
                        legal.append((q.x, q.y, d2))
                    if q.x == 10 and q.y == 9 and d2 <= 26:
                        wallhit = str(ok)
            beyond = sum(1 for (x, y, d2) in legal if x > 10)
            maxd2 = max([d2 for (_, _, d2) in legal]) if legal else -1
            self.n.append("L1 legal=%d expect=%d maxd2=%d" % (len(legal), expect, maxd2))
            self.n.append("L2 beyondwall=%d" % beyond)
            self.n.append("L3 walltile_target=%s" % wallhit)
            return
        if not self.launched:
            self.launched = True
            try:
                ct.launch(HOME, FAR)
                self.n.append("L4 launch ok")
            except Exception as exc:
                self.n.append("L4 launch " + e(exc))
                ct.resign(" | ".join(self.n[:6]))
