"""How many Builders the opening wants, which lanes each owns, where each spawns.

Every unit computes this, so it has to be both cheap and identical everywhere.
It is a plain list schedule: lanes are offered cheapest-first to whichever
Builder would finish one soonest, counting the round that Builder is spawned,
the walk out to the lane, and two rounds per conveyor tile plus one for the
Harvester.

One Builder per lane rather than the whole crew per lane is deliberate.  Four
Builders sharing a ten-tile lane finish it in about eleven rounds instead of
twenty, but nothing else is started meanwhile; four Builders on four lanes put
four Harvesters up at round twenty.  Income is the sum over deposits of how
long each has been running, so starting four clocks beats finishing one early.

Spawn placement falls out of the assignment rather than being a rule of its
own: a Builder is placed on the ring tile beside the first tile of its first
lane, so its opening round is a build, not a walk.
"""

from board import STEPS

# The opening crew.  Four is what 500 Ti affords alongside the conveyors and
# Harvesters they lay (30 + 36 + 43 + 52 = 161 Ti of Builders), and it is the
# number the top economy ladders open with.
OPENING = 4


def assign(board, lanes, count=OPENING):
    """(work, spawns): the lane indices each Builder owns, and its spawn tile.

    `work[i]` is in the order Builder i should do them; `spawns[i]` is None if
    there was no lane for that Builder to take.
    """
    work = [[] for _ in range(count)]
    free = list(range(count))             # the round each Builder can first act
    where = [None] * count                # where its last lane leaves it
    for index, lane in enumerate(lanes):
        best = None
        for who in range(count):
            arrive = free[who] + _walk(where[who], lane.entry)
            finish = arrive + lane.cost
            if best is None or finish < best[0]:
                best = (finish, who)
        _, who = best
        work[who].append(index)
        free[who] = best[0]
        where[who] = lane.stand
    return work, _spawns(board, lanes, work, count)


def _walk(here, there):
    """A cheap stand-in for the walk between two tiles of the tree.

    Manhattan distance, which is exact down an unobstructed lane and an
    underestimate around a wall.  The schedule only needs the ordering of
    candidate finishing times, and a Builder already parked on the far end of
    a lane is ordered correctly against one still at the Core by this measure.
    """
    if here is None:
        return 0
    return abs(here[0] - there[0]) + abs(here[1] - there[1])


def _spawns(board, lanes, work, count):
    """Place each Builder on the ring tile beside its first job."""
    laid = set()
    for lane in lanes:
        laid.update(spot for spot, _ in lane.tiles)
    ring = [tile for tile in board.ring() if tile not in laid]
    taken, out = set(), []
    for who in range(count):
        if not work[who]:
            out.append(None)
            continue
        want = lanes[work[who][0]].entry
        spot = _nearest(ring, taken, want)
        if spot is None:                  # ring full of lanes; take any tile
            spot = _nearest(board.ring(), taken, want)
        taken.add(spot)
        out.append(spot)
    return out


def _nearest(ring, taken, want):
    best = None
    for tile in ring:
        if tile in taken:
            continue
        gap = abs(tile[0] - want[0]) + abs(tile[1] - want[1])
        if best is None or gap < best[0]:
            best = (gap, tile)
    return best[1] if best else None
