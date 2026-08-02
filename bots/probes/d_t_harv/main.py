"""DEFENCE Q2 tiebreak fixture: ONE UNCONNECTED HARVESTER, zero collected, LESS titanium.

Arena `maps/lab/dore.map26` (ore at (5,5)(5,6) next to Core A, (14,5)(14,6) next to Core B).
A builder walks to ring tile (4,5) and builds a HARVESTER on the ore at (5,5).  There is no
conveyor chain, so `titanium_collected` stays 0 (G02) and the only metric that differs from
`noop` is the harvester count -- and titanium_stored, which is WORSE for this bot.
If `harvesters` outranks `titanium_stored`, this bot wins with less titanium.  Never resigns.
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
ROUTE = [(4, 7), (4, 6), (4, 5)]
ORE = (Position(5, 5),)


class Player:
    def __init__(self):
        self.spawned = False
        self.leg = 0
        self.n = 0

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
        if self.leg < len(ROUTE):
            if (p.x, p.y) == ROUTE[self.leg]:
                self.leg += 1
                return
            t = ROUTE[self.leg]
            d = DIRS.get((t[0] - p.x, t[1] - p.y))
            if d is not None and ct.can_move(d):
                ct.move(d)
            return
        if self.n >= len(ORE):
            return
        tgt = ORE[self.n]
        if ct.get_tile_building_id(tgt) is not None:
            self.n += 1
            return
        if ct.can_build_harvester(tgt):
            ct.build_harvester(tgt)
            self.n += 1
