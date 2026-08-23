"""Killing the enemy Core once the economy can pay for it.

976 of 1000 games between the ladder's top ten end with a Core destroyed and
only about 2% on the titanium tiebreak, so a bot that can only outlast has a
low ceiling however good its economy is. This is the half brokkr was missing:
it wins against an all-in rush by surviving the attacker's fixed budget, and
loses to anything with an economy behind its turrets.

The weapon is a Sentinel, and the reason is its line. A Gunner's ray stops at
the first thing in the way and reaches three tiles; a Sentinel's reaches five
and is blocked by nothing at all -- not walls, not units, not the enemy's own
buildings. So a Sentinel does not have to stand next to the Core it is
killing. It can sit five tiles back, outside the ring where enemy Builders
and turrets live, and still put 18 damage every two rounds onto the Core. An
attacker that has to reach adjacency is fighting the whole base; one that
needs only a shared row or column is mostly fighting the walk.

That is what decides placement here: a firing spot is any passable tile
sharing a row or column with one of the four Core tiles, within range, from
which the ray runs the right way. Being far is a feature, so candidates are
ranked by *distance from* the Core among those that still hit.

The economics are the mirror of defence.py. Shooting buys 1.8 HP of damage
per titanium against mending's 4 HP of repair, so a siege only pays when we
can afford to lose that exchange -- which is exactly when our income exceeds
theirs. Hence the trigger is our own harvester count, not the round number.
"""

from fcode import Direction

# Sentinel: 30 Ti, 18 damage every 2 rounds, 10 ammunition a shot, attack
# radius^2 = 32, and its line pierces everything. Five tiles is the furthest
# a whole ray stays in range.
SENTINEL_REACH = 5
SENTINEL_AMMO = 10

# Do not open a siege until the economy can feed it. Killing a 500 HP Core
# costs 28 shots -- 280 titanium of ammunition -- on top of the turrets, so
# starting early only buys turrets that fall silent.
#
# The test is income, not Harvester count. The Core sees radius 6 and an
# economy's Harvesters are mostly far outside it, so counting them off the
# Core's own map read 2 on a map where eight were running and the siege never
# opened at all. Passive income alone is 2.5 Ti a round; anything above this
# means Harvesters are actually delivering, which is the thing being asked.
MIN_INCOME = 5.0
MIN_TITANIUM = 140

# Ammunition to hold once a siege is open. Below this the Sentinels are
# ornaments; far above it we are hoarding titanium the economy could compound.
AMMO_TARGET = 60

_DIR_BY_DELTA = {
    (0, -1): Direction.NORTH, (1, 0): Direction.EAST,
    (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST,
}


def enemy_core_tiles(brain):
    """The enemy Core's 2x2 block, seen or inferred from the map's symmetry."""
    anchor = brain.imap.enemy_core()
    if anchor is None:
        return set()
    x, y = anchor
    return {(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)}


def ready(brain, titanium: int, income: float) -> bool:
    """Whether the economy can fund an attack, and there is somewhere to send it."""
    if not enemy_core_tiles(brain):
        return False
    return income >= MIN_INCOME and titanium >= MIN_TITANIUM


def firing_spots(brain):
    """Tiles a Sentinel could stand on and hit the enemy Core, best first.

    A spot is scored by how far it is from the Core: the ray does not care,
    and every tile of distance is one more tile the enemy has to cross to dig
    the Sentinel out. Ties break on the fixed tile order so two Builders
    planning independently choose the same spot and do not both walk to it --
    the claim board keeps them apart, but agreeing costs nothing.
    """
    core = enemy_core_tiles(brain)
    if not core:
        return []
    terrain = brain.terrain
    out = []
    for target in core:
        for delta, facing in _DIR_BY_DELTA.items():
            # Walk back along the ray from the Core tile: a Sentinel at
            # `spot` facing `facing` has its line running through `target`.
            for step in range(1, SENTINEL_REACH + 1):
                spot = (target[0] - delta[0] * step, target[1] - delta[1] * step)
                if not terrain.inside(spot) or spot in core:
                    continue
                if spot in terrain.blocked and spot != brain.me:
                    continue
                out.append((step, spot, facing))
    out.sort(key=lambda row: (-row[0], row[1]))
    seen = set()
    unique = []
    for step, spot, facing in out:
        if spot in seen:
            continue
        seen.add(spot)
        unique.append((spot, facing))
    return unique


def ammo_wanted(ammo: int, titanium: int, reserve: int) -> int:
    """Titanium to convert this turn, or 0.

    Converting is one-way -- ammunition cannot buy a Harvester back -- so the
    reserve is honoured before the target, and nothing converts until we own
    something that fires.
    """
    if ammo >= AMMO_TARGET:
        return 0
    spare = titanium - reserve
    if spare < SENTINEL_AMMO:
        return 0
    return min(spare, AMMO_TARGET - ammo)
