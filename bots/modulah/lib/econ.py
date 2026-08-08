"""Expected titanium arriving at the Core, as a per-round schedule.

The Core walks its supply network BACKWARDS from its own footprint and buckets
every stack it finds by how many hops away it is. A stack h hops out is
credited to the balance at round T+h, so the hop index IS the arrival round.

Two things this gets right that a naive version does not.

Splitter weight is 1/k, not 1/3
------------------------------
A Splitter round-robins over its outputs, but only over outputs that can
currently ACCEPT a stack. Measured on 2.3.6: a Splitter whose only live
output feeds the Core delivers byte-identically to a plain Conveyor over 575
rounds -- 144 stacks either way. Assuming a flat 1/3 undercounts that case
threefold, and it is the common case, because the docs' own tutorial suggests
using a Splitter as an ordinary chain segment.

Blocked outputs drop out of the rotation by themselves: a Conveyor pointing at
bare ground holds its stack forever rather than dumping it (measured -- the
spur held a stack in all 576 samples), so once full it stops accepting and the
rotation reverts to whatever still drains. So k is dynamic, and reading it
fresh each round is the whole fix.

The window is t+2 .. t+6
------------------------
Not t+1: a hop-1 stack is credited at T+1 and the Core's write only becomes
readable at T+1, so any reader already has it in get_global_resources().
Not t+7: a hop-h tile is at most h steps from the footprint, so dist_sq <= h^2
against CORE_VISION_RADIUS_SQ = 36. Six hops is the last one guaranteed
visible for every chain shape.

Known limitation
----------------
`hop h -> T+h` is verified at h=1 and assumes the path ahead is clear. Under a
saturated trunk, or where two chains merge, arrival order is decided by the
engine's per-edge priority (an LRU key plus a uniform random tie-break, both
read out of the binary) whose state the API does not expose. Deep buckets on a
congested network will run optimistic. Treat bucket 0-1 as reliable and the
tail as indicative.
"""

from __future__ import annotations

from fcode import Direction, EntityType, GameConstants, GameError, Position

from geometry import CARDINALS, building_at, entity_type_of, in_bounds

MAX_HOP = 6          # last hop guaranteed inside CORE_VISION_RADIUS_SQ
FIRST_PUBLISHED = 2  # hop 1 is already in the balance by the time anyone reads

# Depth 6 with up to 3 branches per Splitter is 729 nodes worst case. Real
# networks are nothing like that, but the platform kills a unit over 10 ms of
# CPU per turn, so the walk is bounded by work rather than trusted to be small.
NODE_BUDGET = 400


def _facing(ct, bid: int):
    try:
        return ct.get_direction(bid)
    except GameError:
        return None


def _holds_stack(ct, bid: int) -> bool:
    try:
        return ct.get_stored_resource(bid) is not None
    except GameError:
        return False


def _accepts_from(ct, src: Position, dst: Position) -> bool:
    """Can a stack move src -> dst right now?

    A Conveyor takes input on any side except the one it outputs to; a
    Splitter takes input only on its back; the Core takes input anywhere.
    Conveyors and Splitters hold exactly one stack, so an occupied tile
    accepts nothing -- which is what quietly removes a backed-up branch from a
    Splitter's rotation.
    """
    bid = building_at(ct, dst)
    kind = entity_type_of(ct, bid)
    if kind is None:
        return False
    if kind == EntityType.CORE:
        return ct.get_team(bid) == ct.get_team()
    if kind not in (EntityType.CONVEYOR, EntityType.SPLITTER):
        return False
    if _holds_stack(ct, bid):
        return False

    facing = _facing(ct, bid)
    if facing is None:
        return False
    # Direction the stack travels, and the side of dst it enters through.
    travel = src.cardinal_direction_to(dst)
    entry_side = travel.opposite()
    if kind == EntityType.CONVEYOR:
        return facing != entry_side
    return facing == travel  # Splitter: back-fed only, so flow matches facing


def _accepting_output_count(ct, pos: Position, facing) -> int:
    """How many of a Splitter's three outputs could take a stack this round."""
    n = 0
    back = facing.opposite()
    for d in CARDINALS:
        if d == back:
            continue
        target = pos.add(d)
        if in_bounds(ct, target) and _accepts_from(ct, pos, target):
            n += 1
    return n


def _feeders(ct, pos: Position, kind: EntityType):
    """Neighbours currently pointing a stack into pos, with a weight factor.

    Weight is the chance a stack sitting on that neighbour actually continues
    towards pos: 1.0 from a Conveyor, which has one fixed output, and 1/k from
    a Splitter, where k counts the outputs that can accept right now.
    """
    if kind == EntityType.SPLITTER:
        facing = _facing(ct, building_at(ct, pos))
        if facing is None:
            return
        directions = (facing.opposite(),)  # a Splitter is fed only from behind
    else:
        directions = CARDINALS

    for d in directions:
        m = pos.add(d)
        if not in_bounds(ct, m):
            continue
        bid = building_at(ct, m)
        m_kind = entity_type_of(ct, bid)
        if m_kind not in (EntityType.CONVEYOR, EntityType.SPLITTER):
            continue
        facing = _facing(ct, bid)
        if facing is None:
            continue
        if m_kind == EntityType.CONVEYOR:
            if facing == d.opposite():          # points back at pos
                yield m, m_kind, 1.0
        else:
            if d != facing:                     # pos is not behind the Splitter
                k = _accepting_output_count(ct, m, facing)
                if k:
                    yield m, m_kind, 1.0 / k


def arrivals_by_hop(ct, footprint) -> list[float]:
    """Expected stacks credited at each hop. Index h = round T+h.

    Index 0 is unused so the list reads as a round offset rather than an
    off-by-one waiting to happen.
    """
    out = [0.0] * (MAX_HOP + 1)
    seen_budget = NODE_BUDGET

    frontier: list[tuple[Position, EntityType, float]] = []
    for tile in footprint:
        for m, kind, w in _feeders(ct, tile, EntityType.CORE):
            frontier.append((m, kind, w))

    for hop in range(1, MAX_HOP + 1):
        if not frontier:
            break
        nxt: list[tuple[Position, EntityType, float]] = []
        for pos, kind, weight in frontier:
            bid = building_at(ct, pos)
            if bid is not None and _holds_stack(ct, bid):
                out[hop] += weight
            if hop < MAX_HOP and seen_budget > 0:
                for m, m_kind, factor in _feeders(ct, pos, kind):
                    seen_budget -= 1
                    if seen_budget <= 0:
                        break
                    nxt.append((m, m_kind, weight * factor))
        frontier = nxt
    return out


def published_schedule(ct, footprint) -> list[int]:
    """Whole stacks expected at t+2 .. t+6, ready for the store."""
    hops = arrivals_by_hop(ct, footprint)
    return [int(round(hops[h])) for h in range(FIRST_PUBLISHED, MAX_HOP + 1)]


def passive_per_round() -> float:
    """The guaranteed trickle. Deliberately NOT published.

    PASSIVE_TITANIUM_AMOUNT every PASSIVE_TITANIUM_INTERVAL rounds is a
    constant on a fixed phase, and every unit has get_current_round(). Putting
    it in the store would be spending bits on something already known.
    """
    return GameConstants.PASSIVE_TITANIUM_AMOUNT / GameConstants.PASSIVE_TITANIUM_INTERVAL


def titanium_over(schedule, rounds: int) -> int:
    """Titanium expected within the next `rounds` readable rounds, incl. passive.

    This is the number a Builder actually wants: "can I afford a Sentinel if I
    wait three rounds". Callers who only need a coarse class can bucket this
    rather than reading individual arrivals.
    """
    stacks = sum(schedule[:rounds])
    return stacks * GameConstants.STACK_SIZE + int(passive_per_round() * rounds)


def network_frontier(ct, footprint, anchor):
    """The far end of the supply network that is genuinely CONNECTED.

    Only the Core can answer this. A Builder sees radius ~4.5 and cannot tell
    a conveyor that delivers from one that is stranded -- so when Builders
    routed new chains to "the nearest friendly conveyor" they joined each
    other's dead spurs and grew a web that reached nothing. Infrastructure
    went up (14.7 conveyors, 5.3 Harvesters, both records) and titanium
    collected fell to 307.

    The Core already walks the network backward every round to build the
    arrival schedule, so the connected set is free. This returns the connected
    tile FURTHEST from the Core -- the frontier worth extending -- as an offset
    a Builder can act on.

    Returns None when there is no network yet, which correctly tells a Builder
    to start one at the Core instead.
    """
    reach = _connected(ct, footprint)
    if not reach:
        return None
    best = max(reach, key=lambda t: min(f.distance_squared(Position(*t)) for f in footprint))
    dx, dy = best[0] - anchor.x, best[1] - anchor.y
    if not (-8 <= dx <= 7 and -8 <= dy <= 7):
        return None
    return dx, dy


def _connected(ct, footprint) -> set:
    """Every tile feeding the Core, walked backward from the footprint.

    Same traversal as arrivals_by_hop, but collecting identity rather than
    stacks, and run to MAX_HOP so it covers the whole visible network.
    """
    seen = set()
    frontier = []
    for tile in footprint:
        for m, kind, _w in _feeders(ct, tile, EntityType.CORE):
            frontier.append((m, kind))
            seen.add((m.x, m.y))
    budget = NODE_BUDGET
    for _ in range(MAX_HOP):
        nxt = []
        for pos, kind in frontier:
            if budget <= 0:
                break
            for m, m_kind, _f in _feeders(ct, pos, kind):
                budget -= 1
                key = (m.x, m.y)
                if key in seen:
                    continue
                seen.add(key)
                nxt.append((m, m_kind))
        frontier = nxt
    return seen
