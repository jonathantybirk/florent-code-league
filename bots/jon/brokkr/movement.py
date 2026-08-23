"""Getting a Builder from where it decided to be to the next tile toward it.

Everything here is about the gap between a route and a step. The route comes
from our own map, which is optimistic about ground nobody has looked at and
stale about ground somebody has left, so every step it proposes is exactly
that -- a proposal the engine may refuse. A refusal that is swallowed rather
than handled is how a Builder spends a hundred rounds walking hard and
arriving nowhere.
"""
from fcode import Direction, GameError

import debug
import lanes
from brain import CARDINALS, DELTA
from utils.GCS.Base.protocol import TILE_STATES as STATES

# Conveyor tile states are named by the direction they face.
LETTER = {Direction.NORTH: "N", Direction.EAST: "E",
          Direction.SOUTH: "S", Direction.WEST: "W"}
# Rounds of failing to move before a Builder takes a step that does not help,
# purely to break out of whatever is pinning it, and rounds before it gives up
# on the deposit entirely.
#
# Counting failed moves is the only measure that catches this. The distance
# counter above cannot: it lives on the job, and every role switch clears
# `brain.job` and the count with it. Traced on auroraveil, Builder 7 sat on
# (10, 12) from round 328 to the end of the match re-deciding to walk to
# (10, 4) every round and never taking a step.
UNSTICK_AFTER = 2
UNSTICK_ABANDON = 10



def orthogonal(a, b) -> bool:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


def manhattan(a, b) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def any_orthogonal(brain, tile):
    for candidate in lanes.orthogonal(tile):
        if brain.terrain.inside(candidate) and candidate not in brain.terrain.blocked:
            return candidate
    return None


def step_toward(brain, source, target, exact: bool, hops: bool = False):
    """First cardinal step of a safe route, or None if there is no route.

    With `hops`, the route may begin with a Launcher throw, which shows up as
    a next tile that is not adjacent. The Builder cannot act on that -- only
    the Launcher can throw -- so it walks toward the pickup ring instead and
    lets the Launcher do the rest.
    """
    from utils.pathfinding import first_step
    try:
        nxt = first_step(brain.terrain, source, target, exact=exact, hops=hops)
    except Exception:
        return None
    if nxt is None or nxt == source:
        return None
    step = (nxt[0] - source[0], nxt[1] - source[1])
    if abs(step[0]) + abs(step[1]) != 1:
        return None                     # a throw: stand still and be thrown
    from brain import STEP_DIR
    return STEP_DIR.get(step)


def walk(brain, ct, target, exact: bool, hops: bool = False) -> bool:
    """Take a step toward `target`, and actually verify that it happened.

    The route comes from our own map, which is optimistic about ground nobody
    has looked at and stale about ground somebody has left. So the step it
    returns is a proposal, and `ct.move` refusing it has to be handled rather
    than swallowed. It was not: on helheim a Builder thrown across the map by
    an enemy Launcher recomputed the same illegal step for 120 of the game's
    284 rounds, standing on one tile, while the log cheerfully recorded that
    it was walking home.

    Any legal cardinal step that closes the distance is better than none, so
    the refusal falls back to those before giving up.
    """
    step = step_toward(brain, brain.me, target, exact=exact, hops=hops)
    if step is not None and ct.can_move(step):
        return _moved(brain, attempt(ct.move, step))
    me = brain.me
    best = None
    for direction in CARDINALS:
        spot = (me[0] + DELTA[direction][0], me[1] + DELTA[direction][1])
        if not ct.can_move(direction):
            continue
        gap = manhattan(spot, target)
        if best is None or gap < best[0]:
            best = (gap, direction)
    if best is not None and best[0] < manhattan(me, target):
        return _moved(brain, attempt(ct.move, best[1]))
    # Nothing helps. If this has gone on, take the least bad legal step
    # anyway: a Builder pinned by its own team only comes free if somebody
    # gives ground, and standing still is worth nothing either way.
    brain.frozen += 1
    if best is not None and brain.frozen >= UNSTICK_AFTER:
        debug.intent(brain, ct, "move", "UNSTICK",
                     f"pinned {brain.frozen} turns short of {target}")
        return _moved(brain, attempt(ct.move, best[1]))
    return False


def _moved(brain, ok: bool) -> bool:
    """Record whether a step actually happened. See UNSTICK_AFTER."""
    brain.frozen = 0 if ok else brain.frozen + 1
    return ok


def attempt(action, *args) -> bool:
    """Run a Controller action, swallowing a refusal.

    An uncaught exception removes the unit from the match permanently, so
    every call the bot makes is wrapped. can_* is checked first everywhere
    this is used; this is the second line of defence, not the first.
    """
    try:
        action(*args)
        return True
    except GameError:
        return False


_LETTER = {Direction.NORTH: "N", Direction.EAST: "E",
           Direction.SOUTH: "S", Direction.WEST: "W"}

from utils.GCS.Base.protocol import TILE_STATES as STATES  # noqa: E402


def name_of(state: int) -> str:
    return STATES[state]
