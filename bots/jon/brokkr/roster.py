"""Who each Builder is, in one place.

The Core and every Builder have to agree about this. The Core sizes the mend
alarm and decides when to spawn past the economic target; each Builder decides
for itself whether it is a mender, a harasser, an attacker or a miner. When
those two derivations disagree, a Builder mends a siege the Core thinks is
over, or a Builder the Core spawned to heal wanders back to a lane.

Roles are assigned by spawn index, which is deterministic and needs no
communication beyond the index itself. They do not overlap: an earlier version
let index 3 be both harasser and attacker and resolved it by the order the
checks happened to run in, which is not a decision anybody made.

    0            home guard      stays near the Core, mines only nearby
    1..H         harassers       cut enemy belt (see harass.py)
    H+1..T-A-1   miners          lay lane
    T-A..T-1     attackers       plant the Sentinel line once the siege opens
    T..          siege menders    spawned only to heal, and only heal
"""

LARGE_MAP_AREA = 500
BUILDER_TARGET_SMALL = 4
# Five, measured, not guessed. Every Builder adds 20% to the cost of every
# later build, and the tax compounds faster than the extra hands earn -- even
# after harassment gave the extra hands something valuable to do:
#   roster 4/5 -> 84/90 and 41/90   (125/180)
#   roster 5/6 -> 72/90 and 39/90   (111/180)
#   roster 6/7 -> 66/90 and 31/90   ( 97/180)
BUILDER_TARGET_LARGE = 5

# Builders cutting belt in the enemy half. Two and three measure the same
# overall (125/180 each); three is kept because its gain is against the
# economy, which is seven of the ladder's top ten, and its loss is against the
# rush, which brokkr already beats.
HARASSERS = 3

# Builders that plant the Sentinel line. The walk is most of the cost and the
# line's damage is bounded by ammunition rather than by turret count, so more
# than a couple only adds cost scaling.
ATTACKERS = 1

# Economic Builders that keep mining however loud the alarm is -- mending is
# paid for in titanium, so an economy that stops entirely stops being able to
# heal. See the negative result in llm-slop-analysis: forcing this floor
# measured worse, so it is deliberately 0 and kept only as the name of the
# idea.
MIN_MINERS = 0


def econ_target(width: int, height: int) -> int:
    """Builders bought for the economy, before any siege spawns."""
    return (BUILDER_TARGET_LARGE if width * height >= LARGE_MAP_AREA
            else BUILDER_TARGET_SMALL)


def _attacker_first(target: int) -> int:
    """Lowest index that may attack, never colliding with a harasser."""
    return max(HARASSERS + 1, target - ATTACKERS)


def is_harasser(index: int, target: int, allowed: bool) -> bool:
    if not allowed or index is None or target <= 3:
        return False               # too small a roster to spare anybody
    return 1 <= index <= HARASSERS


def is_attacker(index: int, target: int, siege_open: bool) -> bool:
    """Whether this Builder belongs at the enemy Core rather than a lane.

    The last economic Builders are chosen, not the first: index 0 is the home
    guard and the low indices are harassers already committed in the enemy
    half.
    """
    if not siege_open or index is None or index >= target:
        return False
    return index >= _attacker_first(target)


def is_mender(index: int, wanted: int, target: int) -> bool:
    """Whether this Builder should be healing rather than working.

    Two populations mend: the first `wanted` economic Builders, lowest index
    first, and everything past the economic target, which exists only because
    a siege spawned it. Attackers are exempt -- an attacker recalled is an
    attacker that never arrives.

    Without the count being respected at all, a single enemy scout near our
    Core put the whole workforce on healing duty for the match: 0 titanium
    collected in the 73 rounds of the helheim loss.
    """
    if wanted <= 0 or index is None:
        return False
    if is_attacker(index, target, True):
        return False
    if index >= target:
        return True
    return index < min(wanted, max(0, target - MIN_MINERS))
