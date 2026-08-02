"""DEFENCE Q2 -- is the `harvesters` tiebreak a LIVE count or a cumulative one?

Team-B coordinates on `maps/lab/dore.map26`, same as `d_t_harvb`: build two harvesters, then
`destroy` one at round 500 so exactly one is alive at turn 1000.

Run against `d_t_harv` (team A, exactly one harvester that lives to the end):
  live count   -> 1 vs 1, harvesters ties, decided by titanium_stored
  cumulative   -> B has 2, B wins on harvesters
Which matters for defence: if the count is live, KILLING enemy harvesters flips the turn-1000
tiebreak, and denial is a win condition rather than a delaying tactic.  Never resigns.
"""

from fcode import Controller, Direction, EntityType, Position

SEATS = ((15, 5), (15, 6))
ORE = {(15, 5): Position(14, 5), (15, 6): Position(14, 6)}
KILL_AT = 500


class Player:
    def __init__(self):
        self.n = 0
        self.home = None
        self.done = False
        self.killed = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()
        if et == EntityType.CORE:
            if self.n < len(SEATS):
                p = Position(SEATS[self.n][0], SEATS[self.n][1])
                if ct.can_spawn(p):
                    ct.spawn_builder(p)
                    self.n += 1
            return
        if et != EntityType.BUILDER_BOT:
            return
        p = ct.get_position()
        if self.home is None:
            if (p.x, p.y) not in ORE:
                return
            self.home = (p.x, p.y)
        tgt = ORE[self.home]
        if not self.done:
            if ct.get_tile_building_id(tgt) is not None:
                self.done = True
                return
            if ct.can_build_harvester(tgt):
                ct.build_harvester(tgt)
                self.done = True
            return
        if self.home == (15, 6) and not self.killed and r >= KILL_AT:
            if ct.can_destroy(tgt):
                ct.destroy(tgt)
                self.killed = True
