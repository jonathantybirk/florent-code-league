"""Which deposits to mine, and the conveyor tree that drains them.

The whole network is decided on round zero from the atlas, before a single
Builder has moved.  Two ideas carry it:

*Pick the deposits we can hold.*  A deposit no closer to us than to the enemy
Core is one we walk further to reach and further to defend, so the opening
wave takes only the near half.  The rest stay in the list, ordered, for later
Builders to pick up once the first lanes are paying.

*Share the trunk, but only four deep.*  Routing each deposit to the Core
independently would lay four parallel lanes down the same corridor, so each
lane walks down the distance-to-Core gradient and prefers a tile some earlier
lane has already claimed -- the cheap greedy Steiner heuristic.

The limit is throughput, and it is the thing that decides the whole design.  A
conveyor holds one stack and moves it one tile a round, so a tile carries at
most 10 Ti a round.  A Harvester produces 10 Ti every four rounds.  Four
Harvesters therefore saturate a lane, and the fifth is not slow -- it is free
titanium poured on the floor.  Merging without counting cost more than half
the income on the ore-rich maps: eighteen deposits on yggdrasil, all built,
all draining into one trunk, delivered what four would have.  So every tile
carries a load, and a lane joins the trunk only where there is room.

Cost matters here because every unit recomputes this independently inside a
10 ms budget.  The whole thing is two floods and a walk down the gradient per
deposit; nothing searches.
"""

from board import STEPS, flood

# Harvesters one conveyor tile can carry: 10 Ti a round through the tile
# against 10 Ti every four rounds out of each Harvester.
CAPACITY = 4
ORDER_GAIN_MIN = 100       # do not churn the executor for a modelled rounding win

# A lane never crosses a deposit: a conveyor there would cost us the deposit,
# and a Harvester there would cut the lane.
#
# Two Harvesters cardinally adjacent to each other feed each other -- output
# goes to an adjacent *building*, round-robin, and a Harvester does not
# forward what it receives -- so a stack sent that way is simply lost.  This
# is why `choose` drops the second of any adjacent pair.


class Lane:
    """One deposit and the conveyor tiles that connect it to the tree.

    `tiles` runs Core-outward and holds (tile, direction) pairs, the direction
    being the way that conveyor pushes -- always toward the tile before it.
    `entry` is the walkable tile a Builder stands on to build `tiles[0]`, and
    `stand` the tile it stands on to build the Harvester.
    """

    __slots__ = ("deposit", "tiles", "entry", "stand", "cost")

    def __init__(self, deposit, tiles, entry, stand):
        self.deposit = deposit
        self.tiles = tiles
        self.entry = entry
        self.stand = stand
        # Rounds of Builder time: one to build each tile, one to step onto it,
        # and one for the Harvester at the end.
        self.cost = 2 * len(tiles) + 1


def survey(board, limit=None):
    """(deposits worth a lane, nearest first; their distance field)."""
    home = flood(board, board.home_tiles, blocked=board.ore)
    away = flood(board, board.away_tiles, blocked=board.ore)
    return choose(board, home, away, limit), home


def lay(board, picks, home):
    """The lanes for `picks`, routed in the order given.

    The order matters more than it looks.  A lane is a wall to every later
    lane, so short lanes laid first pack tight around the Core and box the
    remaining ring tiles out of reach; long lanes laid first take the
    corridors and leave the short ones to squeeze in afterwards.  Neither
    order wins everywhere -- nearest-first routes five more deposits on
    midgard, farthest-first four more on snowflake -- which is why the caller
    lays both and keeps whichever delivers more titanium.
    """
    return _lanes(board, picks, home)


def insertion_orders(picks):
    """Cheap, deterministic alternatives to the two fragile distance orders."""
    candidates = (
        picks,
        picks[::-1],
        picks[::2] + picks[1::2],
        sorted(picks),
        sorted(picks, reverse=True),
    )
    seen = set()
    for order in candidates:
        key = tuple(order)
        if key not in seen:
            seen.add(key)
            yield order


def plan(board, limit=None):
    """The lanes to build, nearest deposit first."""
    picks, home = survey(board, limit)
    return _lanes(board, picks, home), home


def choose(board, home, away, limit=None):
    """Deposits worth a lane, nearest first.

    Ours before contested before theirs, and within each group the nearest
    first, so that truncating the list anywhere leaves a sensible opening.
    """
    scored = []
    for deposit in sorted(board.ore):
        near = _approach(board, deposit, home)
        if near is None:
            continue                      # walled off from our side entirely
        theirs = _approach(board, deposit, away)
        mine = home[near] + 1
        contested = 0 if theirs is None else (
            0 if mine <= away[theirs] + 1 else 1)
        scored.append((contested, mine, deposit))
    scored.sort()

    picks, claimed = [], set()
    for _, _, deposit in scored:
        pass
        picks.append(deposit)
        claimed.add(deposit)
        if limit is not None and len(picks) >= limit:
            break
    return picks


def _approach(board, deposit, dist):
    """The walkable neighbour of `deposit` nearest the flood's source."""
    best = None
    x, y = deposit
    for dx, dy in STEPS:
        spot = (x + dx, y + dy)
        step = dist.get(spot)
        if step is not None and (best is None or step < dist[best]):
            best = spot
    return best


def _lanes(board, picks, home):
    """Lay each deposit's run of conveyor into the growing tree."""
    tree = set(board.home_tiles)
    ring = set(board.ring())
    parent = {}                           # tile -> the tile it drains into
    load = {}                             # tile -> Harvesters draining through it
    out = []
    for deposit in picks:
        stand = _approach(board, deposit, home)
        if stand is None:
            continue
        path, join = _connect(board, stand, tree, parent, load)
        if join is None:
            continue                      # nowhere left to drain it
        tiles, previous = [], join
        for spot in path:
            tiles.append((spot, _delta(spot, previous)))
            previous = spot
        entry = _entry(board, tiles, tree, ring, stand)
        if entry is None:
            continue
        out.append(Lane(deposit, tiles, entry, stand))
        previous = join
        for spot in path:
            parent[spot] = previous
            previous = spot
        tree.update(path)
        _charge(board, stand, parent, load)
    return out


def _connect(board, stand, tree, parent, load):
    """The shortest run of fresh conveyor from `stand` into the drainable tree.

    Two rules make this a search rather than a walk down the gradient.

    A lane cannot cross another lane -- a tile holds one conveyor pointing one
    way -- so tiles already in the tree are junctions or they are walls, never
    ground to pass over.

    And a junction is only a junction if everything downstream of it still has
    room.  Where the trunk into the Core is already carrying four Harvesters,
    the nearest tree tile is the wrong answer and the right one is to lay a
    parallel run: three titanium and a couple of rounds a tile, once, against
    an income that would otherwise be poured on the floor for the rest of the
    match.

    Returns (tiles Core-outward, junction), or ([], None) when the deposit
    cannot be drained at all.
    """
    if stand in tree:
        return ([], stand) if _room(board, stand, parent, load) else ([], None)
    came = {stand: None}
    frontier = [stand]
    while frontier:
        nxt = []
        for tile in frontier:
            x, y = tile
            for dx, dy in STEPS:
                spot = (x + dx, y + dy)
                # The junction test comes before walkability on purpose: the
                # Core footprint is a perfectly good place to deliver into and
                # is the one tree tile a Builder can never stand on.
                if spot in tree:
                    if _room(board, spot, parent, load):
                        return _unwind(came, tile), spot
                    continue
                if spot in came or spot in board.ore:
                    continue
                if not board.walkable(spot):
                    continue
                came[spot] = tile
                nxt.append(spot)
        frontier = nxt
    return [], None


def _unwind(came, tile):
    """The chain from `tile` back to the deposit end: Core-outward order."""
    out = []
    while tile is not None:
        out.append(tile)
        tile = came[tile]
    return out


def _room(board, tile, parent, load) -> bool:
    """Whether one more Harvester fits through here and everything below it.

    The Core is the sink, not a conveyor: it has no stack to hold and no
    limit worth modelling. Counting its footprint as a four-Harvester tile
    stopped every map at eight lanes -- two entry tiles' worth -- however much
    open ground was left around it.
    """
    while tile is not None and tile not in board.home_tiles:
        if load.get(tile, 0) >= CAPACITY:
            return False
        tile = parent.get(tile)
    return True


def _charge(board, tile, parent, load):
    """Book one more Harvester against every tile between here and the Core."""
    while tile is not None and tile not in board.home_tiles:
        load[tile] = load.get(tile, 0) + 1
        tile = parent.get(tile)


def _entry(board, tiles, tree, ring, stand):
    """Where a Builder stands to lay the first tile of a lane.

    The tile before `tiles[0]` in the tree is the natural place, and usually
    it is a conveyor an earlier lane already laid.  When the lane starts at
    the Core the tile before it is Core footprint, which is never bot-passable
    even for us, and the Builder has to work from beside the lane instead.

    The one tile that will not do is one of this lane's own, unbuilt: a
    Builder cannot build the ground it is standing on, and a lane whose first
    tile can only be reached from its second is a lane that never starts.
    Everything else is fair, trunk conveyors included -- a conveyor is walkable
    ground.
    """
    if not tiles:
        return stand
    mine = {spot for spot, _ in tiles}
    first = tiles[0][0]
    before = (first[0] + tiles[0][1][0], first[1] + tiles[0][1][1])
    if board.walkable(before) and before not in mine:
        return before
    best = None
    for spot in board.neighbours(first):
        if spot in mine:
            continue
        # Prefer somewhere the crew is already going: a trunk tile, then the
        # spawn ring, then any open ground.
        rank = 0 if spot in tree else 1 if spot in ring else 2
        if best is None or rank < best[0]:
            best = (rank, spot)
    return best[1] if best else None




def _delta(spot, target):
    """The direction a conveyor at `spot` must face to push into `target`."""
    return (target[0] - spot[0], target[1] - spot[1])
