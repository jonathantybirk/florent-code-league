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
BUILDER_TARGET_LARGE = 6


def econ_target(width: int, height: int) -> int:
    """Builders bought for the economy, before any siege spawns.

    Each Builder adds 20% to the cost of every later build, so the number is
    not "as many as we can afford". The ladder's top ten economies run 4 to 7.
    """
    return (BUILDER_TARGET_LARGE if width * height >= LARGE_MAP_AREA
            else BUILDER_TARGET_SMALL)


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
