"""Lane planning: how a deposit gets connected to the Core.

A lane is a chain of conveyors carrying 10 Ti one tile per round. A Harvester
makes 10 Ti every 4 rounds, so one lane saturates at four Harvesters -- which
is where the soft capacity of four in the mining spec comes from, not from
taste.

The plan for one deposit is a route ``[s0, ..., sk]`` of tiles that will hold
conveyors, where ``s0`` is orthogonally adjacent to a sink (a Core tile, or a
conveyor we already own) and ``sk`` is orthogonally adjacent to the deposit.
Each conveyor faces its predecessor, so the stack walks inward; ``s0`` faces
the sink itself. A deposit already touching one of our conveyors yields the
empty route: it needs a Harvester and nothing else.

Why the route is searched from the deposit outward rather than from the Core:
the sink set is large (eight Core-adjacent tiles plus every conveyor we own)
and the deposit is a single tile, so one BFS from the deposit to the nearest
member of that set answers "which lane should this join" and "by what route"
in the same search. Searching from each candidate sink instead would be one
BFS per sink and would still have to compare them.
"""

from utils.pathfinding import travel

from brain import DELTA, STEP_DIR

D4 = ((0, -1), (1, 0), (0, 1), (-1, 0))


def orthogonal(tile):
    x, y = tile
    return [(x + dx, y + dy) for dx, dy in D4]


def sink_tiles(brain) -> set[tuple[int, int]]:
    """Tiles a finished lane may deliver into: the Core, or belt that reaches it.

    "Our own belt" is not good enough, and the difference is the whole
    economy. A conveyor we own that no longer reaches the Core delivers
    nothing, and joining a lane to it produces a Harvester feeding a dead
    stub. Once an enemy cuts the belt at the Core mouth -- which is exactly
    where a competent harasser cuts -- every lane planned afterwards attaches
    to the severed half and the team never earns another titanium.

    Traced on auroraveil against hildr_best: the conveyors laid on rounds 4-10
    at (9, 3), (9, 4), (9, 5) were gone by round 50, and the next 400 rounds
    built four Harvesters and a dozen conveyors onto the orphaned remainder
    for a final score of zero titanium collected, in both seats.

    `connected` already answers "does this tile reach the Core"; it just was
    not being asked. It is cached per round because plan_lane calls this once
    per candidate deposit.
    """
    core = brain.core_tiles()
    if not core:
        # We do not know where home is, so we cannot tell live belt from dead.
        return brain.our_conveyors()
    return core | connected(brain)


def plan_lane(brain, deposit):
    """Route of new conveyor tiles connecting `deposit` to the nearest sink.

    Returns ``(route, sink)`` where `route` is ordered sink-side first and may
    be empty (the deposit already touches our network), or ``None`` when no
    route exists. `sink` is the tile ``route[0]`` -- or the Harvester itself
    for an empty route -- will point into.
    """
    sinks = sink_tiles(brain)
    if not sinks:
        return None

    # Already touching the network: nothing to build but the Harvester.
    for nb in orthogonal(deposit):
        if nb in sinks:
            return [], nb

    # Conveyors may not sit on ore (it would waste the deposit) nor on any
    # tile a building already occupies. The deposit itself is excluded as a
    # route tile for the same reason -- the Harvester goes there.
    terrain = brain.terrain
    banned = set(brain.free_ore())
    banned.add(deposit)

    # Search outward from the deposit. Conveyor tiles must be buildable
    # ground, so hops are meaningless here and threat tiles are not special:
    # we are choosing where infrastructure lives, not walking.
    dist, prev = travel(terrain, deposit, goals=None, hops=False,
                        allow_fire=True, extra_blocked=banned)
    best = None
    for sink in sinks:
        for nb in orthogonal(sink):
            d = dist.get(nb)
            if d is not None and (best is None or d < best[0]):
                best = (d, nb, sink)
    if best is None:
        return None

    # Walk the parent links back from the sink-adjacent tile to the deposit;
    # that yields the route deposit-side first, so reverse it. The deposit
    # itself is the search source and is not a conveyor tile.
    _, node, sink = best
    chain = []
    while node is not None and node != deposit:
        chain.append(node)
        node = prev.get(node)
    # chain is [sink-adjacent, ..., deposit-adjacent]; route wants that order.
    return chain, sink


def connected(brain):
    """Our conveyor tiles that actually reach the Core.

    A belt only pays if a stack can walk all the way in, so "we own a
    conveyor" and "that conveyor delivers" are different questions. Flood out
    from the Core through our own belt to answer the second.
    """
    core = brain.core_tiles()
    if not core:
        return set()
    cached = getattr(brain, "_live_belt", None)
    if cached is not None and cached[0] == brain.round:
        return cached[1]
    ours = brain.our_conveyors()
    reached = set()
    frontier = [tile for tile in core]
    seen = set(core)
    while frontier:
        current = frontier.pop()
        for nb in orthogonal(current):
            if nb in seen or nb not in ours:
                continue
            seen.add(nb)
            reached.add(nb)
            frontier.append(nb)
    brain._live_belt = (brain.round, reached)
    return reached


def orphaned_harvesters(brain):
    """Our Harvesters whose belt no longer reaches the Core.

    This is what an enemy harasser leaves behind, and until now it was
    permanent: a deposit with our Harvester on it is no longer ORE_FREE, so no
    Builder would ever look at it again, and the 20 titanium it cost sat there
    producing into a severed belt for the rest of the match. Cutting our lane
    was therefore worth far more to the opponent than cutting theirs was to
    us -- they had to be repaired, we did not.
    """
    core = brain.core_tiles()
    if not core:
        return []
    live = connected(brain) | core
    out = []
    for tile in brain.our_harvesters():
        if not any(nb in live for nb in orthogonal(tile)):
            out.append(tile)
    out.sort(key=lambda t: min(abs(t[0] - c[0]) + abs(t[1] - c[1]) for c in core))
    return out


def conveyor_facings(route, sink):
    """Direction each route tile's conveyor must face, as ``{tile: Direction}``.

    ``route[0]`` faces `sink`; every later tile faces its predecessor.
    """
    out = {}
    previous = sink
    for tile in route:
        out[tile] = _facing(tile, previous)
        previous = tile
    return out


def _facing(frm, to):
    step = (to[0] - frm[0], to[1] - frm[1])
    return STEP_DIR.get(step)


def lane_cost(route) -> int:
    """Conveyors a route still needs. Used to compare deposits."""
    return len(route)


def score_deposit(brain, deposit, route, horizon=200):
    """Rough payoff of connecting `deposit`, in titanium over `horizon`.

    A Harvester makes 2.5 Ti/round once its lane runs. Building costs are
    scaled at the call site because only the Controller knows the current
    scale factor; here we price the route in tiles and the delay in rounds.
    Two rounds are spent per conveyor tile (build, then step onto it), so a
    long route costs income twice: once in titanium, once in the delay before
    any of it arrives.
    """
    tiles = len(route)
    delay = 2 * tiles + 4          # +4 for the Harvester end-game
    producing = max(0, horizon - delay)
    return 2.5 * producing - 3 * tiles
