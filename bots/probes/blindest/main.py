"""AREA-2 probe: is destroy() / heal() / build() team-blind the way the turret APIs are?

Opponent `ebuild` puts an ENEMY conveyor on (6,5) of arena `close`.  Our builder parks on (5,5),
orthogonally adjacent to it, and asks every question we can ask of an enemy building.

  B1  can_destroy / destroy on an ENEMY building
  B2  can_heal on an ENEMY building
  B3  can_build_* on a tile an ENEMY building occupies
  B4  builder attack on an enemy building -- damage, cost, and whether scale moves
  B5  is an ENEMY conveyor passable to our builder? (G61 says friendly conveyors are)
"""

from fcode import Controller, Direction, EntityType, GameError, Position


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:16]


class Player:
    def __init__(self):
        self.n = []
        self.spawned = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.n.append("TOP:" + e(exc))

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

        if et == EntityType.CORE:
            if r == 0 and not self.spawned:
                p = Position(3, 5)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned = True
            return

        if et != EntityType.BUILDER_BOT:
            return

        tgt = Position(6, 5)

        if r in (1, 2):
            if ct.can_move(Direction.EAST):
                ct.move(Direction.EAST)
            return

        if r == 4:
            bid = None
            try:
                bid = ct.get_tile_building_id(tgt)
            except Exception as exc:
                self.n.append("bid " + e(exc))
            tm = "?"
            if bid is not None:
                try:
                    tm = str(ct.get_team(bid))[-1]
                except Exception as exc:
                    tm = e(exc)
            self.n.append("B0 bid=%s team=%s mine=%s pass=%s" % (
                bid, tm, str(ct.get_team())[-1], ct.is_tile_passable(tgt)))
            try:
                self.n.append("B1 cdes=%s" % ct.can_destroy(tgt))
            except Exception as exc:
                self.n.append("B1 cdes " + e(exc))
            try:
                ct.destroy(tgt)
                self.n.append("B1 DESTROYED ENEMY")
            except Exception as exc:
                self.n.append("B1 des " + e(exc))
            return

        if r == 5:
            try:
                self.n.append("B2 cheal=%s" % ct.can_heal(tgt))
            except Exception as exc:
                self.n.append("B2 " + e(exc))
            try:
                self.n.append("B3 cbar=%s ccnv=%s" % (
                    ct.can_build_barrier(tgt),
                    ct.can_build_conveyor(tgt, Direction.EAST)))
            except Exception as exc:
                self.n.append("B3 " + e(exc))
            return

        if r == 6:
            hp0 = ti0 = sc0 = -1
            try:
                hp0 = ct.get_hp(ct.get_tile_building_id(tgt))
            except Exception:
                hp0 = -1
            ti0 = ct.get_global_resources()
            sc0 = ct.get_scale_percent()
            try:
                self.n.append("B4 cfire=%s" % ct.can_fire(tgt))
                ct.fire(tgt)
                hp1 = ct.get_hp(ct.get_tile_building_id(tgt))
                self.n.append("B4 hp %s->%s dTi=%d sc %.0f->%.0f" % (
                    hp0, hp1, ct.get_global_resources() - ti0, sc0, ct.get_scale_percent()))
            except Exception as exc:
                self.n.append("B4 " + e(exc))
            return

        if r == 7:
            self.n.append("B5 moveE=%s" % ct.can_move(Direction.EAST))
            ct.resign(" | ".join(self.n)[:495])
            return
