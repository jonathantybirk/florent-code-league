"""Cutting the enemy economy: destroy a belt tile, then sit a barrier on it.

This is the best-value action in the game and brokkr has never once performed
it. The arithmetic is not close.

A conveyor has 20 HP. A Builder hits an adjacent building for 2 damage at 2
titanium, so removing one costs **20 titanium and ten rounds**. Every Harvester
behind that tile stops delivering the moment it goes: a lane runs up to four
Harvesters at 2.5 Ti a round each, so a single cut can deny **10 titanium a
round**. It pays for itself in two rounds and then keeps paying. Compare the
two other ways we have of spending titanium on the opponent -- a Sentinel shot
buys 1.8 HP of damage per titanium, and healing buys 4 HP of repair -- and
cutting a belt is an order of magnitude better than either.

The barrier is what makes it stick. Three titanium puts 30 HP of wall on the
tile they need back, so repairing the lane now costs them fifteen Builder-
rounds before they can even start rebuilding. Without it a Builder walks over
and re-lays a 3 Ti conveyor and the ten rounds we spent bought nothing. This
is the `destroy -> occupy` sequence Bean counters run, and it is what
`bots/utils/harassment` was specified around.

Targets are ranked by how near the enemy Core they are, because that is the
cheapest available proxy for fan-in: belt tiles converge as they approach the
Core, so the last tile before it carries every Harvester on that lane, while a
tile out at the frontier carries one. We cannot see their whole network -- we
only know what our units have walked past -- so a proxy is what there is.
"""

from utils.GCS.Base.protocol import TILE_STATES as _STATES

# Worth attacking, in preference order, with the hits each takes at 2 damage.
# A conveyor is both the cheapest to remove and the most valuable to remove,
# which is unusual enough to be worth stating: it is 10 hits to cut a lane
# against 15 to kill one Harvester.
TARGET_HITS = {"ENEMY_CONVEYOR": 10, "ENEMY_SPLITTER": 10, "ENEMY_HARVESTER": 15}

# Do not start before the economy can spare the Builder. A harasser is one
# fewer Builder laying lane, and 20 titanium of attacks it cannot afford is a
# Builder standing next to an enemy conveyor achieving nothing.
START_ROUND = 20
MIN_TITANIUM = 40

# How far into their half a target may be before the walk costs more than the
# cut is worth. Measured from the enemy Core, so this is a radius around their
# base rather than a distance from ours.
TARGET_RADIUS = 9


def targets(brain, enemy_core):
    """Enemy economy tiles we know about, best first.

    Nearest the enemy Core first: belt converges toward the Core, so the tile
    just outside it carries the whole lane's output and a tile at the far end
    carries one Harvester's.
    """
    if not enemy_core:
        return []
    out = []
    for key, tile in brain.imap.tiles.items():
        name = _STATES[tile.state]
        kind = None
        for prefix in TARGET_HITS:
            if name.startswith(prefix):
                kind = prefix
                break
        if kind is None:
            continue
        gap = min(abs(key[0] - c[0]) + abs(key[1] - c[1]) for c in enemy_core)
        if gap > TARGET_RADIUS:
            continue
        # Harvesters are worth removing outright, so they are not penalised
        # for sitting at the end of a lane where the belt would be.
        rank = gap if kind != "ENEMY_HARVESTER" else gap - 2
        out.append((rank, key, kind))
    out.sort(key=lambda row: (row[0], row[1]))
    return [(key, kind) for _rank, key, kind in out]


def ready(round_number: int, titanium: int) -> bool:
    return round_number >= START_ROUND and titanium >= MIN_TITANIUM


def still_there(brain, tile) -> bool:
    """Whether our target is still an enemy building worth hitting."""
    state = brain.imap.state_at(*tile)
    if state is None:
        return True                    # out of sight; assume until disproved
    name = _STATES[state]
    return any(name.startswith(prefix) for prefix in TARGET_HITS)
