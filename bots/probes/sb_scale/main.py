"""SABOTAGE Q0 -- the cost-scale curve, on 2.3.6.  Arena `dopen.map26`, vs noop.

Sabotage economics only close if you know whether the ATTACKER's turrets get more expensive as it
builds them while the DEFENDER's 3 Ti conveyor stays 3 Ti.  sb_bkill already showed conveyor cost
pinned at 3 across eight destroy/rebuild cycles at scale=120%.  This probe measures the curve
itself: the Core spawns a builder every round it can afford one, and every round it appends
(unit_count, scale_percent, builder_cost, gunner_cost, sentinel_cost, conveyor_cost, barrier_cost,
harvester_cost) whenever the scale changes.

Resigns from the Core at round 70 with the change-points only, so the message stays readable.
"""

from fcode import Controller, EntityType, Position

SPAWNS = (Position(4, 7), Position(4, 4), Position(1, 4), Position(1, 7),
          Position(2, 3), Position(3, 3), Position(2, 8), Position(3, 8),
          Position(4, 5), Position(4, 6), Position(1, 5), Position(1, 6))
REPORT = 70


class Player:
    def __init__(self):
        self.rows = []
        self.last = None
        self.note = ""
        self.n = 0

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception as exc:
            self.note = type(exc).__name__[:8] + ":" + str(exc)[:30]

    def _run(self, ct):
        if ct.get_entity_type() != EntityType.CORE:
            return
        r = ct.get_current_round()

        key = (ct.get_unit_count(), int(ct.get_scale_percent()),
               ct.get_builder_bot_cost(), ct.get_gunner_cost(),
               ct.get_sentinel_cost(), ct.get_conveyor_cost(),
               ct.get_barrier_cost(), ct.get_harvester_cost())
        if key != self.last:
            self.rows.append(key)
            self.last = key

        if r == REPORT:
            ct.resign("SBSCALE cols=(units,scale,bld,gun,sen,conv,barr,harv) %s ti=%d n=%s"
                      % (self.rows, ct.get_global_resources(), self.note))
            return

        if self.n < len(SPAWNS):
            p = SPAWNS[self.n]
            if ct.can_spawn(p):
                ct.spawn_builder(p)
                self.n += 1
            else:
                self.n += 1
        return
