"""DEFENCE Q4 -- the barrier exchange rate, and whether losing a building refunds cost scale.

Arena `maps/lab/dopen.map26`, vs noop.  ONE builder, which is also the reporter.

Phase 1  build a BARRIER at (5,5) from (5,6), then `fire()` it down with builder attacks
         (2 dmg / 2 Ti, G59) and count exactly how many attacks and how much titanium a
         30 HP / 3 Ti barrier costs the attacker.
Phase 2  build-and-`destroy` a barrier 24 times, sampling `get_scale_percent()` and
         `get_barrier_cost()`, to see whether a destroyed building gives its scale back.
         If scale never falls, every wall we rebuild permanently taxes every unit we buy.
"""

from fcode import Controller, Direction, EntityType, Position

DIRS = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
        (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
SEAT = Position(5, 6)
BARR = Position(5, 5)
DIAG = Position(4, 5)
ROUTE = [(5, 7), (5, 6)]
CYCLES = 24


class Player:
    def __init__(self):
        self.spawned = False
        self.leg = 0
        self.st = 0
        self.atk = 0
        self.ti0 = 0
        self.hpseq = []
        self.diag = "?"
        self.scale = []
        self.cyc = 0
        self.mkr = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        et = ct.get_entity_type()
        r = ct.get_current_round()

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
            else:
                t = ROUTE[self.leg]
                d = DIRS.get((t[0] - p.x, t[1] - p.y))
                if d is not None and ct.can_move(d):
                    ct.move(d)
                return

        if self.st == 0:
            if ct.can_build_barrier(BARR):
                ct.build_barrier(BARR)
                self.st = 1
                self.ti0 = ct.get_global_resources()
                self.scale.append("b0=%d s0=%.0f" % (ct.get_barrier_cost(),
                                                     ct.get_scale_percent()))
            return

        if self.st == 1:
            if self.diag == "?":
                self.diag = "%d" % (1 if ct.can_fire(DIAG) else 0)
            bid = ct.get_tile_building_id(BARR)
            if bid is None:
                self.st = 2
                self.mkr = ct.get_global_resources()
                return
            if ct.can_fire(BARR):
                ct.fire(BARR)
                self.atk += 1
                nb = ct.get_tile_building_id(BARR)
                self.hpseq.append(ct.get_hp(nb) if nb is not None else 0)
            return

        if self.st == 2:
            if self.cyc >= CYCLES:
                self.st = 3
                return
            bid = ct.get_tile_building_id(BARR)
            if bid is None:
                if ct.can_build_barrier(BARR):
                    ct.build_barrier(BARR)
                return
            if ct.can_destroy(BARR):
                ct.destroy(BARR)
                self.cyc += 1
                if self.cyc % 8 == 0:
                    self.scale.append("c%d=%d s=%.0f" % (
                        self.cyc, ct.get_barrier_cost(), ct.get_scale_percent()))
            return

        if self.st == 3:
            ct.resign("DGRIND atk=%d hp=%s ti_after_build=%d ti_after_kill=%d diagfire=%s "
                      "scale=%s bcost=%d gcost=%d bbcost=%d"
                      % (self.atk, self.hpseq, self.ti0, self.mkr, self.diag,
                         self.scale, ct.get_barrier_cost(), ct.get_gunner_cost(),
                         ct.get_builder_bot_cost()))
