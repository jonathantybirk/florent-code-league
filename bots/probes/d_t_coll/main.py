"""DEFENCE Q2 tiebreak fixture: ONE harvester that actually SCORES.

Arena `maps/lab/dore.map26`.  Core A footprint (2,5)(3,5)(2,6)(3,6); ore at (5,5).
The gap tile (4,5) is a Core spawn-ring tile, so a single CONVEYOR at (4,5) pointing WEST
delivers straight onto the Core footprint -- the shortest scoring chain the game allows (G02).

Builder: spawn (4,6) -> build conveyor (4,5) WEST -> step NORTH onto the conveyor (G61 says
builders stand on conveyors) -> build harvester (5,5).  Result: titanium_collected > 0 with
only ONE harvester.  Run against `d_t_harvb` (two harvesters, nothing collected) to pin
`titanium_collected` above `harvesters`.  Never resigns.
"""

from fcode import Controller, Direction, EntityType, Position

CONV = Position(4, 5)
ORE = Position(5, 5)
SPAWN = Position(4, 6)


class Player:
    def __init__(self):
        self.spawned = False
        self.st = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if not self.spawned and ct.can_spawn(SPAWN):
                ct.spawn_builder(SPAWN)
                self.spawned = True
            return
        if et != EntityType.BUILDER_BOT or self.st > 2:
            return
        p = ct.get_position()
        if self.st == 0:
            if ct.get_tile_building_id(CONV) is not None:
                self.st = 1
                return
            if ct.can_build_conveyor(CONV, Direction.WEST):
                ct.build_conveyor(CONV, Direction.WEST)
                self.st = 1
            return
        if self.st == 1:
            if p == CONV:
                self.st = 2
                return
            if ct.can_move(Direction.NORTH):
                ct.move(Direction.NORTH)
            return
        if ct.get_tile_building_id(ORE) is not None:
            self.st = 3
            return
        if ct.can_build_harvester(ORE):
            ct.build_harvester(ORE)
            self.st = 3
