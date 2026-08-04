"""Map oracle: recognise the map at round 0, then play whichever bot measured
best on it.

Unfair by our house rule (it acts on map *identity*, which a bot cannot derive
from what it can see), though the atlas ban is our rule and not the league's.
Not final-ready: on any map outside the published pool the lookup misses and
this is exactly the default sub-bot.

The selection table comes from the 23,520-match run ``auto-852f773c9500``,
restricted to the four opponents that odin, heimdall and vigil all played, so
the three columns are directly comparable.  Read the margins before trusting a
cell: they are 1-2 games out of 16 nearly everywhere, and the measured spread
between the three bots pooled over all maps is under a point (odin 0.9643,
heimdall 0.9603, vigil 0.9415).  Selecting per map is worth about +0.6pp over
playing one bot everywhere, which is inside that noise -- the honest
expectation for this bot is that it performs like its default sub-bot.

Keyed on map **dimensions**, not on the (dimensions, own Core) pair the atlas
uses, because *every unit re-executes this module and gets its own globals*.
A decision the Core makes is invisible to a Gunner spawned later, and only the
Core stands on the anchor tile the atlas keys off.  Dimensions are the largest
piece of map identity every unit can read for itself, so every unit reaches the
same answer with no shared state.  The Global Communication Store would be the
usual way to share a decision, but it has only 16 slots, the sub-bots already
use at least 0 and 9-15, and its writes are not visible until the next round.

Dimensions separate 16 of the 21 published maps outright.  (16, 16) holds
crossfire and jackpot, which want the same bot anyway.  (24, 24) holds quarry,
runestone and vault, which do not: it is resolved as one group below.

The three sub-bots are vendored flat as ``<bot>_<module>.py`` by
``tools/build_maporacle.py``, because the sandbox exposes no filesystem to load
them from -- see that script for why.  Importing all three at module scope
rather than on the first turn is deliberate: module execution is not counted
against the 10 ms turn limit (vigil standalone pays the same per-unit cost to
parse its atlas data and passes compliance), whereas a first-turn import would
be, and a cold import costs 13-15 ms per bot on a server that ships no
``__pycache__``.
"""

from fcode import Controller

import heimdall_main
import odin_main
import vigil_main

# (map width, map height) -> sub-bot.  Absent means the default.
#
# heimdall is the default and wins every tie: it took the only series any of
# our bots has won against Pantheon (3-2 on 2026-08-04, where odin lost 1-4).
# That is 5 games per bot and odin leads the head-to-head 85/126, so the
# ordering is a deliberate bet on the Pantheon matchup rather than a measured
# result -- if those series turn out to be noise, flip DEFAULT to odin and
# regenerate with the tie-break order reversed.
#
# Entries are maps where another bot beat heimdall outright on the
# common-opponent slice of auto-852f773c9500 (16 games/bot, 48 for vigil).
TABLE = {
    (14, 18): "odin",       # pinch      1.000 vs heimdall 0.958
    (20, 20): "vigil",      # fjord      0.896 vs heimdall 0.875
    (20, 26): "odin",       # strait     1.000 vs heimdall 0.958
    (21, 8): "odin",        # bridge     0.938 vs heimdall 0.917
    (21, 21): "vigil",      # twins      0.979 vs heimdall 0.875
    (24, 24): "vigil",      # quarry/runestone/vault as one group:
                            #   vigil 142/144 0.986, heimdall 70/72 0.972,
                            #   odin 46/48 0.958.  Carries runestone, the one
                            #   override with a real sample (vigil 48/48).
    (28, 20): "odin",       # longship   0.875 vs heimdall 0.833
}
DEFAULT = "heimdall"

PLAYERS = {
    "heimdall": heimdall_main.Player,
    "odin": odin_main.Player,
    "vigil": vigil_main.Player,
}


class Player:
    """One instance per unit, each wrapping one instance of the sub-bot's Player."""

    def __init__(self):
        self._inner = None

    def run(self, ct: Controller) -> None:
        if self._inner is None:
            key = (ct.get_map_width(), ct.get_map_height())
            self._inner = PLAYERS[TABLE.get(key, DEFAULT)]()
        self._inner.run(ct)
