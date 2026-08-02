"""Opponent for the AREA-2 team-blindness probes.

On arena `close` (14x11) Core B's anchor is (8,5).  Spawn one Builder Bot at (7,5) and have it
build a fixed set of buildings on known tiles, then sit still forever:

    (7,4) barrier     (6,5) conveyor facing EAST     (7,6) launcher

(6,5) is orthogonally adjacent to (5,5), which the probing bot can reach, so the probe has a real
ENEMY building to point can_destroy / can_heal / build / fire at.
"""

from fcode import Controller, Direction, EntityType, GameError, Position


class Player:
    def __init__(self):
        self.spawned = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if r == 0 and not self.spawned:
                p = Position(7, 5)
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return
        if r == 1:
            if ct.can_build_barrier(Position(7, 4)):
                ct.build_barrier(Position(7, 4))
            return
        if r == 2:
            if ct.can_build_conveyor(Position(6, 5), Direction.EAST):
                ct.build_conveyor(Position(6, 5), Direction.EAST)
            return
        if r == 3:
            if ct.can_build_launcher(Position(7, 6)):
                ct.build_launcher(Position(7, 6))
            return
        return
