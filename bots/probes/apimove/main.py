"""Movement: speed, diagonals, cooldowns, and the act/move exclusivity rule.

Everything a distance heuristic depends on, measured on arena `scal` (24x20, Core A anchor (1,9),
open ground along row y=9) from a builder spawned at (3,9):

  M1  can_move() for all 9 Directions on open ground -- are diagonals legal?
  M2  move(NORTHEAST) -- raise or silent no-op?
  M3  speed: walk EAST for 8 consecutive rounds and count tiles gained per round.
  M4  a second move() in the same round -- raise or silent no-op?
  M5  move cooldown / action cooldown immediately after a move.
  M6  act-then-move: build a barrier, then can_move / move in the SAME round.
  M7  move-then-act: move, then can_build_barrier / build_barrier in the SAME round.
  M8  Direction.CENTRE as a "stay put" move -- legal, or a raise?

Reported through ct.resign() (G29); under the 500-char cap (M06).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

START = Position(3, 9)
D9 = ((Direction.NORTH, "N"), (Direction.NORTHEAST, "NE"), (Direction.EAST, "E"),
      (Direction.SOUTHEAST, "SE"), (Direction.SOUTH, "S"), (Direction.SOUTHWEST, "SW"),
      (Direction.WEST, "W"), (Direction.NORTHWEST, "NW"), (Direction.CENTRE, "C"))


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.ph = 0
        self.track = []
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T:" + type(exc).__name__)

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(START):
                ct.spawn_builder(START)
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        pos = ct.get_position()
        r = ct.get_current_round()

        # M1 + M2: legality of every direction on open ground, before anything else happens.
        if self.ph == 0:
            self.ph = 1
            self.n.append("M1=" + "".join(
                ("1" if self.safe(ct.can_move, d) else "0") for d, _ in D9))
            self.n.append("M2diag=" + self.act(ct, lambda: ct.move(Direction.NORTHEAST)))
            self.n.append("M8ctr=" + self.act(ct, lambda: ct.move(Direction.CENTRE)))
            self.n.append("at%d,%d" % (ct.get_position().x, ct.get_position().y))
            return

        # M3: eight straight EAST steps, recording position every round.
        if self.ph == 1:
            self.track.append((r, pos.x))
            if len(self.track) >= 9:
                self.ph = 2
                d = [self.track[i + 1][1] - self.track[i][1] for i in range(len(self.track) - 1)]
                dr = [self.track[i + 1][0] - self.track[i][0] for i in range(len(self.track) - 1)]
                self.n.append("M3 dx=%s dr=%s" % ("".join(str(v) for v in d),
                                                  "".join(str(v) for v in dr)))
                return
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
                # M4/M5, measured on the very first step only.
                if len(self.track) == 1:
                    self.n.append("M5 mcd=%d acd=%d canact=%s canmoveE=%s" % (
                        ct.get_move_cooldown(), ct.get_action_cooldown(),
                        ct.can_act(), ct.can_move(Direction.EAST)))
                    self.n.append("M4 2nd=" + self.act(ct, lambda: ct.move(Direction.EAST)))
            return

        # M6: build, then try to move in the same round.
        if self.ph == 2:
            self.ph = 3
            t = Position(pos.x, pos.y - 1)
            self.n.append("M6 pre_cm=%s" % self.safe(ct.can_move, Direction.SOUTH))
            ct.build_barrier(t)
            self.n.append("M6 post acd=%d mcd=%d cm=%s mv=%s" % (
                ct.get_action_cooldown(), ct.get_move_cooldown(),
                self.safe(ct.can_move, Direction.SOUTH),
                self.act(ct, lambda: ct.move(Direction.SOUTH))))
            return

        # M7: move, then try to build in the same round.
        if self.ph == 3:
            self.ph = 4
            t = Position(pos.x, pos.y + 2)
            mv = self.act(ct, lambda: ct.move(Direction.SOUTH))
            self.n.append("M7 mv=%s cb=%s bld=%s" % (
                mv, self.safe(ct.can_build_barrier, t),
                self.act(ct, lambda: ct.build_barrier(t))))
            return

        if self.ph == 4:
            self.done = True
            ct.resign("MOVE|" + "|".join(self.n))

    def safe(self, fn, arg):
        try:
            return fn(arg)
        except GameError:
            return "GE"

    def act(self, ct, fn):
        """'ok' if the call returned, 'GE' if it raised GameError."""
        try:
            fn()
            return "ok"
        except GameError:
            return "GE"
