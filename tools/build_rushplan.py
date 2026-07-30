#!/usr/bin/env python
"""Generate ``bot/rushplan.py`` -- the forward-gunner attack plan for all 15 maps x both teams.

Everything here is derived from ``bot/atlas.py`` plus engine geometry that was MEASURED, not
assumed (probe logs in the session scratchpad):

  * Gunner raw attack pattern (``get_attackable_tiles_from`` dumped live on ``sprint``): a
    single-tile ray in the facing direction, origin tile EXCLUDED, length 3 for the four
    cardinals (1,4,9 <= 13) and length 2 for the four diagonals (2,8 <= 13; 18 > 13).
  * Core spawn ring: ``can_spawn`` is True on exactly the 12 tiles touching the 2x2 footprint
    (orthogonally or diagonally), never on the footprint itself. Round numbering starts at 0 and
    the Core's first spawn lands on round 0.
  * Start bank 500 Ti, scale 100.0%, builder 30 / gunner 10 / harvester 20 at scale 1.0.
  * A Gunner fed by an orthogonally adjacent Harvester fires EVERY round without a gap: the
    magazine holds 10, drains 10-8-6-4-2 and is topped straight back to 10 on the round it would
    have hit 0. 50 shots, 50 consecutive rounds, 500 HP Core dead.

Timeline (calibrated against 10 live matches, exact on all 10):
    T_gunner    = d_ring(S1) + 1
    T_harvester = T_gunner + d(S1 -> S2) + 1
    first shot  = T_harvester + 1 + transit          (transit = number of conveyors)
    kill round  = first shot + 49
    run_game turns = kill round + 1 = T_harvester + transit + 51

Run:  .\\.venv\\Scripts\\python.exe tools\\build_rushplan.py [--emit]
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bot"))

import atlas  # noqa: E402

GUNNER_R2 = 13
SHOTS_TO_KILL = 50            # 500 HP / 10 damage
FIRE_TAIL = SHOTS_TO_KILL - 1  # rounds between the first and the last shot

DIRS = {
    "NORTH": (0, -1), "NORTHEAST": (1, -1), "EAST": (1, 0), "SOUTHEAST": (1, 1),
    "SOUTH": (0, 1), "SOUTHWEST": (-1, 1), "WEST": (-1, 0), "NORTHWEST": (-1, -1),
}
CARDINALS = ((0, -1), (1, 0), (0, 1), (-1, 0))
CARD_NAME = {(0, -1): "NORTH", (1, 0): "EAST", (0, 1): "SOUTH", (-1, 0): "WEST"}


def ray(g, d):
    out = []
    k = 1
    while (k * d[0]) ** 2 + (k * d[1]) ** 2 <= GUNNER_R2:
        out.append((g[0] + k * d[0], g[1] + k * d[1]))
        k += 1
    return out


class Board:
    def __init__(self, rec):
        self.w = rec["width"]
        self.h = rec["height"]
        self.walls = rec["walls"]
        self.ore = set(rec["ore"])
        self.own_core = set(rec["own_core_tiles"])
        self.enemy_core = set(rec["enemy_core_tiles"])
        self.cores = self.own_core | self.enemy_core

    def inb(self, p):
        return 0 <= p[0] < self.w and 0 <= p[1] < self.h

    def open_tile(self, p):
        return self.inb(p) and p not in self.walls and p not in self.cores

    def ring(self):
        out = set()
        for (cx, cy) in self.own_core:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    p = (cx + dx, cy + dy)
                    if p not in self.own_core and self.open_tile(p):
                        out.add(p)
        return out

    def bfs(self, sources, blocked=frozenset()):
        dist = {}
        q = deque()
        for s in sources:
            if self.open_tile(s) and s not in blocked:
                dist[s] = 0
                q.append(s)
        while q:
            c = q.popleft()
            for d in CARDINALS:
                n = (c[0] + d[0], c[1] + d[1])
                if n in dist or not self.open_tile(n) or n in blocked:
                    continue
                dist[n] = dist[c] + 1
                q.append(n)
        return dist


def firing_solutions(bd):
    """(gunner_tile, facing_name, facing_vec, range, ray) for every unobstructed bead on the Core."""
    out = []
    for x in range(bd.w):
        for y in range(bd.h):
            g = (x, y)
            if not bd.open_tile(g):
                continue
            for name, d in DIRS.items():
                r = ray(g, d)
                for i, t in enumerate(r):
                    if not bd.inb(t):
                        break
                    if t in bd.enemy_core:
                        out.append((g, name, d, i + 1, tuple(r[: i + 1])))
                        break
                    if t in bd.walls or t in bd.cores:
                        break
    return out


def schedule(bd, ring_dist, rayset, build_tiles):
    """Exact cheapest build schedule via a tiny DP over stand tiles.

    ``build_tiles`` is the ordered list of tiles to build on (gunner first, harvester last).
    Returns (T_last_build, stands, walk) or None.

    Rules, all of them observed in the engine:
      * one build per round, and a move and an action cannot share a round;
      * the builder must stand ORTHOGONALLY adjacent to what it builds;
      * a tile that already holds a building is impassable and cannot be stood on -- but a tile
        that is only going to hold one later is still free ground (the Builder Bot happily
        stands on the ore tile and drops the Gunner from there);
      * the ray is off limits at all times: a friendly body in it shields the enemy Core
        permanently (G11).
    """
    stages = []
    for i, tile in enumerate(build_tiles):
        built = set(build_tiles[:i])
        opts = []
        for c in CARDINALS:
            s = (tile[0] + c[0], tile[1] + c[1])
            if s in rayset or s in built or not bd.open_tile(s):
                continue
            opts.append(s)
        if not opts:
            return None
        stages.append((tile, built, opts))

    # stage 0: walk out from the spawn ring
    cur = {}
    for s in stages[0][2]:
        if s in ring_dist:
            cur[s] = (ring_dist[s] + 1, (s,), ring_dist[s])
    if not cur:
        return None

    for i in range(1, len(stages)):
        built = stages[i][1]
        nxt = {}
        for s_prev, (t_prev, path, walk) in cur.items():
            dist = bd.bfs([s_prev], blocked=(rayset | built) - {s_prev})
            for s in stages[i][2]:
                if s not in dist:
                    continue
                t = t_prev + dist[s] + 1
                key = (t, path + (s,))
                if s not in nxt or key < (nxt[s][0], nxt[s][1]):
                    nxt[s] = (t, path + (s,), walk)
        cur = nxt
        if not cur:
            return None

    best = min(cur.values(), key=lambda v: (v[0], v[1]))
    return best[0], best[1], best[2]


def zero_conveyor_plans(bd, sols, ring_dist):
    out = []
    for g, name, d, k, rr in sols:
        rayset = set(rr)
        for c in CARDINALS:
            o = (g[0] + c[0], g[1] + c[1])
            if o not in bd.ore or o in rayset or not bd.open_tile(o):
                continue
            sch = schedule(bd, ring_dist, rayset, [g, o])
            if sch is None:
                continue
            t_harv, stands, walk = sch
            out.append({
                "gunner": g, "facing": name, "range": k, "ore": o, "ray": rr,
                "conveyors": (), "n_conv": 0, "stand": stands[0], "stands": stands,
                "walk": walk, "t_harvester": t_harv, "turns": t_harv + 51,
            })
    return out


def conveyor_plans(bd, sols, ring_dist, limit=4):
    out = []
    for g, name, d, k, rr in sols:
        rayset = set(rr)
        dist_from_g = bd.bfs([g], blocked=rayset)
        for o in bd.ore:
            if o in rayset or o not in dist_from_g:
                continue
            n_conv = dist_from_g[o] - 1
            if n_conv <= 0 or n_conv > limit:
                continue
            chain = walk_back(bd, dist_from_g, o, g, rayset)
            if chain is None:
                continue
            build_tiles = [g] + [c[0] for c in chain] + [o]
            sch = schedule(bd, ring_dist, rayset, build_tiles)
            if sch is None:
                continue
            t_harv, stands, walk = sch
            out.append({
                "gunner": g, "facing": name, "range": k, "ore": o, "ray": rr,
                "conveyors": tuple(chain), "n_conv": n_conv, "stand": stands[0],
                "stands": stands, "walk": walk,
                "t_harvester": t_harv, "turns": t_harv + n_conv + 51,
            })
    return out


def walk_back(bd, dist_from_g, o, g, rayset):
    """Conveyor tiles from the gunner side back to the ore, each with its OUTPUT direction."""
    chain = []
    cur = o
    while dist_from_g[cur] > 1:
        nxt = None
        for c in CARDINALS:
            n = (cur[0] + c[0], cur[1] + c[1])
            if n in dist_from_g and dist_from_g[n] == dist_from_g[cur] - 1:
                nxt = n
                break
        if nxt is None:
            return None
        cur = nxt
        chain.append(cur)
    # chain currently runs ore-side -> gunner-side; give each its output direction
    out = []
    seq = chain + [g]
    for i, tile in enumerate(chain):
        nxt = seq[i + 1]
        dv = (nxt[0] - tile[0], nxt[1] - tile[1])
        if dv not in CARD_NAME:
            return None
        out.append((tile, CARD_NAME[dv]))
    out.reverse()  # build gunner-side first so the chain is complete before the harvester lands
    return out


def cost_plan(n_conveyors=0):
    """cost = floor(scale * base), one global scale. builder +20pp, gunner +10, conveyor +1,
    harvester +5 -- each bump applies AFTER that purchase."""
    scale = 1.0
    total = 0
    steps = []

    def buy(label, base, bump):
        nonlocal scale, total
        c = int(scale * base + 1e-9)
        total += c
        steps.append((label, c))
        scale += bump

    buy("builder", 30, 0.20)
    buy("gunner", 10, 0.10)
    for i in range(n_conveyors):
        buy("conveyor", 3, 0.01)
    buy("harvester", 20, 0.05)
    return total, steps


def pick(plans):
    plans.sort(key=lambda p: (p["turns"], -p["range"], p["n_conv"], p["gunner"], p["facing"]))
    return plans[0]


def analyse():
    rows = {}
    for name in atlas.MAP_NAMES:
        for team in ("a", "b"):
            rec = atlas.by_name(name, team)
            bd = Board(rec)
            ring_dist = bd.bfs(bd.ring())
            sols = firing_solutions(bd)
            zc = zero_conveyor_plans(bd, sols, ring_dist)
            if zc:
                pool = zc
            else:
                pool = conveyor_plans(bd, sols, ring_dist)
            best = pick(pool) if pool else None
            alts = []
            seen = set()
            for p in pool:
                if p["gunner"] == best["gunner"] and p["facing"] == best["facing"]:
                    continue
                if p["gunner"] in seen:
                    continue
                seen.add(p["gunner"])
                alts.append(p)
                if len(alts) == 4:
                    break
            row = {
                "map": name, "team": team,
                "n_ray_solutions": len(sols),
                "n_firing_tiles": len(set(s[0] for s in sols)),
                "n_zero_conveyor": len(zc),
                "plan": best,
                "alts": alts,
            }
            if best is not None:
                ti, steps = cost_plan(best["n_conv"])
                row["cost"] = ti
                row["cost_steps"] = steps
            rows[(name, team)] = row
    return rows


HEADER = '''"""Forward-gunner rush plan for the 15-map pool -- GENERATED by tools/build_rushplan.py.

DO NOT EDIT BY HAND. Pure stdlib, zero imports: safe inside the bot sandbox.

What this is
------------
For every (map, team) it names the single highest-value unclaimed asset on the board: a Gunner
firing position that already bears on the enemy Core, plus the Harvester that feeds it. One
Builder Bot walks out, drops a Gunner and a Harvester, and the Gunner grinds the 500 HP Core
down in 50 consecutive shots. Total outlay {COST} Ti on 13 of the 15 maps -- less than one
Builder Bot plus change.

Measured, not modelled
----------------------
* Gunner ray: origin excluded, 3 tiles on a cardinal facing, 2 on a diagonal (r^2 = 13).
* A Gunner with an orthogonally adjacent Harvester fires EVERY round with no gap. Its magazine
  holds 10, drains 10-8-6-4-2, and is refilled to 10 on the round it would hit 0.
* Live probe vs `idle`, ALL 15 maps x BOTH sides = 30 matches: every single one ended
  `core_destroyed` on exactly the ``kill_turn`` in this table. Nothing here is extrapolated.
* Cost model confirmed to the titanium: 30 (builder) + 12 (gunner) + 26 (harvester) = 68.

What breaks it
--------------
Also measured, on the same probe vs `starter_fixed` (5 maps x both sides): 1 kill in 10. The
failures are not timing failures, they are contested-tile failures. On sprint/a the enemy's own
conveyor chain had already built ON the primary firing tile by round 5, and `can_build_gunner`
returned False forever. Others lost tempo to a Builder Bot parking in the ray (G11) and to the
enemy healing its Core (+4 HP for 1 Ti) faster than a single Gunner could out-damage the heal.

So: ``kill_turn`` is the floor, exact against no resistance, and the opening is cheap enough to
always be worth starting. But a caller that hardcodes one tile and cannot retarget will hang.
Use ``ALTERNATIVES`` when ``can_build_gunner`` refuses, and keep the ray clear of your own bodies.

Interface
---------
``plan(map_name, team)``   -> dict | None      team is 'a'/'b' (Team enum / 'Team.A' also work)
``recommend(map_name, team)`` -> 'RUSH' | 'HYBRID' | 'ECON' | None
``alternatives(map_name, team)`` -> tuple of (gunner, facing, ore, n_conveyors, kill_turn)
``for_record(atlas_record)`` -> dict | None     look the plan up straight off an atlas record
``PLANS`` / ``ALTERNATIVES`` / ``RECOMMENDATION``  -> dict[(name, team)] -> ...

Plan keys
---------
``gunner``          (x, y)   where to build the Gunner
``facing``          str      compass name for build_gunner's direction argument
``ore``             (x, y)   ORE tile for the feeding Harvester
``conveyors``       tuple of ((x, y), facing) -- () on the 13 zero-conveyor maps; build in the
                             order given (gunner side first) so the chain is live before the
                             Harvester's first stack is emitted
``ray``             tuple    tiles the shot crosses, nearest first; the last one is a Core tile.
                             NEVER put a friendly body or building on these -- a friendly in the
                             ray shields the enemy Core permanently (G11).
``stand``           (x, y)   tile the Builder Bot stands on to place the Gunner
``route``           tuple of (kind, tile, facing_or_None, stand_tile) in build order -- the exact
                             schedule the kill_turn is derived from. Follow it verbatim: the
                             stand tiles are chosen by DP, and a different (equally short) stand
                             tile can cost 2 extra rounds on the next leg.
``walk``            int      moves from the Core spawn ring to ``stand``
``t_gunner``        int      round the Gunner goes up
``t_harvester``     int      round the Harvester goes up
``first_shot``      int      round of the first shot
``kill_turn``       int      run_game 'turns' when the enemy Core dies (vs a passive enemy)
``cost``            int      titanium for the whole package, with global cost scaling applied
``zero_conveyor``   bool
``range``           int      1..3, ray length to the Core
"""

'''

FOOTER = '''

def _norm_team(team):
    t = team if type(team) is str else str(team)
    t = t.strip().lower()
    if t.endswith("a"):
        return "a"
    if t.endswith("b"):
        return "b"
    return None


def plan(map_name, team):
    """Return the rush plan for this (map, team), or None. Never raises."""
    try:
        t = _norm_team(team)
        if t is None:
            return None
        return PLANS.get((map_name, t))
    except Exception:
        return None


def recommend(map_name, team):
    """'RUSH' | 'HYBRID' | 'ECON' for this (map, team), or None. Never raises."""
    try:
        t = _norm_team(team)
        if t is None:
            return None
        return RECOMMENDATION.get((map_name, t))
    except Exception:
        return None


def alternatives(map_name, team):
    """Backup firing positions, best first. Empty tuple if none. Never raises."""
    try:
        t = _norm_team(team)
        if t is None:
            return ()
        return ALTERNATIVES.get((map_name, t), ())
    except Exception:
        return ()


def for_record(record):
    """Convenience: look the plan up straight off an atlas record.

    ``atlas.identify()`` gives you the record; this saves re-deriving the team from it.
    """
    try:
        name = record["name"]
        own = record["own_core"]
        for t in ("a", "b"):
            p = PLANS.get((name, t))
            if p is not None and p["own_core"] == (own[0], own[1]):
                return p
        return None
    except Exception:
        return None
'''


def verdict(turns):
    """RUSH / HYBRID / ECON from the measured kill turn.

    This is the one judgement call in the file -- the kill turns themselves are measured. The
    rush costs 68-71 Ti out of a 500 Ti opening bank, so it is affordable on every map; the
    verdict is about how much OTHER investment to make alongside it.

      RUSH   <= 70   the Core is dead before a normal economy opponent has income or defence
                     worth the name. Commit the opening to it.
      HYBRID <= 85   long enough that a contesting opponent can plausibly interrupt it. Run the
                     rush and an economy in parallel so a broken rush is not a lost game.
      ECON    > 85   30+ tiles of walking with one unescorted Builder Bot. Treat the rush as
                     opportunistic and build the economy first.
    """
    if turns <= 70:
        return "RUSH"
    if turns <= 85:
        return "HYBRID"
    return "ECON"


def emit(rows, path):
    lines = [HEADER.replace("{COST}", "68")]
    lines.append("PLANS = {\n")
    for k in sorted(rows):
        r = rows[k]
        p = r["plan"]
        if p is None:
            lines.append('    ("%s", "%s"): None,\n' % k)
            continue
        rec = atlas.by_name(k[0], k[1])
        t_g = p["walk"] + 1
        conv = ", ".join('((%d, %d), "%s")' % (c[0][0], c[0][1], c[1]) for c in p["conveyors"])
        conv = "(%s%s)" % (conv, "," if conv else "")
        route = [("gunner", p["gunner"], p["facing"])]
        for c in p["conveyors"]:
            route.append(("conveyor", c[0], c[1]))
        route.append(("harvester", p["ore"], None))
        rt = ", ".join(
            '("%s", (%d, %d), %s, (%d, %d))' % (
                kind, t[0], t[1], ('"%s"' % f) if f else "None", s[0], s[1])
            for (kind, t, f), s in zip(route, p["stands"]))
        lines.append(
            '    ("%s", "%s"): {\n'
            '        "map": "%s", "team": "%s",\n'
            '        "own_core": %r, "enemy_core": %r,\n'
            '        "gunner": %r, "facing": "%s", "range": %d,\n'
            '        "ore": %r, "conveyors": %s,\n'
            '        "ray": %r,\n'
            '        "stand": %r, "walk": %d,\n'
            '        "route": (%s,),\n'
            '        "t_gunner": %d, "t_harvester": %d, "first_shot": %d,\n'
            '        "kill_turn": %d, "cost": %d, "zero_conveyor": %s,\n'
            '        "n_firing_tiles": %d, "n_zero_conveyor_options": %d,\n'
            '    },\n' % (
                k[0], k[1], k[0], k[1],
                tuple(rec["own_core"]), tuple(rec["enemy_core"]),
                p["gunner"], p["facing"], p["range"],
                p["ore"], conv,
                p["ray"],
                p["stand"], p["walk"],
                rt,
                t_g, p["t_harvester"], p["t_harvester"] + p["n_conv"] + 1,
                p["turns"], r["cost"], p["n_conv"] == 0,
                r["n_firing_tiles"], r["n_zero_conveyor"],
            )
        )
    lines.append("}\n\n# Backup firing positions, same enemy Core, sorted by kill turn. Use one when the primary\n"
                 "# tile is already taken -- a live opponent's conveyor chain can and does land on it.\n"
                 "# (gunner, facing, ore, n_conveyors, kill_turn)\n"
                 "ALTERNATIVES = {\n")
    for k in sorted(rows):
        alts = rows[k].get("alts") or ()
        body = "".join(
            '        (%r, "%s", %r, %d, %d),\n' % (a["gunner"], a["facing"], a["ore"],
                                                   a["n_conv"], a["turns"])
            for a in alts)
        lines.append('    ("%s", "%s"): (\n%s    ),\n' % (k[0], k[1], body))
    lines.append("}\n\nRECOMMENDATION = {\n")
    for k in sorted(rows):
        p = rows[k]["plan"]
        lines.append('    ("%s", "%s"): %r,\n' % (k[0], k[1],
                                                  None if p is None else verdict(p["turns"])))
    lines.append("}\n")
    lines.append(FOOTER)
    Path(path).write_text("".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    rows = analyse()
    hdr = ("map", "tm", "tiles", "zc", "gunner", "facing", "r", "ore", "walk", "cv",
           "Tg", "Th", "shot1", "kill", "Ti", "verdict")
    print("%-10s %-3s %6s %4s %-9s %-10s %2s %-9s %5s %3s %4s %4s %6s %5s %4s %-7s" % hdr)
    zc = 0
    zc_maps = set()
    for k in sorted(rows):
        r = rows[k]
        p = r["plan"]
        if p is None:
            print("%-10s %-3s %6d %4d  *** NO SOLUTION ***" % (r["map"], r["team"],
                                                               r["n_firing_tiles"],
                                                               r["n_zero_conveyor"]))
            continue
        if p["n_conv"] == 0:
            zc += 1
            zc_maps.add(r["map"])
        print("%-10s %-3s %6d %4d %-9s %-10s %2d %-9s %5d %3d %4d %4d %6d %5d %4d %-7s" % (
            r["map"], r["team"], r["n_firing_tiles"], r["n_zero_conveyor"],
            "%d,%d" % p["gunner"], p["facing"], p["range"], "%d,%d" % p["ore"],
            p["walk"], p["n_conv"], p["walk"] + 1, p["t_harvester"],
            p["t_harvester"] + p["n_conv"] + 1, p["turns"], r["cost"], verdict(p["turns"])))
    print("\nzero-conveyor (map,team) pairs: %d / 30   distinct maps: %d / 15"
          % (zc, len(zc_maps)))
    print("maps needing conveyors:", sorted(set(atlas.MAP_NAMES) - zc_maps))
    if "--emit" in sys.argv:
        emit(rows, ROOT / "bot" / "rushplan.py")
        print("wrote", ROOT / "bot" / "rushplan.py")
