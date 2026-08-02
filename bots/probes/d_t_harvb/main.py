"""DEFENCE Q2 tiebreak fixture, TEAM-B COORDINATES: two unconnected harvesters.

Arena `maps/lab/dore.map26`.  Core B anchor (16,5); (15,5) and (15,6) are spawn-ring tiles
orthogonally adjacent to the ore at (14,5) and (14,6).  Two builders, one per ore, so no
walking is needed at all.  0 collected, 2 harvesters, slightly less titanium than `noop`.
Never resigns.
"""

from fcode import Controller, Direction, EntityType, Position

SEATS = ((15, 5), (15, 6))
ORE = {(15, 5): Position(14, 5), (15, 6): Position(14, 6)}


class Player:
    def __init__(self):
        self.n = 0
        self.home = None
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        if et == EntityType.CORE:
            if self.n < len(SEATS):
                p = Position(SEATS[self.n][0], SEATS[self.n][1])
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.n += 1
            return
        if et != EntityType.BUILDER_BOT or self.done:
            return
        p = ct.get_position()
        if self.home is None:
            if (p.x, p.y) not in ORE:
                return
            self.home = (p.x, p.y)
        tgt = ORE[self.home]
        if ct.get_tile_building_id(tgt) is not None:
            self.done = True
            return
        if ct.can_build_harvester(tgt):
            ct.build_harvester(tgt)
            self.done = True
