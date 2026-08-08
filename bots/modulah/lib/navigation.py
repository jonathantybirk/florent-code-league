"""MEASURED AND REJECTED -- kept for the numbers, not imported by any bot.

A vision-bounded BFS distance field, stepping to whichever neighbour is closer
to the goal. The motivation was real: greedy stepping has no memory of walls,
and on the 26x26 and 28x20 maps of the current official pool aegis was
building Harvesters and never finishing their chains.

It lost anyway, twice, on the full 15-map pool against steward/vidar/odin:

                        greedy    BFS only   BFS + bearing fallback
    titanium collected    740        387            472
    core hp at end         38          8             19
    games survived        5/45       3/45           4/45

Why: the field only covers tiles the unit can SEE, and a Builder sees radius
~4.5. Whenever the Core is out of sight the field never reaches the unit, so
every step fell through to an arbitrary legal move -- a random walk. Adding a
compass-bearing fallback recovered most of the loss and still did not beat
plain greedy, because the fallback is then doing the actual work.

The lesson is about scope, not about BFS. A local router cannot replace
knowing which way home is; steward pairs its distance map with a remembered
Core position and a map model, which is the missing half. Revisit this
together with a persistent internal map, not on its own.
"""


from __future__ import annotations

from collections import deque

from fcode import GameError, Position

from geometry import CARDINALS, in_bounds

# Tiles expanded before the search gives up. Vision holds ~140 tiles at most,
# so this never binds in practice; it exists so a pathological map cannot
# turn one Builder's turn into a timeout.
NODE_BUDGET = 400


def _passable(ct, pos: Position, goal: Position) -> bool:
    if not in_bounds(ct, pos):
        return False
    if pos.x == goal.x and pos.y == goal.y:
        return True  # the goal tile itself may hold the thing we walk to
    try:
        return ct.is_tile_passable(pos)
    except GameError:
        return False


def distance_field(ct, goal: Position) -> dict[tuple[int, int], int]:
    """Walking distance from `goal` to every reachable visible tile.

    Built outward from the goal rather than from the unit, so one field serves
    every unit heading to the same place and can be cached for the turn.
    """
    dist = {(goal.x, goal.y): 0}
    q = deque([goal])
    budget = NODE_BUDGET
    while q and budget > 0:
        cur = q.popleft()
        budget -= 1
        base = dist[(cur.x, cur.y)]
        for d in CARDINALS:
            nxt = cur.add(d)
            key = (nxt.x, nxt.y)
            if key in dist:
                continue
            try:
                if not ct.is_in_vision(nxt):
                    continue
            except GameError:
                continue
            if not _passable(ct, nxt, goal):
                continue
            dist[key] = base + 1
            q.append(nxt)
    return dist


def step_toward(ct, goal: Position, avoid=None):
    """Direction of the best legal step toward `goal`, or None.

    `avoid` is a set of tiles under enemy fire. It is a preference, not a
    veto: a unit with every route covered still moves rather than standing
    still and dying anyway, which is what a hard refusal would produce.
    """
    pos = ct.get_position()
    field = distance_field(ct, goal)
    here = field.get((pos.x, pos.y))

    best = None
    for d in CARDINALS:
        nxt = pos.add(d)
        key = (nxt.x, nxt.y)
        score = field.get(key)
        if score is None:
            continue
        if here is not None and score >= here:
            continue  # never step away from the goal
        try:
            if not ct.can_move(d):
                continue
        except GameError:
            continue
        penalty = 1 if (avoid and key in avoid) else 0
        rank = (penalty, score)
        if best is None or rank < best[0]:
            best = (rank, d)

    if best is not None:
        return best[1]

    # The field could not help: the goal is outside vision, so BFS never
    # reached us, or we are boxed in. Fall back to the compass bearing.
    #
    # This fallback is the whole reason the first BFS version measured WORSE
    # than greedy (collected 740 -> 386, core hp at end 38 -> 8): for a target
    # out of sight the field is empty, so every step became an arbitrary legal
    # move -- a random walk. BFS is the better local router; it is not a
    # replacement for knowing which way the Core is.
    dx, dy = goal.x - pos.x, goal.y - pos.y
    pref = []
    if abs(dx) >= abs(dy):
        if dx:
            pref.append(CARDINALS[1] if dx > 0 else CARDINALS[3])
        if dy:
            pref.append(CARDINALS[2] if dy > 0 else CARDINALS[0])
    else:
        if dy:
            pref.append(CARDINALS[2] if dy > 0 else CARDINALS[0])
        if dx:
            pref.append(CARDINALS[1] if dx > 0 else CARDINALS[3])

    for group in (pref, [d for d in CARDINALS if d not in pref]):
        for d in group:
            nxt = pos.add(d)
            if avoid and (nxt.x, nxt.y) in avoid:
                continue
            try:
                if ct.can_move(d):
                    return d
            except GameError:
                continue
    for d in pref + [d for d in CARDINALS if d not in pref]:
        try:
            if ct.can_move(d):
                return d
        except GameError:
            continue
    return None
