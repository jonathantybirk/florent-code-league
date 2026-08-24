"""Decide which lineage plays this map, from what any unit can see.

The corner test is the one that survived measurement in prospect/doctrine.py:
a Core touching two perpendicular map edges has two of its four approaches
guarded by the map itself, and on the current pool that selects bridge,
jackpot, string, sweden and vase -- five of the seven maps the tournament data
says reward building over rushing.

What is new here is who gets to run the test. Units do not share a module
namespace: measured, a Builder sees its own module globals and nothing the
Core set, so there is no decision to inherit and every unit has to reach the
same verdict on its own. The global store is the only channel between them and
both lineages already spend all sixteen slots, so the verdict travels through
the map instead.

That works because the rules make maps symmetric by reflection or rotation,
and all three symmetries send corners to corners -- confirmed against the 21
official maps, where the two Cores are always images of each other under
point, x-mirror or y-mirror reflection. So a unit may test whichever Core it
can see and get the same answer either way. This matters for turrets, which
Builders put up next to the *enemy* Core and which would otherwise wake up
too far from home to have an opinion.

Seeing a Core is not something every unit can do, which cost a whole round of
measurement to learn. A Gunner sees r^2 = 13 and a Launcher r^2 = 26, and
Builders put both of those up out in the field, far from either base. Measured
on bridge, the Core and every Builder chose the closed lineage and four
Launchers chose the open one -- a team running two bots at once, over a single
sixteen-slot store whose layout means different things to each of them.

So a unit that can see a Core publishes the verdict, and a unit that cannot
reads it. The channel needs no change to either lineage and no slot of its
own: vanguard never touches slot 13, and tempest uses it only for a packed
position, which pack_pos caps at 958 on the largest legal map. A value far
above that is therefore something only this module can have written. It is
published only for CLOSED, so on an open map nothing is written at all and
tempest keeps slot 13 entirely to itself.

The Core is never blind and classifies on round 0, and store writes land the
following round, so every later unit has an answer before its first turn.
"""

from fcode import EntityType

OPEN = 0
CLOSED = 1

NAMES = {OPEN: "open/tempest", CLOSED: "closed/vanguard"}

# Strict: sprint's Core sits one tile off the corner and plays as an open map,
# so a margin of 1 would start costing false positives immediately.
CORNER_MARGIN = 0

# Free in vanguard; in tempest it holds pack_pos output, which cannot reach
# 1 + 29*32 + 29 = 958, let alone this.
LINEAGE_SLOT = 13
CLOSED_MARK = 31337


def classify(ct) -> int:
    """Pick a lineage. Never raises -- a bad read must not cost the game."""
    try:
        return _classify(ct)
    except Exception:  # noqa: BLE001
        return OPEN


def _classify(ct) -> int:
    core = _any_core(ct)
    if core is None:
        # Blind: trust whatever a unit that could see published.
        return CLOSED if ct.read_store(LINEAGE_SLOT) == CLOSED_MARK else OPEN
    width, height = ct.get_map_width(), ct.get_map_height()
    x, y = core
    # A Core is 2x2 and is reported by its north-west cell, so the far edges
    # sit at width - 2 and height - 2.
    on_side = x <= CORNER_MARGIN or x >= width - 2 - CORNER_MARGIN
    on_end = y <= CORNER_MARGIN or y >= height - 2 - CORNER_MARGIN
    if not (on_side and on_end):
        return OPEN
    ct.write_store(LINEAGE_SLOT, CLOSED_MARK)
    return CLOSED


def _any_core(ct):
    """North-west cell of any Core in vision, ours or theirs."""
    if ct.get_entity_type() == EntityType.CORE:
        return tuple(ct.get_position())
    for building in ct.get_nearby_buildings():
        if ct.get_entity_type(building) == EntityType.CORE:
            return tuple(ct.get_position(building))
    return None
