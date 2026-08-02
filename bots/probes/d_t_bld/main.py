"""DEFENCE Q2 tiebreak fixture: MANY BUILDINGS, zero collected, zero harvesters, LESS titanium.

Arena `maps/lab/dore.map26`, vs noop.  One builder walks east along y=8 planting a BARRIER
to the north at every step.  Against `noop` (0 barriers, 0 units, maximum stored titanium)
this isolates one question: does the turn-1000 tiebreak look at building count at all?
If it does, this bot wins.  If the ladder is collected > harvesters > stored > coinflip,
this bot LOSES on titanium_stored, because barriers cost titanium and noop spends none.
Never resigns -- the point is to reach turn 1000.
"""

from fcode import Controller, Direction, EntityType, Position

N = 12


class Player:
    def __init__(self):
        self.spawned = False
        self.built = 0

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
        p = ct.get_position()
        if p.y != 8:
            if ct.can_move(Direction.SOUTH):
                ct.move(Direction.SOUTH)
            return
        if self.built >= N:
            return
        up = Position(p.x, 7)
        if ct.get_tile_building_id(up) is None:
            if ct.can_build_barrier(up):
                ct.build_barrier(up)
                self.built += 1
            return
        if ct.can_move(Direction.EAST):
            ct.move(Direction.EAST)
