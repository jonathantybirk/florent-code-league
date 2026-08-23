"""How many Builders the economy wants, and which of them mend.

The Core and the Builders both have to answer these, and they have to give the
same answer: the Core sizes the mend alarm and decides when to spawn past the
economic target, while each Builder decides for itself whether it is one of
the menders. Deriving both from the same two functions is what stops a Builder
mending a siege the Core thinks is over, or a mender the Core spawned going
back to a lane instead of healing.
"""

LARGE_MAP_AREA = 500
BUILDER_TARGET_SMALL = 4
# Five, measured, not guessed. Every Builder adds 20% to the cost of every
# later build, and an intent trace on glacierkeep showed the sixth was pure
# tax: it drove the team's scale factor to about 4.1 while the Builders that
# were working waited on Harvesters they could not afford (56 Ti against a
# base of 20). On the pool at 90 games a matchup, against hildr and steward:
#   4 builders -> 87/90 and 23/90   (110/180)
#   5 builders -> 90/90 and 24/90   (114/180)
#   6 builders -> 78/90 and 28/90   (106/180)
BUILDER_TARGET_LARGE = 5


def econ_target(width: int, height: int) -> int:
    """Builders bought for the economy, before any siege spawns.

    Each Builder adds 20% to the cost of every later build, so the number is
    not "as many as we can afford". The ladder's top ten economies run 4 to 7.
    """
    return (BUILDER_TARGET_LARGE if width * height >= LARGE_MAP_AREA
            else BUILDER_TARGET_SMALL)


# Builders sent to plant the Sentinel line at the enemy Core. Two is enough:
# the walk is most of the cost and a third only adds cost scaling, since the
# line's damage is limited by ammunition rather than by turret count.
ATTACKERS = 3


def is_attacker(index: int, target: int, siege_open: bool) -> bool:
    """Whether this Builder should be at the enemy Core rather than a lane.

    The last economic Builders are chosen, not the first: index 0 is the home
    guard and the low indices hold the oldest, longest lanes, so taking those
    would strand the most infrastructure. Siege Builders spawned past the
    economic target are menders, not attackers -- see `is_mender`.
    """
    if not siege_open or index >= target:
        return False
    return index >= max(1, target - ATTACKERS)


def is_mender(index: int, wanted: int, target: int) -> bool:
    """Whether the Builder at `index` should be healing rather than mining.

    Two populations mend. The first `wanted` economic Builders, lowest index
    first -- index 0 is the home guard, so a one-mender alarm costs the
    economy the Builder that was already staying home. And every Builder past
    the economic target, because those exist only because a siege spawned
    them; sending them back to a lane would waste the titanium that bought
    them.

    Without this the published count was ignored and every Builder within
    recall mended, so a single enemy scout sitting near our Core shut the
    whole economy down for the match: 0 titanium collected in the 73 rounds
    of the helheim loss.
    """
    if wanted <= 0:
        return False
    if index >= target:
        return True
    return index < wanted
