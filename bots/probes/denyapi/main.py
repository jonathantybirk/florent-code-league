"""AREA-2 probe: what counts toward MAX_TEAM_UNITS, and what destroy() actually costs.

Reported from the Builder Bot (M07: only one unit can report).

  D1  get_unit_count() baseline and after each build type -> which entities count as "units".
  D2  does destroying our own building lower get_scale_percent()?  (cost-scale monotonicity)
  D3  destroy() "does not cost action cooldown" -- can we destroy AND build in the same turn?
  D4  does destroy() refund titanium?
"""

from fcode import Controller, Direction, EntityType, GameError, Position


def e(exc):
    return type(exc).__name__ + ":" + str(exc)[:18]


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
                p = Position(3, 9)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned = True
            return

        if et != EntityType.BUILDER_BOT:
            return

        if r == 1:
            self.n.append("D1 base uc=%d sc=%.0f ti=%d" % (
                ct.get_unit_count(), ct.get_scale_percent(), ct.get_global_resources()))
            ct.move(Direction.EAST)
            return
        if r == 2:
            ct.move(Direction.EAST)
            return

        # builder now at (5,9); free orthogonal neighbours (4,9) (6,9) (5,8) (5,10)
        if r == 3:
            ct.build_barrier(Position(5, 8))
            self.n.append("bar uc=%d sc=%.0f" % (ct.get_unit_count(), ct.get_scale_percent()))
            return
        if r == 4:
            ct.build_conveyor(Position(4, 9), Direction.EAST)
            self.n.append("cnv uc=%d sc=%.0f" % (ct.get_unit_count(), ct.get_scale_percent()))
            return
        if r == 5:
            ct.build_gunner(Position(6, 9), Direction.EAST)
            self.n.append("gun uc=%d sc=%.0f" % (ct.get_unit_count(), ct.get_scale_percent()))
            return
        if r == 6:
            ct.build_launcher(Position(5, 10))
            self.n.append("lau uc=%d sc=%.0f" % (ct.get_unit_count(), ct.get_scale_percent()))
            return

        if r == 7:
            b = Position(5, 8)
            self.n.append("D2 pre sc=%.0f ti=%d cd=%s cdes=%s" % (
                ct.get_scale_percent(), ct.get_global_resources(),
                ct.get_action_cooldown(), ct.can_destroy(b)))
            ct.destroy(b)
            self.n.append("post sc=%.0f ti=%d cd=%s" % (
                ct.get_scale_percent(), ct.get_global_resources(), ct.get_action_cooldown()))
            # D3: can we still act this turn?
            try:
                ct.build_barrier(b)
                self.n.append("D3 rebuild SAME turn OK ti=%d uc=%d" % (
                    ct.get_global_resources(), ct.get_unit_count()))
            except Exception as exc:
                self.n.append("D3 " + e(exc))
            return

        if r == 8:
            # destroy the gunner: does a turret leaving lower the unit count?
            g = Position(6, 9)
            try:
                ct.destroy(g)
                self.n.append("D1b gundes uc=%d sc=%.0f" % (
                    ct.get_unit_count(), ct.get_scale_percent()))
            except Exception as exc:
                self.n.append("D1b " + e(exc))
            ct.resign(" | ".join(self.n)[:495])
            return
