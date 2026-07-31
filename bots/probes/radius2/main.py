"""Follow-up to `radius`: is the builder's ATTACK / HEAL / DESTROY radius orthogonal-only too?

`radius` proved BUILD is orthogonal-only and that an orthogonally adjacent shot works
(2 dmg for 2 Ti) while the own-tile shot is illegal. Its FIRE/HEAL grids were all-zero only
because nothing targetable or damaged existed yet. This probe supplies real targets.

Plan on `openfield`, builder homing to (6,9):
  build barrier E at (7,9); step NORTH to (6,8) so that barrier is now DIAGONAL (+1,+1);
  test can_fire/fire on it diagonally; build a second barrier orthogonally at (7,8);
  damage it, then compare can_heal orthogonal vs diagonal; same for can_destroy.
"""

from fcode import Controller, Direction, EntityType, GameError, Position

HOME = Position(6, 9)
B_DIAG = Position(7, 9)   # orthogonal from (6,9), diagonal from (6,8)
B_ORTH = Position(7, 8)   # orthogonal from (6,8)
UP = Position(6, 8)


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:26]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False
        self.ph = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned:
                p = Position(3, 9)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return

        pos = ct.get_position()

        if self.ph == 0:
            if pos != HOME:
                d = pos.cardinal_direction_to(HOME)
                if ct.can_move(d):
                    ct.move(d)
                return
            ct.build_barrier(B_DIAG)
            self.ph = 1
            return

        if self.ph == 1:
            if ct.can_move(Direction.NORTH):
                ct.move(Direction.NORTH)
                self.ph = 2
            return

        if self.ph == 2:   # now at (6,8); B_DIAG is at (+1,+1)
            self.ph = 3
            self.n.append("at %d,%d" % (pos.x, pos.y))
            self.n.append("DIAG canfire=%s" % ct.can_fire(B_DIAG))
            try:
                ct.fire(B_DIAG)
                self.n.append("DIAGFIRE ok hp=%d" % ct.get_hp(ct.get_tile_building_id(B_DIAG)))
            except Exception as exc:
                self.n.append("DIAGFIRE " + e(exc))
            return

        if self.ph == 3:
            self.ph = 4
            ct.build_barrier(B_ORTH)
            return

        if self.ph == 4:   # damage the orthogonal barrier
            self.ph = 5
            ct.fire(B_ORTH)
            self.n.append("ORTHFIRE ok hp=%d" % ct.get_hp(ct.get_tile_building_id(B_ORTH)))
            return

        if self.ph == 5:
            self.ph = 6
            self.n.append("HEAL orth=%s diag=%s self=%s" % (
                ct.can_heal(B_ORTH), ct.can_heal(B_DIAG), ct.can_heal(pos)))
            self.n.append("DESTROY orth=%s diag=%s" % (
                ct.can_destroy(B_ORTH), ct.can_destroy(B_DIAG)))
            return

        if self.ph == 6:
            self.ph = 7
            hp0 = ct.get_hp(ct.get_tile_building_id(B_ORTH))
            ti0 = ct.get_global_resources()
            try:
                ct.heal(B_ORTH)
                self.n.append("HEALdo hp %d->%d dTi=%d" % (
                    hp0, ct.get_hp(ct.get_tile_building_id(B_ORTH)),
                    ct.get_global_resources() - ti0))
            except Exception as exc:
                self.n.append("HEALdo " + e(exc))
            return

        ct.resign(" | ".join(self.n[:10]))
