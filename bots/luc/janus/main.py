"""Two whole bots behind one entry point, chosen by the shape of the map.

Prospect tried to get this effect by turning knobs inside one bot and it did
not work, for a reason the tournament fingerprints make obvious in hindsight:
the families that win the two kinds of map are not the same machine tuned
differently. At the end of a game the tempest lineage has about 5.6 buildings
standing and has collected about 90 titanium, killing on median turn 38-40;
vanguard has 15-19 buildings and 500-650 titanium and kills on turn 50-63.
Adding two field Gunners to a rusher moves it a tenth of the way there, and a
tenth of the way is worth nothing.

So this ships both lineages intact and picks between them once, per unit, on
the unit's first turn. Neither is modified beyond making its sibling imports
package-relative, so each still plays exactly as it was measured playing.

Both are imported at module load rather than lazily after the verdict. Loading
is what the engine pays for when it builds the Player, outside the 10ms that
run() has to fit in; deferring it into the first run() would put a two-lineage
import inside a turn budget, and a turn that overruns is abandoned midway,
which is a bad place to leave a half-initialised module.

And it does not pay, for a reason worth writing down. On the five corner maps,
both seats, ten games each:

    tempest as of da3fd8a  vs  vanguard   vanguard 7 - 3    (2026-08-01)
    prospect               vs  tempest as of da3fd8a   9 - 1
    prospect               vs  vanguard   prospect 6 - 4    (this bot, 4 - 6)

The tournament was not wrong. Vanguard really did beat the tempest line on
closed ground, by roughly the margin 138,785 matches said it would. What has
happened since is that the tempest line moved: prospect beats the bot that
measurement was taken against 9-1, and having done so it no longer needs
rescuing on the maps it used to lose. The switch is now a slightly worse bot
than just being prospect everywhere.

Kept because it is correct and cheap to re-measure rather than because it
wins. If the two lineages diverge again -- or if vanguard gets the same month
of work prospect just had -- the plumbing is here and the answer is one
tournament run away. The analysis behind it has a shelf life measured in days,
which is the real lesson: a map-strategy result is a fact about two particular
bots on a particular afternoon, not about the maps.

tempest/ is prospect at 1b5f3d1b8, itself Vigil with the atlas removed.
vanguard/ is bots/jon/fair/vanguard from x/jon -- Jon's bot, vendored, fair.
"""

import sys

from fcode import EntityType

import mapshape
from tempest.lineage import Player as OpenPlayer
from vanguard.lineage import Player as ClosedPlayer

_PLAYERS = {mapshape.OPEN: OpenPlayer, mapshape.CLOSED: ClosedPlayer}


class Player:
    """One per entity; each reaches its own verdict and then stops deciding."""

    def __init__(self) -> None:
        self._inner = None

    def run(self, ct) -> None:
        if self._inner is None:
            choice = mapshape.classify(ct)
            self._inner = _PLAYERS[choice]()
            _announce(ct, choice)
        self._inner.run(ct)


def _announce(ct, choice: int) -> None:
    """One line per match. A module-level "already said it" flag would not
    work: units do not share globals, so each would announce its own."""
    if ct.get_entity_type() != EntityType.CORE:
        return
    print(f"LINEAGE round={ct.get_current_round()} "
          f"map={ct.get_map_width()}x{ct.get_map_height()} "
          f"choice={mapshape.NAMES[choice]}", file=sys.stderr, flush=True)
