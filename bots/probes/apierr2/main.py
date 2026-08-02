"""Silent-failure hunt, round two: the cases `apierr` could not reach because it had no real targets.

`apierr` fired 30 illegal calls at empty ground and every one raised GameError.  The dangerous cases
are the ones where a call is *nearly* legal -- a real friendly building at full HP, a rotate to the
direction the turret already faces, a generic build() missing its Direction, a destroy() on a round
we already spent.  Those are where an engine is most likely to return normally while doing nothing,
and a bot that believes it acted is a bot one round out of step with the board forever after.

  E1  heal() a friendly building already at FULL HP -- raise, or 1 Ti for nothing?
  E2  rotate() a Gunner to the direction it ALREADY faces -- raise, or 10 Ti for nothing?
      (Relayed through store slot 2: only the Gunner can rotate itself, and its notes are invisible
      to the reporting builder -- M07.  Encoding: 10000*(2 if no raise else 1) + 100*can_rotate
      + 10*(facing unchanged) + titanium spent.)
  E3  build(EntityType.CONVEYOR, pos) with extra=None -- raise, or a silently-defaulted facing?
  E4  build(EntityType.CORE, pos) -- an EntityType that is not buildable.
  E5  destroy() on a round where we have ALREADY built (action cooldown 1), against a real, adjacent,
      allied building.  The stub says destroy costs no cooldown; does it actually still work?
  E6  destroy() on a round where we have already MOVED, against a real adjacent allied building.
  E7  the can_act() trap: right after a move, read action cooldown / can_act() / can_build_barrier(),
      then actually attempt the build.
  E8  two destroy() calls in the same round -- the docs say destroy is unlimited per turn.
  E9  two write_store() calls to the same slot in the same round -- which one lands?

Arena `scal` (24x20, Core A anchor (1,9), ore at (6,8) and (6,10), open elsewhere).
Reported through ct.resign() (G29), under the 500-char cap (M06).
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(6, 9)
UP = Position(6, 7)
W9 = Position(5, 9)      # allied barrier #1, WEST of HOME
W7 = Position(5, 7)      # allied barrier #2, WEST of UP
E7 = Position(7, 7)      # allied barrier #3, EAST of UP
GUN = Position(7, 9)     # the Gunner, EAST of HOME


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.ph = 0
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("T:" + type(exc).__name__)

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(3, 9)):
                ct.spawn_builder(Position(3, 9))
                self.spawned = True
            return
        if et == EntityType.GUNNER:
            if self.ph == 0:
                self.ph = 1
                ti = ct.get_global_resources()
                face = ct.get_direction()
                cr = 1 if self.safe(ct.can_rotate, face) is True else 0
                k = self.k(lambda: ct.rotate(face))
                same = 1 if ct.get_direction() == face else 0
                ct.write_store(2, 10000 * (2 if k == "N" else 1) + 100 * cr + 10 * same
                               + min(9, ti - ct.get_global_resources()))
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        pos = ct.get_position()

        if self.ph == 0:
            if pos != HOME:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                return
            self.ph = 1
            return

        if self.ph == 1:                       # allied barrier + the Gunner that E2 needs
            self.ph = 2
            ct.build_barrier(W9)
            return
        if self.ph == 2:
            self.ph = 3
            ct.build_gunner(GUN, Direction.EAST)
            return

        if self.ph == 3:                       # E1 / E3 / E4 against real targets
            self.ph = 4
            ti = ct.get_global_resources()
            bid = ct.get_tile_building_id(W9)
            self.n.append("E1 hp%d/%d ch=%s r=%s dTi=%d" % (
                ct.get_hp(bid), ct.get_max_hp(bid), self.safe(ct.can_heal, W9),
                self.k(lambda: ct.heal(W9)), ct.get_global_resources() - ti))
            self.n.append("E3=" + self.k(lambda: ct.build(EntityType.CONVEYOR, Position(6, 10))))
            self.n.append("E4=" + self.k(lambda: ct.build(EntityType.CORE, Position(6, 10))))
            return

        if self.ph == 4:                       # walk two north, keeping W9 for E6
            if pos != UP:
                d = pos.cardinal_direction_to(UP)
                if ct.can_move(d):
                    ct.move(d)
                return
            self.ph = 5
            return

        if self.ph == 5:
            self.ph = 6
            ct.build_barrier(W7)
            return
        if self.ph == 6:
            self.ph = 7
            ct.build_barrier(E7)               # sets action cooldown to 1 this round
            self.n.append("E5 acd=%d cd=%s r=%s gone=%s" % (
                ct.get_action_cooldown(), self.safe(ct.can_destroy, W7),
                self.k(lambda: ct.destroy(W7)),
                ct.get_tile_building_id(W7) is None))
            self.n.append("E8=" + self.k(lambda: ct.destroy(E7)))
            self.n.append("E9=" + self.k(lambda: (ct.write_store(1, 5), ct.write_store(1, 9))[0]))
            return

        if self.ph == 7:                       # E6 / E7: move south, then act
            self.ph = 8
            mv = self.k(lambda: ct.move(Direction.SOUTH))
            self.n.append("E7 mv=%s acd=%d mcd=%d act=%s cb=%s b=%s" % (
                mv, ct.get_action_cooldown(), ct.get_move_cooldown(), ct.can_act(),
                self.safe(ct.can_build_barrier, Position(7, 8)),
                self.k(lambda: ct.build_barrier(Position(7, 8)))))
            return

        if self.ph == 8:                       # now at (6,8); W9 is diagonal, so step to HOME first
            if pos != HOME:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                    self.n.append("E6 mv acd=%d cd=%s r=%s gone=%s" % (
                        ct.get_action_cooldown(), self.safe(ct.can_destroy, W9),
                        self.k(lambda: ct.destroy(W9)),
                        ct.get_tile_building_id(W9) is None))
                    self.ph = 9
                return
            self.ph = 9
            return

        if self.ph == 9:
            self.done = True
            self.n.append("E9r=%d E2relay=%d" % (ct.read_store(1), ct.read_store(2)))
            ct.resign("ERR2|" + "|".join(self.n))

    def safe(self, fn, arg):
        try:
            return fn(arg)
        except GameError:
            return "GE"

    def k(self, fn):
        try:
            fn()
            return "N"
        except GameError:
            return "R"
        except TypeError:
            return "T"
        except ValueError:
            return "V"
