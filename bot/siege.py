"""Runtime siege geometry -- the forward-gunner kill, derived from observed terrain.

No map files, no lookup table, no map name. Everything here is computed from three things a unit
can always get: the map dimensions, our own Core anchor, and whatever terrain it has personally
walked past. That is deliberate: a precomputed route is worth nothing on a map nobody precomputed,
and the measured cost of that was ZERO core kills on every unrecognised map.

The doctrine being implemented is G16: a Gunner parked with a clear single-tile ray onto the enemy
Core footprint, fed by a Harvester on an ore tile orthogonally adjacent to it, kills a 500 HP Core
with zero conveyors for well under 100 Ti. Three sub-problems:

1. WHERE IS THE ENEMY CORE.  Every map in this game is symmetric under exactly one of rot180,
   mirror_x, mirror_y (G32 -- no diagonal in the published pool, and the shipped generator emits
   only these three). Each symmetry maps our own Core anchor onto a different candidate anchor, so
   there are at most three answers on any map. Observed terrain refutes them: if we have seen tile
   t and its image under hypothesis H, and the two disagree, H is dead. Seeing all four tiles of a
   candidate footprint with no enemy Core on them also kills it. Sighting the real Core settles it.

2. WHERE DO WE SHOOT FROM.  A Gunner's ray is a single tile wide, reaches 3 on a cardinal
   (1, 4, 9 <= r^2 13; 16 > 13) and stops at the FIRST targetable thing in the lane -- a wall, any
   building, either Core. So the only tiles that can ever bear on a 2x2 footprint are
   ``f - k*d`` for a footprint tile f, a cardinal d and k in 1..3: at most 48 candidates, whatever
   the map size. Rank them by walk distance and prefer the ones with ore orthogonally adjacent,
   because that harvester feeds the turret with no conveyors for the defender to cut.

3. WHAT DO WE BUILD.  Gunner, then any conveyors, then the harvester -- turret end first, so the
   belt is live before the ammunition exists. Nothing of ours may be left standing in the ray:
   a friendly in the lane becomes the target and jams the turret permanently (G11).

Validated offline against the fifteen precomputed maps: given full terrain this module picks the
same tile, the same facing, the same ore and the same conveyor count as ``rushplan`` on 30/30
orientations, and finds a plan on 48/48 orientations of the generated pool.

Pure stdlib and no imports at all, like ``atlas``: this module is imported once per unit in its own
CPython sub-interpreter (G20), so import has to stay cheap. Nothing here raises.
"""

CDELTA = ((0, -1), (1, 0), (0, 1), (-1, 0))
DIR_NAMES = ("NORTH", "EAST", "SOUTH", "WEST")

# Eight facings, cardinals first so an index survives a trip through a store slot unchanged.
# A Gunner's r^2 = 13 reaches 3 on a cardinal (9 <= 13 < 16) but only 2 on a diagonal
# (8 <= 13 < 18). Diagonal beads used not to be generated at all, which threw away the four
# CORNER tiles of the enemy Core's ring -- the only range-1 tiles no cardinal ray can occupy, and
# the ones a defender bricking its ring is slowest to reach. Confirmed live rather than assumed:
# in `bots/rivals/vanguard`'s hands a NORTHWEST ray from (4,3) landed 19 shots on (2,1) on sprint.
DELTA8 = ((0, -1), (1, 0), (0, 1), (-1, 0), (1, -1), (1, 1), (-1, 1), (-1, -1))
DIR_NAMES8 = ("NORTH", "EAST", "SOUTH", "WEST",
              "NORTHEAST", "SOUTHEAST", "SOUTHWEST", "NORTHWEST")
REACH8 = (3, 3, 3, 3, 2, 2, 2, 2)

# Symmetry hypotheses, in the order their bits live in the rejection mask.
ROT180, MIRROR_X, MIRROR_Y = 0, 1, 2
ALL_REJECTED = 0b111

# Cardinal reach of a Gunner at r^2 = 13. Diagonal facings reach only 2 and are never chosen.
GUNNER_REACH = 3
# Beyond this a forward belt costs more than the shots it delivers, and hands the defender more
# 20 HP tiles to cut than one builder can hold.
MAX_CONVEYORS = 4
# At range 1 the Gunner touches the enemy footprint and NOTHING can ever get between the two. At
# range >= 2 every tile short of the Core is a tile the defender can put a 30 HP Barrier on, and a
# Barrier two Builders are healing at 4 HP a shot beats one Gunner outright. Measured against
# `vanguard` over 14 games: of 256 shots our single range-2/3 turret fired, 154 were absorbed by
# its Barrier ring -- 2 of 25 reached the Core on crossfire/a. The penalty is therefore charged
# PER TILE OF STANDOFF, not once: twelve rounds of extra walk is a cheap price for a lane that
# cannot be bricked.
STANDOFF_PENALTY = 6
# How many beads get the (comparatively expensive) belt search when no ore touches any of them.
# Each search is a 4-step flood, so this is the planner's worst-case CPU knob. It has to be
# generous rather than tight: ranking beads by walk alone puts a 3-belt position ahead of a
# 1-belt one two tiles further out, and cutting the list at six lost runestone and eight of the
# forty-eight generated orientations outright. Now that the standoff penalty is charged per tile,
# a tight cap is worse still -- the whole head of the list is range-1 tiles on the enemy Core's
# own ring, and on a map whose only deposits are seven rows away NONE of them can reach one. That
# cost random-...-011 its plan entirely at 24. The real CPU guard is the `cut` prune below, which
# skips the search outright whenever a free position already beats anything a belt could buy.
BELT_CANDIDATES = 64
# How many extra turrets may be packed around one forward producer. A Harvester delivers 10 Ti
# every four rounds and a Gunner burns 2 Ti a shot firing once a round, so ONE turret already
# takes 80% of a deposit's output: the second and third are not bought for throughput, they are
# bought for ANGLES. A defender can brick one lane and heal the brick; it cannot brick three at
# once, and three turrets put 30 damage a round into a 30 HP Barrier that heals 4.
MAX_BATTERY = 3

EMPTY, WALL, ORE = 0, 1, 2


def footprint(anchor):
    """The four tiles a Core occupies. The anchor is the TOP-LEFT of the 2x2 (G33)."""
    x, y = anchor
    return ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1))


def candidates(w, h, anchor):
    """Enemy Core anchors implied by each symmetry, indexed the way the mask bits are.

    A 2x2 footprint anchored at x spans [x, x+1]; its image under a flip of the x axis spans
    [w-2-x, w-1-x], so the image ANCHOR is w-2-x, not w-1-x.
    """
    x, y = anchor
    return ((w - 2 - x, h - 2 - y), (w - 2 - x, y), (x, h - 2 - y))


def transform(w, h, tile, index):
    """Map a tile onto its counterpart under one symmetry hypothesis."""
    x, y = tile
    if index == ROT180:
        return (w - 1 - x, h - 1 - y)
    if index == MIRROR_X:
        return (w - 1 - x, y)
    return (x, h - 1 - y)


def seed_mask(w, h, anchor):
    """Hypotheses already dead before a single tile is observed.

    Only what the map format itself guarantees: a candidate has to fit on the board, and the two
    Cores cannot overlap. Deliberately NOT the one-tile-margin rule -- a false rejection of the
    true hypothesis sends the whole siege to the wrong corner for the entire match, and the margin
    is a property of the shipped generator rather than of the engine.
    """
    mask = 0
    for i, c in enumerate(candidates(w, h, anchor)):
        if c[0] < 0 or c[1] < 0 or c[0] + 1 >= w or c[1] + 1 >= h:
            mask |= 1 << i
        elif abs(c[0] - anchor[0]) <= 1 and abs(c[1] - anchor[1]) <= 1:
            mask |= 1 << i
    return mask


def reject_by_tile(w, h, mask, terrain, tile, code):
    """Fold ONE newly observed tile into the rejection mask.

    Incremental on purpose. Rescanning the whole terrain memory every round for every unit is
    thousands of dict lookups against a 10 ms budget already shared with pathing; folding each tile
    once as it arrives costs three lookups and is exactly as complete, because the pair (t, T(t))
    is tested whichever of the two is observed second.
    """
    for i in range(3):
        bit = 1 << i
        if mask & bit:
            continue
        other = transform(w, h, tile, i)
        if other == tile:
            continue
        seen = terrain.get(other)
        if seen is not None and seen != code:
            mask |= bit
    return mask


def reject_by_footprint(w, h, anchor, mask, seen, enemy_core_tiles):
    """Kill any candidate whose whole footprint has been looked at and holds no enemy Core."""
    for i, c in enumerate(candidates(w, h, anchor)):
        bit = 1 << i
        if mask & bit:
            continue
        tiles = footprint(c)
        if all(t in seen for t in tiles) and not any(t in enemy_core_tiles for t in tiles):
            mask |= bit
    return mask


def alive(w, h, anchor, mask):
    """Surviving candidate anchors, de-duplicated, in mask-bit order."""
    out = []
    for i, c in enumerate(candidates(w, h, anchor)):
        if mask & (1 << i):
            continue
        if c not in out:
            out.append(c)
    return out


def symmetry_index(w, h, anchor, mask):
    """The one surviving hypothesis index, or None while still ambiguous.

    Distinct hypotheses can agree on the anchor (a map symmetric two ways); any of them then
    predicts the same mirrored terrain, so that ambiguity is not one that matters.
    """
    live = [i for i in range(3) if not mask & (1 << i)]
    if not live:
        return None
    if len(live) == 1:
        return live[0]
    cand = candidates(w, h, anchor)
    if len({cand[i] for i in live}) == 1:
        return live[0]
    return None


def index_mask(w, h, anchor, enemy_anchor):
    """Rejection mask implied by a KNOWN enemy anchor: everything inconsistent with it dies."""
    mask = 0
    for i, c in enumerate(candidates(w, h, anchor)):
        if c != enemy_anchor:
            mask |= 1 << i
    return mask if mask != ALL_REJECTED else 0


def mirror_terrain(w, h, index, terrain):
    """Predict the unseen half by reflecting everything we have walked past.

    The map is symmetric, so our own half IS the enemy half. Only terrain is mirrored: buildings
    are not part of the map and still have to be seen.
    """
    walls, ores, seen = set(), set(), set()
    for tile, code in terrain.items():
        other = transform(w, h, tile, index)
        if other in terrain:
            continue
        if other[0] < 0 or other[1] < 0 or other[0] >= w or other[1] >= h:
            continue
        seen.add(other)
        if code == WALL:
            walls.add(other)
        elif code == ORE:
            ores.add(other)
    return walls, ores, seen


# ---------------------------------------------------------------------------
# Firing geometry
# ---------------------------------------------------------------------------

def firing_spots(enemy_anchor):
    """Every tile that could possibly bear on the footprint.

    Independent of map size: 4 footprint tiles x 8 facings x their reach, de-duplicated.
    """
    out = set()
    for f in footprint(enemy_anchor):
        for di, d in enumerate(DELTA8):
            for k in range(1, REACH8[di] + 1):
                out.add((f[0] - k * d[0], f[1] - k * d[1]))
    return out


def _ray(w, h, g, di, foot, walls, stoppers):
    """(range, ray tiles) for a clear bead from g on facing index di, or None.

    A shot stops at the first targetable tile: a wall stops it without being hit, any building or
    Core absorbs it. So every tile short of the footprint has to be genuinely empty.
    """
    d = DELTA8[di]
    ray = []
    for k in range(1, REACH8[di] + 1):
        t = (g[0] + k * d[0], g[1] + k * d[1])
        if t[0] < 0 or t[1] < 0 or t[0] >= w or t[1] >= h:
            return None
        if t in walls:
            return None
        ray.append(t)
        if t in foot:
            return k, tuple(ray)
        if t in stoppers:
            return None
    return None


def _chain(reach, o, g):
    """Belt tiles from the turret back to the ore, each with its OUTPUT direction.

    Emitted turret-end first: the line has to be live before the harvester that feeds it exists,
    or the first stacks fall on bare ground.
    """
    walk, cur = [], o
    for _ in range(MAX_CONVEYORS + 2):
        if reach.get(cur, 0) <= 1:
            break
        nxt = None
        for d in CDELTA:
            n = (cur[0] + d[0], cur[1] + d[1])
            if reach.get(n, -1) == reach[cur] - 1:
                nxt = n
                break
        if nxt is None:
            return None
        cur = nxt
        walk.append(cur)
    else:
        return None
    seq = walk + [g]
    out = []
    for i, tile in enumerate(walk):
        dv = (seq[i + 1][0] - tile[0], seq[i + 1][1] - tile[1])
        if dv not in CDELTA:
            return None
        out.append((tile, DIR_NAMES[CDELTA.index(dv)]))
    out.reverse()
    return out


def _spread(w, h, g, rayset, walls, ore, buildings, own, known):
    """Walk distance from the turret tile over ground a conveyor could legally occupy.

    Ore tiles are entered but never left: a belt cannot stand on a deposit, so a deposit is only
    ever the far end of a chain.
    """
    dist = {g: 0}
    frontier = [g]
    step = 0
    while frontier and step <= MAX_CONVEYORS:
        step += 1
        nxt = []
        for cur in frontier:
            if cur != g and cur in ore:
                continue
            for d in CDELTA:
                n = (cur[0] + d[0], cur[1] + d[1])
                if n in dist or n[0] < 0 or n[1] < 0 or n[0] >= w or n[1] >= h:
                    continue
                if n in walls or n in rayset or n in buildings or n in own:
                    continue
                if known is not None and n not in known:
                    continue
                dist[n] = step
                nxt.append(n)
        frontier = nxt
    return dist


def plan(w, h, enemy_anchor, own_core_tiles, walls, ore, buildings, dist,
         blacklist=(), known=None):
    """Best forward-gunner plan against ``enemy_anchor``, or None.

    ``walls`` / ``ore``  terrain believed -- observed, or mirrored off our own half
    ``buildings``        tiles currently holding a building of either team, Cores excluded
    ``dist``             walk distance from the rusher to each tile, from a BFS over what it knows
                         is impassable. A bead whose whole approach ring is missing from this
                         field is unreachable and never gets proposed.
    ``known``            tiles we have terrain for, observed or mirrored. ``None`` disables the
                         check. Unknown ground is not permission to spend titanium: the turret,
                         its lane, its belt and its deposit must all be on ground we can account
                         for, or the siege buys a wall it cannot see.

    Returns a dict with ``route`` in the executor's format, plus ``ray``, ``gunner``, ``facing``,
    ``ore``, ``range``, ``conveyors`` and ``score``.
    """
    foot = frozenset(footprint(enemy_anchor))
    own = frozenset(own_core_tiles)
    stoppers = frozenset(buildings) | own
    blacklist = frozenset(blacklist)

    def stand_cost(tile, extra=()):
        """Cheapest walk to a tile we could build ``tile`` from, or None."""
        best = None
        for d in CDELTA:
            s = (tile[0] + d[0], tile[1] + d[1])
            if s[0] < 0 or s[1] < 0 or s[0] >= w or s[1] >= h:
                continue
            if s in walls or s in foot or s in own or s in extra:
                continue
            c = dist.get(s)
            if c is not None and (best is None or c < best):
                best = c
        return best

    zero, beads = [], []
    for g in firing_spots(enemy_anchor):
        if g in blacklist or g in foot or g in own:
            continue
        if g[0] < 0 or g[1] < 0 or g[0] >= w or g[1] >= h:
            continue
        # A turret standing ON the ore destroys the one thing that makes the position
        # self-sufficient, and a turret on unseen ground is a guess paid for in titanium.
        if g in walls or g in ore or g in buildings:
            continue
        if known is not None and g not in known:
            continue
        approach = stand_cost(g)
        if approach is None:
            continue
        for di in range(8):
            shot = _ray(w, h, g, di, foot, walls, stoppers)
            if shot is None:
                continue
            k, ray = shot
            rayset = frozenset(ray)
            if known is not None and not rayset <= known:
                continue
            pen = STANDOFF_PENALTY * (k - 1)
            touched = False
            for c in CDELTA:
                o = (g[0] + c[0], g[1] + c[1])
                if o not in ore or o in rayset or o in buildings or o in foot or o in own:
                    continue
                if o in blacklist:
                    continue
                if stand_cost(o, extra=rayset) is None:
                    continue
                touched = True
                zero.append((approach + pen, k, 0, g, di,
                             {"gunner": g, "facing": DIR_NAMES8[di], "range": k, "ore": o,
                              "ray": rayset, "conveyors": ()}))
            if not touched:
                beads.append((approach + pen, k, g, di, rayset))

    pool = zero
    if beads:
        # A short belt creep is a FIRST-CLASS option, not a last resort. It used to run only when
        # no position anywhere touched a deposit, which meant one ore tile happening to sit beside
        # a range-3 bead vetoed every range-1 bead on the board -- and a range-3 lane is exactly
        # what a defender bricks. Measured on sprint/a: the planner took (4,8) at range 3 because
        # the deposit at (3,8) touched it, and 11 of its first 27 shots were eaten by a Barrier at
        # (6,8). Belts are still charged 3 walk-tiles each, so nothing changes when the free
        # position was genuinely the better one.
        # One entry per TILE, keeping its cheapest facing. Eight facings roughly double the raw
        # bead list, and BELT_CANDIDATES is a cap on tiles searched, not on rays considered:
        # without this collapse the top of the list fills with four rays off the same square and
        # the tiles that actually admit a belt fall off the end. Measured: two orientations of
        # random-...-011 went from a working plan to none at all.
        best_bead = {}
        for row in beads:
            cur = best_bead.get(row[2])
            if cur is None or row[:2] < cur[:2]:
                best_bead[row[2]] = row
        beads = sorted(best_bead.values())
        cut = min(row[0] for row in zero) if zero else None
        for approach, k, g, di, rayset in beads[:BELT_CANDIDATES]:
            # Even a one-tile creep costs 3, so anything at or above the best free position's
            # score cannot win. Prunes the whole (comparatively expensive) flood in the common
            # case where a deposit already touches a good bead.
            if cut is not None and approach + 3 >= cut:
                continue
            reach = _spread(w, h, g, rayset, walls, ore, buildings, own, known)
            best_o = None
            for o in ore:
                if o in blacklist:
                    continue
                n = reach.get(o)
                if n is None or n < 2 or n - 1 > MAX_CONVEYORS:
                    continue
                if best_o is None or n < best_o[0]:
                    best_o = (n, o)
            if best_o is None:
                continue
            n, o = best_o
            chain = _chain(reach, o, g)
            if chain is None or len(chain) != n - 1:
                continue
            pool.append((approach + 3 * (n - 1), k, n - 1, g, di,
                         {"gunner": g, "facing": DIR_NAMES8[di], "range": k, "ore": o,
                          "ray": rayset, "conveyors": tuple(chain)}))
    if not pool:
        return None
    pool.sort(key=lambda row: row[:5])
    best = pool[0][5]
    route = [("gunner", best["gunner"], best["facing"], None)]
    for tile, facing in best["conveyors"]:
        route.append(("conveyor", tile, facing, None))
    route.append(("harvester", best["ore"], None, None))
    best["route"] = tuple(route)
    best["score"] = pool[0][0]
    return best


def battery(w, h, enemy_anchor, feeders, own_core_tiles, walls, ore, buildings, lanes, dist,
            known=None, blacklist=()):
    """Extra Gunner tiles packed around a producer we already own, best first.

    A Harvester round-robins its output into EVERY orthogonally adjacent building, so a second
    turret beside the deposit that already feeds the first costs a turret and no logistics
    whatsoever -- no belt for the defender to cut, no second walk across the map.

    It is not bought for throughput. One Gunner firing every round burns 2 Ti a round against a
    deposit's 2.5, so the deposit is nearly saturated already. It is bought for ANGLES: a Gunner
    at range >= 2 can be shut off completely by one 30 HP Barrier that two Builders keep healing
    at 4 HP a time, and that is exactly how `vanguard` beat this doctrine -- 154 of our 256 shots
    absorbed across 14 games, 23 of 25 on crossfire/a. A defender can brick one lane. Three
    turrets on three different bearings put 30 damage a round into whichever brick it chooses.

    ``lanes``  every tile already reserved as one of OUR firing lines. A building in a friendly
               turret's ray becomes its target and jams it for the rest of the match (G11), so a
               new turret may never be sited in an old one's lane -- the single mistake that
               would make this change strictly negative.
    """
    foot = frozenset(footprint(enemy_anchor))
    own = frozenset(own_core_tiles)
    stoppers = frozenset(buildings) | own
    feeders = frozenset(feeders)
    lanes = frozenset(lanes)
    blacklist = frozenset(blacklist)
    out = []
    for f in feeders:
        for c in CDELTA:
            g = (f[0] + c[0], f[1] + c[1])
            if g[0] < 0 or g[1] < 0 or g[0] >= w or g[1] >= h:
                continue
            if g in blacklist or g in lanes or g in foot or g in own or g in feeders:
                continue
            if g in walls or g in ore or g in buildings:
                continue
            if known is not None and g not in known:
                continue
            best = None
            for di in range(8):
                shot = _ray(w, h, g, di, foot, walls, stoppers)
                if shot is None:
                    continue
                k, ray = shot
                rayset = frozenset(ray)
                if known is not None and not rayset <= known:
                    continue
                # Never lay a lane over our own supply: the producer becomes the target and the
                # turret we just paid for shoots the deposit feeding it (G10/G11).
                if rayset & feeders or rayset & own:
                    continue
                approach = None
                for c2 in CDELTA:
                    s = (g[0] + c2[0], g[1] + c2[1])
                    if s[0] < 0 or s[1] < 0 or s[0] >= w or s[1] >= h:
                        continue
                    if s in walls or s in foot or s in own or s in rayset:
                        continue
                    v = dist.get(s)
                    if v is not None and (approach is None or v < approach):
                        approach = v
                if approach is None:
                    continue
                row = (STANDOFF_PENALTY * (k - 1) + approach, k, di, g,
                       {"gunner": g, "facing": DIR_NAMES8[di], "range": k, "ray": rayset})
                if best is None or row[:4] < best[:4]:
                    best = row
            if best is not None:
                out.append(best)
    out.sort(key=lambda row: row[:4])
    return [row[4] for row in out]
