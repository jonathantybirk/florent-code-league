"""DEFENCE Q2 tiebreak fixture: MANY UNITS, zero collected, zero harvesters, LESS titanium.

Arena `maps/lab/dore.map26`, vs noop.  The Core spawns builders on its ring until it has 12
and they never move.  Against `noop` this isolates: does the turn-1000 tiebreak look at unit
count?  If not, this bot loses on titanium_stored (12 builders at escalating cost is a large
spend).  Never resigns.
"""

from fcode import Controller, EntityType, Position

RING = ((1, 4), (2, 4), (3, 4), (4, 4), (1, 5), (4, 5),
        (1, 6), (4, 6), (1, 7), (2, 7), (3, 7), (4, 7))
N = 12


class Player:
    def __init__(self):
        self.n = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        if ct.get_entity_type() != EntityType.CORE:
            return
        if self.n >= N:
            return
        p = Position(RING[self.n][0], RING[self.n][1])
        if ct.can_spawn(p):
            ct.spawn_builder(p)
            self.n += 1
