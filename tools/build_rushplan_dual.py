#!/usr/bin/env python
"""Generate ``bot/rushplan.py`` -- the DUAL-USE firing-position tables, 15 maps x both teams.

Two halves, computed from the same geometry:

  A. ATTACK  every tile a Gunner of OURS could hit the ENEMY Core from, the ore that feeds it with
             zero conveyors, the walk from our spawn ring, and the kill turn.
  B. DEFEND  the exact mirror -- every tile the ENEMY could hit OUR Core from -- ranked by threat
             and filtered into a Barrier denial list that can never wall in our own Core.

Every geometric constant below was dumped LIVE from the engine, not assumed
(``bots/probe_ray``, ``bots/probe_time``, run through ``tools/probe_run.py``):

  GUNNER raw pattern, ``get_attackable_tiles_from(p, d, GUNNER)``, offsets relative to p::

      N  (0,-3) (0,-2) (0,-1)        NE (1,-1) (2,-2)
      E  (1, 0) (2, 0) (3, 0)        SE (1, 1) (2, 2)
      S  (0, 1) (0, 2) (0, 3)        SW (-1,1) (-2,2)
      W  (-1,0) (-2,0) (-3,0)        NW (-1,-1)(-2,-2)

  i.e. a single-tile ray, origin excluded, length 3 on the cardinals (1,4,9 <= 13) and 2 on the
  diagonals (2,8 <= 13; 18 > 13). We emit CARDINAL facings only: a diagonal facing is strictly
  worse (2 tiles of reach instead of 3) and the consuming interface is cardinal-only.

  CORE SPAWN RING, ``can_spawn`` over the 5x5 block centred on a Core anchored at (1,1)::

      y=-1  0 0 0 0 0        -> exactly the 12 tiles at Chebyshev distance 1 from the 2x2
      y= 0  0 1 1 1 1           footprint. Never the footprint itself, never further out.
      y= 1  0 1 0 0 1
      y= 2  0 1 0 0 1
      y= 3  0 1 1 1 1

  BUILDER CADENCE, 14 consecutive rounds of ``move(EAST)`` logged from a live builder: it moved on
  every single round and ``get_move_cooldown()``/``get_action_cooldown()`` both read 0 every round.
  So walking costs 1 round per tile; moving and acting are mutually exclusive within a round
  (docs/api-reference/robot-api.md:113).

Other engine facts used (docs/ground-truth.md):
  G05  ammo is titanium delivered INTO the turret; a chain into a turret scores 0 collected.
  G07  ONE global cost scale: cost = floor(scale*base); builder +.20, gunner +.10, harvester +.05,
       conveyor/barrier +.01.
  G11  a friendly body or building standing in the ray BECOMES the target and blocks the shot
       forever -- so neither the harvester, nor a conveyor, nor the builder may sit in the lane.

Run:  .\\.venv\\Scripts\\python.exe tools\\build_rushplan_dual.py [--emit]
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bot"))

import atlas  # noqa: E402

# --- measured engine constants ------------------------------------------------------------

CORE_HP = 500
GUNNER_DMG = 10
SHOTS_TO_KILL = CORE_HP // GUNNER_DMG          # 50
FIRE_TAIL = SHOTS_TO_KILL - 1                  # rounds between first and last shot

CARD = (("NORTH", (0, -1)), ("EAST", (1, 0)), ("SOUTH", (0, 1)), ("WEST", (-1, 0)))
CDELTA = tuple(d for _n, d in CARD)
CARD_NAME = {d: n for n, d in CARD}

# Diagonal facings reach only 2 tiles (2, 8 <= 13; 18 > 13). We never CHOOSE one for our own turret
# -- less reach for the same money, and the consuming interface is cardinal-only -- but the enemy
# may, so the DEFEND census must count them or it understates the threat by about 40%.
DIAG = (("NORTHEAST", (1, -1)), ("SOUTHEAST", (1, 1)),
        ("SOUTHWEST", (-1, 1)), ("NORTHWEST", (-1, -1)))
FACINGS = tuple((n, d, 3) for n, d in CARD) + tuple((n, d, 2) for n, d in DIAG)
CARD_ONLY = tuple((n, d, 3) for n, d in CARD)

# Standoff penalty used only to BREAK TIES between otherwise equal plans. At range 1 the Gunner is
# orthogonally adjacent to the enemy Core footprint and nothing can ever come between the two. At
# range >= 2 the intervening tile at distance 1 is on the enemy Core's own 12-tile spawn ring, so
# every Builder Bot they spawn lands in our lane and eats the shot instead of the Core (G11) --
# about 4 wasted shots per builder. Vs a passive opponent this costs nothing, which is exactly why
# it must not be allowed to change the reported kill_turn.
STANDOFF_PENALTY = 4


class Board:
    def __init__(self, rec):
        self.name = rec["name"]
        self.team_own_core = tuple(rec["own_core"])
        self.team_enemy_core = tuple(rec["enemy_core"])
        self.w = rec["width"]
        self.h = rec["height"]
        self.walls = rec["walls"]
        self.ore = frozenset(rec["ore"])
        self.own_core = frozenset(rec["own_core_tiles"])
        self.enemy_core = frozenset(rec["enemy_core_tiles"])
        self.cores = self.own_core | self.enemy_core
        self.own_ring = self.ring(self.own_core)
        self.enemy_ring = self.ring(self.enemy_core)

    def inb(self, p):
        return 0 <= p[0] < self.w and 0 <= p[1] < self.h

    def passable(self, p):
        """Walkable at match start: in bounds, not a wall, not a Core footprint tile."""
        return self.inb(p) and p not in self.walls and p not in self.cores

    def ring(self, core_tiles):
        """The 12 spawn tiles -- Chebyshev distance 1 from the footprint, footprint excluded."""
        out = set()
        for (cx, cy) in core_tiles:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    p = (cx + dx, cy + dy)
                    if p not in core_tiles and self.passable(p):
                        out.add(p)
        return frozenset(out)

    def bfs(self, sources, blocked=frozenset()):
        dist, q = {}, deque()
        for s in sources:
            if self.passable(s) and s not in blocked:
                dist[s] = 0
                q.append(s)
        while q:
            c = q.popleft()
            for d in CDELTA:
                n = (c[0] + d[0], c[1] + d[1])
                if n in dist or not self.passable(n) or n in blocked:
                    continue
                dist[n] = dist[c] + 1
                q.append(n)
        return dist


def firing_solutions(bd, target_core, buildable, facings=CARD_ONLY):
    """(tile, facing, range, ray) for every bead on ``target_core`` in one of ``facings``.

    A Gunner's shot stops at the FIRST targetable tile in the lane. At match start the only
    buildings on the board are the two Cores, so the only things that can end a ray early are the
    board edge, a wall (which is not itself targetable), and the OTHER Core.
    """
    out = []
    for x in range(bd.w):
        for y in range(bd.h):
            g = (x, y)
            if not buildable(g):
                continue
            for name, d, reach in facings:
                for k in range(1, reach + 1):
                    t = (g[0] + k * d[0], g[1] + k * d[1])
                    if not bd.inb(t) or t in bd.walls:
                        break
                    if t in target_core:
                        out.append((g, name, k,
                                    tuple((g[0] + j * d[0], g[1] + j * d[1])
                                          for j in range(1, k + 1))))
                        break
                    if t in bd.cores:
                        break
    return out


# --- cost model (G07) ---------------------------------------------------------------------

def cost_of(n_conveyors=0):
    scale, total, steps = 1.0, 0, []

    def buy(label, base, bump):
        nonlocal scale, total
        c = int(scale * base + 1e-9)
        total += c
        steps.append((label, c, round(scale, 4)))
        scale += bump

    buy("builder", 30, 0.20)
    buy("gunner", 10, 0.10)
    for _ in range(n_conveyors):
        buy("conveyor", 3, 0.01)
    buy("harvester", 20, 0.05)
    return total, steps


# --- construction schedule ------------------------------------------------------------------
# Round 0: the Core spawns the Builder Bot onto a spawn-ring tile; the bot is live the same round.
# It then moves exactly 1 tile per round (measured). A build is an action, and an action forfeits
# that round's move. So:
#       t_build(first)  = d_ring(stand1) + 1
#       t_build(next)   = t_build(prev) + dist(stand_prev -> stand_next) + 1
# The Harvester emits its first 10 Ti stack on the round it is built (docs), the stack lands in the
# turret on the following round, and the Gunner fires that round:
#       first_shot = t_harvester + n_conveyors + 1
#       kill round = first_shot + 49              (50 shots x 10 damage into 500 HP)
#       run_game 'turns' = kill round + 1


def schedule(bd, ring_dist, rayset, build_tiles):
    """Cheapest legal build schedule. Returns (t_last_build, stands, walk) or None.

    ``build_tiles`` is the ordered list of tiles to build on, gunner first, harvester last. The
    builder must stand ORTHOGONALLY adjacent to each.

    The firing lane only becomes untouchable once the Gunner has ammo, which is the round after the
    Harvester goes up -- before that a body in the lane blocks nothing, because the turret cannot
    fire at all. So intermediate stands and every step of the walk may cross the lane freely; only
    the FINAL stand, where the builder is left parked, must be clear of it (G11).

    Of our own buildings only the Gunner blocks movement -- Harvesters, Conveyors and Splitters all
    read "Blocks movement: No" in the reference table -- but no building may be stood on to build
    the next one, so earlier build tiles are removed from the stand options either way.
    """
    stages = []
    last = len(build_tiles) - 1
    for i, tile in enumerate(build_tiles):
        built = frozenset(build_tiles[:i])
        opts = [s for s in ((tile[0] + c[0], tile[1] + c[1]) for c in CDELTA)
                if bd.passable(s) and s not in built and not (i == last and s in rayset)]
        if not opts:
            return None
        stages.append((built, sorted(opts)))

    blocker = frozenset(build_tiles[:1])          # the Gunner tile, once it exists

    cur = {}
    for s in stages[0][1]:
        if s in ring_dist:
            cur[s] = (ring_dist[s] + 1, (s,), ring_dist[s])
    if not cur:
        return None

    for i in range(1, len(stages)):
        opts = stages[i][1]
        nxt = {}
        for s_prev, (t_prev, path, walk) in cur.items():
            d = bd.bfs([s_prev], blocked=blocker - {s_prev})
            for s in opts:
                if s not in d:
                    continue
                cand = (t_prev + d[s] + 1, path + (s,), walk)
                if s not in nxt or cand[:2] < nxt[s][:2]:
                    nxt[s] = cand
        cur = nxt
        if not cur:
            return None
    return min(cur.values(), key=lambda v: v[:2])


def conveyor_chain(bd, dist_from_g, o, g):
    """Belt tiles from the turret side back to the ore, each with its OUTPUT direction."""
    chain, cur = [], o
    while dist_from_g[cur] > 1:
        nxt = None
        for c in CDELTA:
            n = (cur[0] + c[0], cur[1] + c[1])
            if n in dist_from_g and dist_from_g[n] == dist_from_g[cur] - 1:
                nxt = n
                break
        if nxt is None:
            return None
        cur = nxt
        chain.append(cur)
    seq = chain + [g]
    out = []
    for i, tile in enumerate(chain):
        dv = (seq[i + 1][0] - tile[0], seq[i + 1][1] - tile[1])
        if dv not in CARD_NAME:
            return None
        out.append((tile, CARD_NAME[dv]))
    out.reverse()          # turret side first: the chain must be live before the harvester lands
    return out


# --- A. ATTACK --------------------------------------------------------------------------------

def attack_for(bd):
    def buildable(g):
        # A turret may not sit on a wall or a Core footprint. We also refuse ORE tiles: the ore is
        # the ammo supply, and a turret standing on it destroys the only thing that makes the
        # position self-sufficient.
        return bd.passable(g) and g not in bd.ore

    sols = firing_solutions(bd, bd.enemy_core, buildable)
    ring_dist = bd.bfs(bd.own_ring)

    zero, fed = [], []
    for g, facing, k, rr in sols:
        rayset = frozenset(rr)
        for c in CDELTA:
            o = (g[0] + c[0], g[1] + c[1])
            if o not in bd.ore or o in rayset or not bd.passable(o):
                continue
            sch = schedule(bd, ring_dist, rayset, [g, o])
            if sch is None:
                continue
            t_harv, stands, walk = sch
            zero.append({"g": g, "facing": facing, "range": k, "ore": o, "ray": rr,
                         "conveyors": (), "nconv": 0, "stands": stands, "walk": walk,
                         "t_harv": t_harv, "turns": t_harv + 1 + FIRE_TAIL + 1})

    if not zero:
        for g, facing, k, rr in sols:
            rayset = frozenset(rr)
            dfg = bd.bfs([g], blocked=rayset)
            for o in bd.ore:
                if o in rayset or o not in dfg:
                    continue
                n = dfg[o] - 1
                if n <= 0 or n > 4:
                    continue
                chain = conveyor_chain(bd, dfg, o, g)
                if chain is None:
                    continue
                sch = schedule(bd, ring_dist, rayset, [g] + [c[0] for c in chain] + [o])
                if sch is None:
                    continue
                t_harv, stands, walk = sch
                fed.append({"g": g, "facing": facing, "range": k, "ore": o, "ray": rr,
                            "conveyors": tuple(chain), "nconv": n, "stands": stands, "walk": walk,
                            "t_harv": t_harv, "turns": t_harv + n + 1 + FIRE_TAIL + 1})

    pool = zero or fed
    if not pool:
        return None, sols, zero

    def key(p):
        pen = 0 if p["range"] == 1 else STANDOFF_PENALTY
        return (p["turns"] + pen, p["range"], p["nconv"], p["g"], p["facing"])

    best = min(pool, key=key)
    best["ti"], best["cost_steps"] = cost_of(best["nconv"])
    best["t_gunner"] = best["walk"] + 1
    best["first_shot"] = best["t_harv"] + best["nconv"] + 1
    return best, sols, zero


# --- B. DEFEND --------------------------------------------------------------------------------

def defend_for(bd, our_plan):
    """Every tile the ENEMY could shoot OUR Core from, ranked, then filtered into a deny list."""
    # The threat census is deliberately MAXIMAL. Probed live: can_build_gunner / can_build_barrier /
    # can_build_conveyor / can_build_harvester are all True on an ORE tile, so the enemy is free to
    # park a turret on ore and we must count those tiles as threats even though we will not barrier
    # them ourselves.
    def their_buildable(g):
        return bd.passable(g)

    # Cardinal AND diagonal: the enemy is under no obligation to face a cardinal.
    threats = firing_solutions(bd, bd.own_core, their_buildable, FACINGS)
    from_enemy = bd.bfs(bd.enemy_ring)

    # tiles our own plan owns: the turret, its lane, its ore.
    ours = set()
    if our_plan is not None:
        ours.add(our_plan["g"])
        ours.update(our_plan["ray"])
        ours.add(our_plan["ore"])
        ours.update(t for t, _f in our_plan["conveyors"])

    agg = {}
    for g, _f, k, _rr in threats:
        e = agg.setdefault(g, {"lanes": 0, "min_range": 9})
        e["lanes"] += 1
        e["min_range"] = min(e["min_range"], k)

    excluded = {"own_spawn_ring": 0, "own_firing_lane": 0, "on_ore": 0, "unreachable": 0,
                "would_wall_us_in": 0}
    ranked = []
    for g, e in sorted(agg.items()):
        if g in bd.own_ring:
            excluded["own_spawn_ring"] += 1
            continue
        if g in ours:
            excluded["own_firing_lane"] += 1
            continue
        if g in bd.ore:
            # a Barrier on ore seals a harvest site; never worth it
            excluded["on_ore"] += 1
            continue
        if g not in from_enemy:
            excluded["unreachable"] += 1
            continue
        ore_adj = any((g[0] + d[0], g[1] + d[1]) in bd.ore for d in CDELTA)
        covers = sum(1 for g2, _f2, _k2, rr2 in threats if g in rr2 and g2 != g)
        ranked.append({"pos": g, "ore_adj": ore_adj, "d_enemy": from_enemy[g],
                       "covers": covers, "lanes": e["lanes"], "min_range": e["min_range"]})

    # Spec order: ore-adjacent first (no logistics needed there), then nearest to the enemy spawn.
    # Lane coverage and range are tiebreaks only.
    ranked.sort(key=lambda r: (not r["ore_adj"], r["d_enemy"], -r["covers"],
                               r["min_range"], r["pos"]))

    # Connectivity guard. Barriers block movement. Placing the whole list must leave our spawn ring
    # intact, still connected to itself, and still able to reach every ore tile we could reach
    # before. Anything that fails is dropped, greedily, in threat order.
    base = bd.bfs(bd.own_ring)
    want_ore = {o for o in bd.ore if o in base}
    keep, placed = [], set()
    for r in ranked:
        trial = placed | {r["pos"]}
        free_ring = bd.own_ring - trial
        if len(free_ring) < 8:
            excluded["would_wall_us_in"] += 1
            continue
        d = bd.bfs(free_ring, blocked=trial)
        if not all(o in d for o in want_ore) or not all(t in d for t in free_ring):
            excluded["would_wall_us_in"] += 1
            continue
        keep.append(r)
        placed = trial
    return keep, excluded, len(agg), len(bd.own_ring), len(threats)


def recommend(plan):
    """RUSH / HYBRID / ECON from the computed kill turn.

    The match runs 1000 rounds and one connected harvester is worth ~2490 collected over that span
    (G04), so economy is never a bad answer -- the question is only whether the kill lands before a
    competent opponent can build anything that shoots back. A kill inside ~80 turns beats every
    econ line outright; past ~120 we are betting the match on an unmolested lane, and a conveyor-fed
    plan is fragile enough (every belt tile is a shootable link) that it never earns RUSH.
    """
    if plan is None:
        return "ECON"
    if plan["nconv"] == 0 and plan["turns"] <= 80:
        return "RUSH"
    if plan["turns"] <= 120:
        return "HYBRID"
    return "ECON"


def analyse():
    rows = {}
    for name in atlas.MAP_NAMES:
        for team in ("a", "b"):
            bd = Board(atlas.by_name(name, team))
            plan, sols, zero = attack_for(bd)
            deny, excl, n_threat_tiles, n_ring, n_threat_sols = defend_for(bd, plan)
            rows[(name, team)] = {
                "bd": bd, "plan": plan, "deny": deny, "excl": excl,
                "n_fire_tiles": len({s[0] for s in sols}), "n_fire_sols": len(sols),
                "n_zero_tiles": len({z["g"] for z in zero}), "n_zero_opts": len(zero),
                "n_threat_tiles": n_threat_tiles, "n_threat_sols": n_threat_sols,
                "n_ring": n_ring, "rec": recommend(plan),
            }
    return rows


# --- emit -------------------------------------------------------------------------------------

HEADER = '''"""Dual-use firing-position tables for the 15-map pool -- GENERATED, DO NOT EDIT BY HAND.

Produced by ``tools/build_rushplan_dual.py`` from ``bot/atlas.py`` plus engine geometry dumped LIVE
(``get_attackable_tiles_from``, ``can_spawn``, a 14-round builder move trace). See that script's
docstring for the raw dumps.

Pure stdlib, no imports, literal tuples only: this module is imported by every unit in its own
CPython sub-interpreter (G20), so import must stay cheap.

A. ATTACK -- ``attack_plan(map_name, team)``
    A forward Gunner parked with a clear cardinal ray onto the enemy Core footprint, fed by a
    Harvester built on an ore tile orthogonally adjacent to the turret. Zero conveyors: a Harvester
    outputs directly into any adjacent building, and 10 Ti / 4 rounds of supply comfortably covers
    2 Ti / round of burn, so the turret never starves once the first stack lands.

    Timeline (round 0 = the Core spawns the builder onto its ring; builders move 1 tile/round and
    cannot move and act in the same round):
        t_gunner    = walk + 1
        t_harvester = t_gunner + (steps from the gunner stand to the ore stand) + 1
        first_shot  = t_harvester + conveyors + 1
        kill_turn   = first_shot + 49 + 1        (50 shots x 10 damage into a 500 HP Core,
                                                  +1 because run_game reports turns, not rounds)

    ``kill_turn`` assumes an unobstructed lane. At range >= 2 the ray crosses the enemy Core's own
    spawn ring, where an enemy Builder Bot becomes the target instead of the Core (G11), so range 1
    is preferred whenever it costs nothing.

B. DEFEND -- ``deny_tiles(map_name, team)``
    The exact mirror: every tile the ENEMY could shoot OUR Core from, ore-adjacent ones first (they
    need no logistics at all), then nearest to the enemy spawn. Already filtered -- nothing in our
    own 12-tile spawn ring, nothing in our own turret's firing lane, nothing on ore or a wall, and
    nothing whose Barrier would cut our spawn ring off from itself or from reachable ore.

    Note what the filter implies: the enemy can ALWAYS park a Gunner orthogonally adjacent to our
    Core, because those tiles are our own spawn ring and barriering them would wall in the Core.
    Denial necessarily starts at distance 2. Barriers are 3 Ti / 30 HP and block movement AND line
    of sight, so a barrier at distance 2 in a lane also shuts down the distance-3 tile behind it.
"""

'''

FOOTER = '''

_ATTACK_KEYS = ("fire_pos", "facing", "ore", "walk", "kill_turn", "ti_cost", "zero_conveyor")


def _key(map_name, team):
    """(name, 'a'|'b') or None. Accepts 'a'/'A'/'Team.A'/a Team enum. Never raises."""
    try:
        t = team if type(team) is str else str(team)
        t = t.strip().lower()
        if t.endswith("a"):
            t = "a"
        elif t.endswith("b"):
            t = "b"
        else:
            return None
        return (str(map_name), t)
    except Exception:
        return None


def attack_plan(map_name, team):
    """Forward-gunner plan, or None on an unknown map/team. Never raises.

    dict: ``fire_pos`` (x, y), ``facing`` 'NORTH'|'EAST'|'SOUTH'|'WEST', ``ore`` (x, y) or None,
    ``walk`` int, ``kill_turn`` int, ``ti_cost`` int, ``zero_conveyor`` bool.
    """
    try:
        k = _key(map_name, team)
        if k is None:
            return None
        row = _ATTACK.get(k)
        if row is None:
            return None
        return dict(zip(_ATTACK_KEYS, row))
    except Exception:
        return None


def deny_tiles(map_name, team):
    """Tiles to Barrier, most threatening first. Pre-filtered; may be (). Never raises."""
    try:
        k = _key(map_name, team)
        if k is None:
            return ()
        return _DENY.get(k, ())
    except Exception:
        return ()


def recommendation(map_name, team):
    """'RUSH' | 'HYBRID' | 'ECON'. Unknown maps fall back to 'ECON'. Never raises."""
    try:
        k = _key(map_name, team)
        if k is None:
            return "ECON"
        return _REC.get(k, "ECON")
    except Exception:
        return "ECON"


# --- extended detail, for callers that want to execute the plan step by step ------------------

_DETAIL_KEYS = ("map", "team", "own_core", "enemy_core", "gunner", "facing", "range", "ore",
                "conveyors", "ray", "stand", "stands", "walk", "t_gunner", "t_harvester",
                "first_shot", "kill_turn", "cost", "zero_conveyor", "n_firing_tiles",
                "n_zero_conveyor_options", "deny")


def plan(map_name, team):
    """Full plan dict (every key of ``_DETAIL_KEYS``), or None. Never raises."""
    try:
        k = _key(map_name, team)
        if k is None:
            return None
        row = _DETAIL.get(k)
        if row is None:
            return None
        d = dict(zip(_DETAIL_KEYS, row))
        d["deny"] = _DENY.get(k, ())
        return d
    except Exception:
        return None


def recommend(map_name, team):
    """Back-compatible alias of ``recommendation`` that returns None on an unknown map."""
    try:
        k = _key(map_name, team)
        if k is None:
            return None
        return _REC.get(k)
    except Exception:
        return None


def threat_tiles(map_name, team):
    """Unfiltered threat census: every tile the enemy could shoot our Core from, ranked.

    ``deny_tiles`` is this minus our spawn ring, our own lane, ore and anything that would wall us
    in. Exposed so a caller can reason about threats it is not allowed to barrier.
    """
    try:
        k = _key(map_name, team)
        if k is None:
            return ()
        return _THREAT.get(k, ())
    except Exception:
        return ()


MAP_NAMES = tuple(sorted({k[0] for k in _ATTACK}))
'''


def emit(rows, path):
    L = [HEADER]

    L.append("# (map, team) -> (fire_pos, facing, ore, walk, kill_turn, ti_cost, zero_conveyor)\n")
    L.append("_ATTACK = {\n")
    for k in sorted(rows):
        p = rows[k]["plan"]
        if p is None:
            L.append('    ("%s", "%s"): None,\n' % k)
            continue
        L.append('    ("%s", "%s"): ((%d, %d), "%s", (%d, %d), %d, %d, %d, %s),\n'
                 % (k[0], k[1], p["g"][0], p["g"][1], p["facing"], p["ore"][0], p["ore"][1],
                    p["walk"], p["turns"], p["ti"], p["nconv"] == 0))
    L.append("}\n\n")

    L.append("# (map, team) -> Barrier targets, most threatening first (already filtered)\n")
    L.append("_DENY = {\n")
    for k in sorted(rows):
        t = tuple(d["pos"] for d in rows[k]["deny"])
        body = ", ".join("(%d, %d)" % q for q in t)
        if len(t) == 1:
            body += ","
        L.append('    ("%s", "%s"): (%s),\n' % (k[0], k[1], body))
    L.append("}\n\n")

    L.append("# (map, team) -> unfiltered threat census, most threatening first\n")
    L.append("_THREAT = {\n")
    for k in sorted(rows):
        t = tuple(rows[k]["threat_all"])
        body = ", ".join("(%d, %d)" % q for q in t)
        if len(t) == 1:
            body += ","
        L.append('    ("%s", "%s"): (%s),\n' % (k[0], k[1], body))
    L.append("}\n\n")

    L.append("_REC = {\n")
    for k in sorted(rows):
        L.append('    ("%s", "%s"): "%s",\n' % (k[0], k[1], rows[k]["rec"]))
    L.append("}\n\n")

    L.append("_DETAIL = {\n")
    for k in sorted(rows):
        r = rows[k]
        p = r["plan"]
        if p is None:
            L.append('    ("%s", "%s"): None,\n' % k)
            continue
        bd = r["bd"]
        conv = ", ".join('((%d, %d), "%s")' % (c[0][0], c[0][1], c[1]) for c in p["conveyors"])
        conv = "(%s%s)" % (conv, "," if conv else "")
        ray = ", ".join("(%d, %d)" % q for q in p["ray"])
        ray = "(%s%s)" % (ray, "," if len(p["ray"]) == 1 else "")
        stands = ", ".join("(%d, %d)" % q for q in p["stands"])
        stands = "(%s%s)" % (stands, "," if len(p["stands"]) == 1 else "")
        L.append(
            '    ("%s", "%s"): ("%s", "%s", (%d, %d), (%d, %d), (%d, %d), "%s", %d, (%d, %d),\n'
            '        %s, %s, (%d, %d), %s, %d, %d, %d, %d, %d, %d, %s, %d, %d, None),\n'
            % (k[0], k[1], k[0], k[1], bd.team_own_core[0], bd.team_own_core[1],
               bd.team_enemy_core[0], bd.team_enemy_core[1], p["g"][0], p["g"][1], p["facing"],
               p["range"], p["ore"][0], p["ore"][1], conv, ray,
               p["stands"][0][0], p["stands"][0][1], stands, p["walk"], p["t_gunner"],
               p["t_harv"], p["first_shot"], p["turns"], p["ti"], p["nconv"] == 0,
               r["n_fire_tiles"], r["n_zero_opts"]))
    L.append("}\n")
    L.append(FOOTER)
    Path(path).write_text("".join(L), encoding="utf-8", newline="\n")


def report(rows):
    print("=" * 122)
    print("A. ATTACK -- forward Gunner onto the enemy Core")
    print("=" * 122)
    print("%-10s %-2s %6s %5s %-8s %-6s %2s %-8s %5s %3s %4s %4s %5s %5s %4s %-6s" % (
        "map", "tm", "fire", "zc", "gunner", "facing", "r", "ore", "walk", "cv",
        "Tgun", "Thrv", "shot1", "kill", "Ti", "rec"))
    zc = 0
    for k in sorted(rows):
        r = rows[k]
        p = r["plan"]
        if p is None:
            print("%-10s %-2s %6d %5d   *** NO SOLUTION ***" % (
                k[0], k[1], r["n_fire_tiles"], r["n_zero_tiles"]))
            continue
        if p["nconv"] == 0:
            zc += 1
        print("%-10s %-2s %6d %5d %-8s %-6s %2d %-8s %5d %3d %4d %4d %5d %5d %4d %-6s" % (
            k[0], k[1], r["n_fire_tiles"], r["n_zero_tiles"], "%d,%d" % p["g"], p["facing"],
            p["range"], "%d,%d" % p["ore"], p["walk"], p["nconv"], p["t_gunner"], p["t_harv"],
            p["first_shot"], p["turns"], p["ti"], r["rec"]))
    zc_maps = sorted(n for n in atlas.MAP_NAMES
                     if rows[(n, "a")]["plan"] and rows[(n, "b")]["plan"]
                     and rows[(n, "a")]["plan"]["nconv"] == 0
                     and rows[(n, "b")]["plan"]["nconv"] == 0)
    print("\nzero-conveyor (map,team) pairs: %d / 30" % zc)
    print("maps with a zero-conveyor kill on BOTH sides: %d / 15  %s" % (len(zc_maps), zc_maps))
    print("maps NOT zero-conveyor on both sides: %s"
          % sorted(set(atlas.MAP_NAMES) - set(zc_maps)))

    print()
    print("=" * 122)
    print("B. DEFEND -- tiles the ENEMY can shoot OUR Core from")
    print("=" * 122)
    print("%-10s %-2s %7s %6s %5s %6s %5s  %s" % (
        "map", "tm", "threat", "denied", "excl", "oreadj", "ring", "deny order (* = ore-adjacent)"))
    tot = {}
    for k in sorted(rows):
        r = rows[k]
        ne = sum(r["excl"].values())
        for a, b in r["excl"].items():
            tot[a] = tot.get(a, 0) + b
        oa = sum(1 for d in r["deny"] if d["ore_adj"])
        tiles = " ".join("%d,%d%s" % (d["pos"][0], d["pos"][1], "*" if d["ore_adj"] else "")
                         for d in r["deny"][:8])
        print("%-10s %-2s %7d %6d %5d %6d %5d  %s%s" % (
            k[0], k[1], r["n_threat_tiles"], len(r["deny"]), ne, oa, r["n_ring"], tiles,
            " ..." if len(r["deny"]) > 8 else ""))
    print("\ntotal deny candidates excluded: %d" % sum(tot.values()))
    print("exclusions by reason:", dict(sorted(tot.items())))


if __name__ == "__main__":
    rows = analyse()
    # Unfiltered threat census -- includes the tiles we are NOT allowed to barrier, same ranking.
    for k in rows:
        bd = rows[k]["bd"]
        threats = firing_solutions(bd, bd.own_core,
                                   lambda g, bd=bd: bd.passable(g) and g not in bd.ore, FACINGS)
        from_enemy = bd.bfs(bd.enemy_ring)
        seen = {}
        for g, _f, kk, _rr in threats:
            seen[g] = min(seen.get(g, 9), kk)
        cen = []
        for g, mr in seen.items():
            ore_adj = any((g[0] + d[0], g[1] + d[1]) in bd.ore for d in CDELTA)
            cen.append((not ore_adj, from_enemy.get(g, 10 ** 6), mr, g))
        cen.sort()
        rows[k]["threat_all"] = [c[3] for c in cen]
    report(rows)
    if "--emit" in sys.argv:
        emit(rows, ROOT / "bot" / "rushplan.py")
        print("\nwrote %s" % (ROOT / "bot" / "rushplan.py"))
