"""Q2 -- is the cost scale PER TEAM or GLOBAL to the game?

This bot builds NOTHING and spawns NOTHING for the whole match.  Its Core simply reads its own
get_scale_percent() and all eight cost getters every round and resigns at round 150 with the
maximum scale it ever saw.

Run it BOTH ways round against a heavy spender (`gg_spam` spawns a Builder Bot every round it can
afford one, +20pp per builder on the spender's side):

    runfull cs_watch --map lab/csopen --vs gg_spam    # we watch, they spend
    runfull gg_spam  --map lab/csopen --vs cs_watch   # they watch, we spend

If the scale were global to the game, the watcher's scale would climb with the spender's
purchases.  If it is per team, the watcher stays pinned at 100.0 with base costs while the
result dict shows the spender piling up units.
"""

from fcode import Controller, EntityType, GameError, Position


class Player:
    def __init__(self):
        self.smax = 0.0
        self.smin = 1e9
        self.done = False

    def run(self, ct: Controller) -> None:
        try:
            self._run(ct)
        except Exception:
            return

    def _run(self, ct):
        if ct.get_entity_type() != EntityType.CORE or self.done:
            return
        s = ct.get_scale_percent()
        if s > self.smax:
            self.smax = s
        if s < self.smin:
            self.smin = s
        if ct.get_current_round() < 150:
            return
        self.done = True
        ct.resign(("CSWATCH r=%d s=%.1f min=%.1f max=%.1f cv=%d sp=%d hv=%d br=%d "
                   "gn=%d st=%d lu=%d bb=%d u=%d ti=%d" % (
                       ct.get_current_round(), s, self.smin, self.smax,
                       ct.get_conveyor_cost(), ct.get_splitter_cost(),
                       ct.get_harvester_cost(), ct.get_barrier_cost(),
                       ct.get_gunner_cost(), ct.get_sentinel_cost(),
                       ct.get_launcher_cost(), ct.get_builder_bot_cost(),
                       ct.get_unit_count(), ct.get_global_resources()))[:495])
