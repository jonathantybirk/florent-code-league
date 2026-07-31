"""Probe G48 / G49 with the LAUNCHER itself as reporter.

The first `launcher` probe lost its scan because the Launcher and the Builder run in separate
sub-interpreters (G20) and the Builder did the resigning. Here the Launcher reports.

Arena `close` (14x11) vs the `sitter` opponent:
  our Core A anchor (1,5); our builder parks at (5,5) and builds a Launcher at (6,5).
  the enemy Core B anchor (8,5) spawns ONE enemy builder at (7,5) -- orthogonally adjacent
  to our Launcher.

  L1 legal-target set vs {in-bounds, bot-passable, d^2 <= 26 from the Launcher}
  L5 can_launch() on the ENEMY builder at (7,5) -- is pickup still team-blind? (G49)
  L6 pickup radius: is our own builder at (5,5) (d^2=1) also launchable?
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(5, 5)
LAUNCH = Position(6, 5)
ENEMY = Position(7, 5)


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:24]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.built = False
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 5)):
                ct.spawn_builder(Position(3, 5))
                self.spawned = True
            return
        if et == EntityType.BUILDER_BOT:
            if self.built:
                return
            pos = ct.get_position()
            if pos != HOME:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                return
            if ct.can_build_launcher(LAUNCH):
                ct.build_launcher(LAUNCH)
                self.built = True
            return
        if et != EntityType.LAUNCHER or self.done:
            return

        # Give the enemy time to spawn and settle.
        if ct.get_current_round() < 12:
            return
        self.done = True
        lp = ct.get_position()

        ebid = ct.get_tile_builder_bot_id(ENEMY)
        eteam = "none" if ebid is None else str(ct.get_team(ebid))
        self.n.append("L5 enemybot_at_7_5=%s team=%s mine=%s" % (
            ebid is not None, eteam, ct.get_team()))

        legal = []
        expect = 0
        for dy in range(-6, 7):
            for dx in range(-6, 7):
                q = Position(lp.x + dx, lp.y + dy)
                if not (0 <= q.x < ct.get_map_width() and 0 <= q.y < ct.get_map_height()):
                    continue
                d2 = dx * dx + dy * dy
                try:
                    ok = ct.can_launch(ENEMY, q)
                except Exception:
                    ok = False
                try:
                    passable = ct.is_tile_passable(q)
                except Exception:
                    passable = False
                if d2 <= 26 and passable:
                    expect += 1
                if ok:
                    legal.append(d2)
        self.n.append("L5 ENEMY legal=%d expect=%d maxd2=%s" % (
            len(legal), expect, max(legal) if legal else -1))

        own = [1 for dy in range(-6, 7) for dx in range(-6, 7)
               if 0 <= lp.x + dx < ct.get_map_width()
               and 0 <= lp.y + dy < ct.get_map_height()
               and ct.can_launch(HOME, Position(lp.x + dx, lp.y + dy))]
        self.n.append("L6 OWN legal=%d" % len(own))
        ct.resign(" | ".join(self.n[:6]))
