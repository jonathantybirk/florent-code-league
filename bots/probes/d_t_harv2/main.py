"""DEFENCE Q2 tiebreak fixture: TWO unconnected harvesters (see `d_t_harv` for the design).

Builds on the ore at (5,5) from ring tile (4,5) and then on the ore at (5,6) from (4,6).
Run against `d_t_harv` to check that the `harvesters` tiebreak compares COUNTS rather than
merely "has any".  Never resigns.
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
PLAN = (((4, 7), (4, 6), (4, 5)), Position(5, 5),
        ((4, 6),), Position(5, 6))


class Player:
    def __init__(self):
        self.spawned = False
        self.stage = 0
        self.leg = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(Position(4, 7)):
                ct.spawn_builder(Position(4, 7))
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT:
            return
        if self.stage >= 4:
            return
        p = ct.get_position()
        route = PLAN[self.stage]
        if self.leg < len(route):
            if (p.x, p.y) == route[self.leg]:
                self.leg += 1
                return
            t = route[self.leg]
            d = DIRS.get((t[0] - p.x, t[1] - p.y))
            if d is not None and ct.can_move(d):
                ct.move(d)
            return
        tgt = PLAN[self.stage + 1]
        if ct.get_tile_building_id(tgt) is not None:
            self.stage += 2
            self.leg = 0
            return
        if ct.can_build_harvester(tgt):
            ct.build_harvester(tgt)
            self.stage += 2
            self.leg = 0
