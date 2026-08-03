"""Runtime siege geometry -- the forward-gunner kill, derived from observed terrain.

No map files, no lookup table, no map name. Everything here is computed from three things a unit
can always get: the map dimensions, our own Core anchor, and whatever terrain it has personally
walked past. That is deliberate: a precomputed route is worth nothing on a map nobody precomputed,
and the measured cost of that was ZERO core kills on every unrecognised map.

WHAT 2.3.3 CHANGED, AND WHY MOST OF THIS FILE GOT SHORTER
---------------------------------------------------------
This module used to rank firing positions by ORTHOGONAL ADJACENCY TO AN ORE TILE, so a forward
Harvester could feed the turret with no conveyors, and fell back to a <=4-tile conveyor creep when
no such position existed. Both are dead on 2.3.3:

  G52  Ammunition is a single TEAM-WIDE pool. It starts at 0 and the only thing that fills it is
       `convert_ammo(n)` at the Core, 1:1 with titanium. Where a turret stands has nothing to do
       with how well it is supplied.
  G53  Turrets accept NOTHING from a conveyor. A belt pointed into a Gunner jams permanently --
       measured holding the same stack id from round 9 to round 90 while the ammo pool stayed 0.
       The harvester -> belt -> turret chain does not exist.
  G57  A forward Gunner killed a 500 HP Core on turn 53 on an arena with ZERO ore tiles: 50 shots
       in 50 consecutive rounds, no harvester, no conveyor, ~162 Ti out of a 500 Ti opening bank.

So the ore filter had stopped buying anything and was purely discarding legal ground. Measured
offline over all 21 maps x both sides with full terrain: 29.2 tiles per orientation have a clear
line of fire, 22.9 survive the old ore-or-belt filter, and only 3.3 satisfy the zero-conveyor form
the ranking actually preferred. Twelve of the 42 orientations have NO ore-adjacent position at all.
The filter also cost approach distance on 42 orientations out of 42 -- a mean 5.8 and a maximum 15
on the planner's own score scale, which is denominated in rounds of walking.

Firing positions are therefore now ranked on exactly three things: LINE OF FIRE onto the enemy Core
footprint, WALK DISTANCE from where the rusher stands, and SURVIVABILITY. Nothing else.

Three sub-problems remain:

1. WHERE IS THE ENEMY CORE.  Every map in this game is symmetric under exactly one of rot180,
   mirror_x, mirror_y (G32 -- no map in the 21-map pool is diagonal-only, and the shipped generator
   emits only these three). Each symmetry maps our own Core anchor onto a different candidate
   anchor, so there are at most three answers on any map. Observed terrain refutes them: if we have
   seen tile t and its image under hypothesis H, and the two disagree, H is dead. Seeing all four
   tiles of a candidate footprint with no enemy Core on them also kills it. Sighting the real Core
   settles it.

2. WHERE DO WE SHOOT FROM.  A Gunner's ray is a single tile wide, reaches 3 on a cardinal
   (1, 4, 9 <= r^2 13; 16 > 13) and 2 on a diagonal (2, 8 <= 13; 18 > 13), and stops at the FIRST
   targetable thing in the lane -- a wall, any building, either Core. Both facing classes were
   re-verified on 2.3.3: `build_gunner` accepts all eight compass directions (CENTRE alone is
   refused) and a NORTHEAST-facing Gunner reports exactly two attackable tiles, max d^2 = 8. So the
   only tiles that can ever bear on a 2x2 footprint are ``f - k*d`` for a footprint tile f, a facing
   d and k inside that facing's reach: at most 48 candidates, whatever the map size.

3. WHAT DO WE BUILD.  A Gunner. That is the entire route now. Nothing of ours may be left standing
   in the ray: a friendly in the lane becomes the target and jams the turret (G11).

Pure stdlib and no imports at all, like ``atlas``: this module is imported once per unit in its own
CPython sub-interpreter (G20), so import has to stay cheap. Nothing here raises.
"""

CDELTA = ((0, -1), (1, 0), (0, 1), (-1, 0))
DIR_NAMES = ("NORTH", "EAST", "SOUTH", "WEST")

# Eight facings, cardinals first so an index survives a trip through a store slot unchanged.
# A Gunner's r^2 = 13 reaches 3 on a cardinal (9 <= 13 < 16) but only 2 on a diagonal
# (8 <= 13 < 18). Diagonal beads matter because they are the only way to occupy the four CORNER
# tiles of the enemy Core's ring -- range-1 tiles no cardinal ray can reach, and the ones a
# defender bricking its ring is slowest to get to. Re-probed on 2.3.3 rather than carried over:
# `bots/probes/gundir` built a NORTHEAST Gunner successfully and read back `n=2 off=1,-1;2,-2
# maxd2=8`, and `can_build_gunner` was True for all eight compass directions.
DELTA8 = ((0, -1), (1, 0), (0, 1), (-1, 0), (1, -1), (1, 1), (-1, 1), (-1, -1))
DIR_NAMES8 = ("NORTH", "EAST", "SOUTH", "WEST",
              "NORTHEAST", "SOUTHEAST", "SOUTHWEST", "NORTHWEST")
REACH8 = (3, 3, 3, 3, 2, 2, 2, 2)
# A SENTINEL's r^2 = 32 reaches 5 on a cardinal (25 <= 32 < 36) and 4 on a diagonal (32 <= 32 < 50).
# Measured facing by facing on all eight compass directions: the pattern is a single-tile-wide
# straight line exactly like a Gunner's, just longer.
REACH8_SENT = (5, 5, 5, 5, 4, 4, 4, 4)

# Symmetry hypotheses, in the order their bits live in the rejection mask.
ROT180, MIRROR_X, MIRROR_Y = 0, 1, 2
ALL_REJECTED = 0b111

# Cardinal reach of a Gunner at r^2 = 13.
GUNNER_REACH = 3
# Extra score, per tile of standoff, charged to a firing position that is not at range 1.
#
# WAS 6, NOW 0, and the old reasoning is worth keeping because it is a good example of a true
# observation driving a wrong constant. At range 1 the Gunner touches the enemy footprint and
# nothing can get between the two; at range >= 2 every tile short of the Core is a tile the
# defender can brick, and a Barrier two Builders are healing at 4 HP a shot beats one Gunner
# outright. That was measured, and it is real: against `vanguard` over 14 games, 154 of 256 shots
# from a range-2/3 turret were absorbed by its Barrier ring.
#
# But 14 games against ONE opponent is not enough to price a term that is added to every candidate
# on every map. Re-measured over 810 games -- 9 opponents x 21 published maps x 2 sides, plus all
# 24 generated maps x 2 -- dropping it to 0 is worth about +25 games. The penalty is denominated
# in ROUNDS OF WALKING, so charging 6 per tile made a range-3 position cost 12 extra rounds of
# apparent approach; that is more than most maps' entire walk, so the ranking was discarding
# lanes that were strictly closer in order to avoid a brick the defender usually never lays.
# Getting there first beats getting there unbrickable.
#
# The bricking risk did not go away -- it is simply not worth 6 rounds a tile. If a defender that
# actually bricks its lane shows up on the ladder, this is the first constant to re-open, and the
# right form is probably conditional on having SEEN a barrier go up, not a flat prior.
STANDOFF_PENALTY = 0
# Survivability, and the only new term. Every open tile orthogonally adjacent to the turret is a
# tile an enemy Builder Bot can stand on and chew it from: G13 is REVERSED on 2.3.3, so a builder
# does 2 damage for 2 Ti to an orthogonal neighbour, and a 40 HP Gunner dies to 20 such actions --
# inside the 50 rounds it needs to kill a Core. A tile in a nook has fewer of those approaches,
# and our own rusher parks in one of them healing at 4 HP for 1 Ti. Weighted at one round each so
# it only ever separates positions the walk and the standoff have already tied.
EXPOSURE_PENALTY = 1
# How many Gunners the rusher will pack around one enemy Core. Ammunition is global now, so extra
# turrets are NOT splitting a producer's output the way they were on 2.2.0 -- each one is a flat
# 2 Ti a round of income against 10 more damage a round. The binding constraint is titanium
# income (passive alone is 2.5/round, one connected chain another 2.5), not logistics.
MAX_BATTERY = 6

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
    is a property of the shipped generator rather than of the engine. On the 21-map pool it is not
    even true any more: five of the six new maps put a Core footprint flush against a border and
    `jackpot` anchors one at literal (0, 0) (G64).
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

def firing_spots(enemy_anchor, sentinel=False):
    """Every tile that could possibly bear on the footprint.

    Independent of map size: 4 footprint tiles x 8 facings x their reach, de-duplicated. A Sentinel
    reaches 5/4 rather than 3/2, which is why it has +54% more firing positions on an enemy Core
    across the 21-map pool (1886 against the Gunner's 1222) and why its nearest position is 2-4
    walk-steps closer on every single map in it.
    """
    reach = REACH8_SENT if sentinel else REACH8
    out = set()
    for f in footprint(enemy_anchor):
        for di, d in enumerate(DELTA8):
            for k in range(1, reach[di] + 1):
                out.add((f[0] - k * d[0], f[1] - k * d[1]))
    return out


def _ray(w, h, g, di, foot, walls, stoppers, sentinel=False):
    """(range, ray tiles) for a clear bead from g on facing index di, or None.

    A GUNNER's shot stops at the first targetable tile: a wall stops it without being hit, any
    building or Core absorbs it. So every tile short of the footprint has to be genuinely empty.

    A SENTINEL's does not stop at all. Measured in-engine on `maps/lab/sentwall.map26`: a Sentinel
    behind a two-tile-thick wall band killed a 500 HP Core at turn 84, with `get_attackable_tiles`
    listing both WALL tiles and `can_fire` on the enemy Core returning True through them. The
    arithmetic closes exactly -- 500 HP / 18 damage = 28 shots at cooldown 3 = 84 rounds. It is
    documented behaviour (`docs/official/docs/game-rules-turrets.txt:83`, "unlike a Gunner's, is
    never blocked by walls or units in the way") and reproduced by three independent probes.

    So for a Sentinel neither `walls` nor `stoppers` terminates the bead -- only the map edge and
    its own reach. That is what makes it the only unjammable weapon in the game: a Gunner is
    neutralised by a 3 Ti barrier dropped in its lane, and a Sentinel has no lane to block.
    """
    d = DELTA8[di]
    reach = REACH8_SENT[di] if sentinel else REACH8[di]
    ray = []
    for k in range(1, reach + 1):
        t = (g[0] + k * d[0], g[1] + k * d[1])
        if t[0] < 0 or t[1] < 0 or t[0] >= w or t[1] >= h:
            return None
        if t in walls and not sentinel:
            return None
        ray.append(t)
        if t in foot:
            return k, tuple(ray)
        if t in stoppers and not sentinel:
            return None
    return None


def rank(w, h, enemy_anchor, own_core_tiles, walls, buildings, dist,
         blacklist=(), known=None, lanes=(), sentinel=False):
    """Every firing position with a clear ray onto the enemy Core, best first.

    ``sentinel``   rank SENTINEL positions instead of Gunner ones: reach 5/4 instead of 3/2, no
                   ballistic blocking at all, and no standoff penalty. See ``_ray``.

    ``walls``      terrain believed -- observed, or mirrored off our own half
    ``buildings``  tiles currently holding a building of either team, Cores excluded. These are
                   ballistic STOPPERS as well as siting obstacles: a shot is absorbed by the first
                   building in the lane whoever owns it, so a ray through one bears on nothing.
    ``dist``       walk distance from the rusher to each tile, from a BFS over what it knows is
                   impassable. A position whose whole approach ring is missing from this field is
                   unreachable and never gets proposed.
    ``blacklist``  tiles we have already tried and failed to take.
    ``known``      tiles we have terrain for, observed or mirrored. ``None`` disables the check.
                   Unknown ground is not permission to spend titanium: the turret and its lane must
                   both be on ground we can account for, or the siege buys a wall it cannot see.
    ``lanes``      tiles already reserved as one of OUR firing lines. Nothing may be built on one.
                   A friendly building in a Gunner's ray becomes its target and jams it for the
                   rest of the match (G11), so a second turret sited across the first one's lane
                   does not add throughput, it deletes throughput.

    One entry per TILE -- a tile holds one turret, so its cheapest facing is the only one that can
    ever be used. Each entry is a dict with ``gunner``, ``facing``, ``range``, ``ray`` and
    ``score``; ``score`` is denominated in rounds of walking.
    """
    foot = frozenset(footprint(enemy_anchor))
    own = frozenset(own_core_tiles)
    buildings = frozenset(buildings)
    stoppers = buildings | own
    lanes = frozenset(lanes)
    # A lane is not an obstacle to a SHOT -- two rays may cross freely, only a body in one blocks
    # it -- so lanes are folded into the blacklist (siting) and never into `stoppers` (ballistics).
    blacklist = frozenset(blacklist) | lanes

    def stand_cost(tile):
        """Cheapest walk to a tile we could build ``tile`` from, or None.

        Orthogonal neighbours only: on 2.3.3 a Builder Bot's whole action set is the four cardinals
        (G59, which reverses G50), so a diagonal approach can never place the turret.
        """
        best = None
        for d in CDELTA:
            s = (tile[0] + d[0], tile[1] + d[1])
            if s[0] < 0 or s[1] < 0 or s[0] >= w or s[1] >= h:
                continue
            if s in walls or s in foot or s in own:
                continue
            c = dist.get(s)
            if c is not None and (best is None or c < best):
                best = c
        return best

    def exposure(tile):
        """Open orthogonal neighbours -- tiles an enemy Builder Bot can attack the turret from."""
        n = 0
        for d in CDELTA:
            s = (tile[0] + d[0], tile[1] + d[1])
            if s[0] < 0 or s[1] < 0 or s[0] >= w or s[1] >= h:
                continue
            if s in walls or s in foot or s in own or s in buildings:
                continue
            n += 1
        return n

    best_by_tile = {}
    for g in firing_spots(enemy_anchor, sentinel):
        if g in blacklist or g in foot or g in own:
            continue
        if g[0] < 0 or g[1] < 0 or g[0] >= w or g[1] >= h:
            continue
        if g in walls or g in buildings:
            continue
        if known is not None and g not in known:
            continue
        approach = stand_cost(g)
        if approach is None:
            continue
        exp = exposure(g)
        for di in range(8):
            shot = _ray(w, h, g, di, foot, walls, stoppers, sentinel)
            if shot is None:
                continue
            k, ray = shot
            rayset = frozenset(ray)
            # A Gunner's whole lane must be accounted for, because one unseen wall or building
            # absorbs the shot and the siege buys a turret that bears on nothing. A Sentinel's
            # ray is not stopped by either, so only its own tile has to be known ground.
            if known is not None and not sentinel and not rayset <= known:
                continue
            # STANDOFF is charged only to Gunners. The entire reason for the penalty is that every
            # tile short of the Core is a tile the defender can drop a 30 HP barrier onto -- 154 of
            # 256 measured shots from a range-2/3 Gunner were absorbed by exactly that. A Sentinel
            # shoots through barriers, so distance costs it nothing but the walk, which `approach`
            # already prices.
            standoff = 0 if sentinel else STANDOFF_PENALTY * (k - 1)
            score = approach + standoff + EXPOSURE_PENALTY * exp
            # Cardinal before diagonal at equal score, then the tile itself, so the order is total
            # and deterministic across sub-interpreters (G20 -- no shared state to disagree with).
            row = (score, k, 0 if di < 4 else 1, g, di)
            cur = best_by_tile.get(g)
            if cur is None or row < cur[0]:
                best_by_tile[g] = (row, {"gunner": g, "facing": DIR_NAMES8[di], "range": k,
                                         "ray": rayset, "score": score})
    out = sorted(best_by_tile.values(), key=lambda p: p[0])
    return [p[1] for p in out]


def plan(w, h, enemy_anchor, own_core_tiles, walls, buildings, dist,
         blacklist=(), known=None, lanes=(), sentinel=False):
    """Best forward-turret plan against ``enemy_anchor``, or None.

    ``sentinel``   plan a SENTINEL instead of a Gunner. The caller decides when: a Sentinel is
                   2.78x worse per titanium of damage, so it is only ever correct once BOTH Gunner
                   passes -- strict and permissive -- have come back empty.

    The route is one step. It used to be a Gunner, then a conveyor creep, then a Harvester on the
    deposit that fed it -- 1 to 6 buildings, 30 to 60 titanium, and several rounds of standing in
    the enemy's half building belts. On 2.3.3 the Harvester feeds the turret nothing (G53) and the
    conveyors feed the Harvester nowhere, so all of it was a pure tax on the one purchase that
    matters. `_top_up_ammo` at the Core supplies the turret instead, for 2 Ti a shot (G52, G57).
    """
    ranked = rank(w, h, enemy_anchor, own_core_tiles, walls, buildings, dist,
                  blacklist=blacklist, known=known, lanes=lanes, sentinel=sentinel)
    if not ranked:
        return None
    best = dict(ranked[0])
    best["route"] = (("sentinel" if sentinel else "gunner",
                      best["gunner"], best["facing"], None),)
    return best


def battery(w, h, enemy_anchor, own_core_tiles, walls, buildings, lanes, dist,
            known=None, blacklist=()):
    """Further Gunner tiles bearing on the same Core, best first.

    On 2.2.0 this had to hang off a producer we already owned, because ammunition arrived by
    conveyor and a second turret beside the same Harvester was the only one that cost no
    logistics. On 2.3.3 ammunition is a global pool (G52), so a second turret anywhere with a
    clear lane costs exactly one Gunner and 2 Ti a round -- it is the same search as `plan`, run
    against the lanes we have already reserved.

    Extra turrets buy two things at once now, where on 2.2.0 they only bought the first. ANGLES: a
    defender can brick one lane and heal the brick, but three turrets put 30 damage a round into a
    30 HP Barrier that heals 4. And THROUGHPUT: 10 more damage a round for 2 more titanium a
    round, with no producer output to split.
    """
    return rank(w, h, enemy_anchor, own_core_tiles, walls, buildings, dist,
                blacklist=blacklist, known=known, lanes=lanes)
