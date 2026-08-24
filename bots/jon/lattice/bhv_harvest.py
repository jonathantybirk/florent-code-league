"""Harvest: put a Harvester on ore.

A Harvester is 20 Ti (+5% scale) and returns 10 Ti every four rounds, so it pays
for itself in eight rounds of production and then prints titanium for the rest of
the match. In a 1000-round game there is almost no ore that is not worth taking.

The two things that stop us are both about *delivery* rather than cost:

* A trunk carries one stack per round and a Harvester emits one per four, so four
  delivering Harvesters saturate a trunk. Past that the fifth mines into a jam.
  So this behaviour refuses to build when the pipe is already full and the route
  module has not opened a new one.
* Ore whose every cardinal neighbour is also ore or wall is skipped: a Harvester
  there has nowhere to put a conveyor, so it can never deliver, so it scores
  nothing on the tiebreak that decides most games.
"""
from __future__ import annotations

from fcode import EntityType, GameError, Position

import config
import econ
import geom
import nav

NAME = "harvest"


def score(ctx) -> float:
    ct, wm = ctx.ct, ctx.wm
    if wm.me is None or wm.my_core is None:
        return 0.0
    try:
        cost = ct.get_harvester_cost()
    except GameError:
        return 0.0
    if ctx.titanium() < cost:
        return 0.0

    # Do not out-run the pipe. Orphans are the route module's problem; if there
    # are already several waiting, another Harvester makes the jam worse.
    orphans = econ.orphan_harvesters(ct, wm)
    if len(orphans) >= 2:
        return 0.0
    if econ.trunk_load(ct, wm) >= config.HARVESTERS_PER_TRUNK * _trunks(wm):
        return 0.0

    cands = econ.ore_candidates(ct, wm)
    if not cands:
        return 0.0
    ctx.scratch["harvest_targets"] = cands[:12]

    # Nearer ore scores higher, so a Builder standing next to ore takes it rather
    # than walking past to a marginally better tile.
    best = cands[0]
    d = abs(best[0] - wm.me.x) + abs(best[1] - wm.me.y)
    return min(config.CEILINGS[NAME] - 0.01, 4.0 - min(d, 30) * 0.08)


def _trunks(wm) -> int:
    """How many independent belts we are running. One until proven otherwise."""
    n = 0
    for s in wm.my_buildings(EntityType.CONVEYOR):
        if wm.my_core is not None and geom.dist_sq(s.pos, wm.my_core) <= 8:
            n += 1
    return max(1, n)


def run(ctx) -> bool:
    ct, wm = ctx.ct, ctx.wm
    targets = ctx.scratch.get("harvest_targets") or []
    if not targets or wm.me is None:
        return False

    # Build it if we are already standing beside one.
    if ctx.can_act():
        for nb in geom.orth_neighbours(wm.me, wm.w, wm.h):
            key = (nb.x, nb.y)
            if key not in wm.ore or wm.buildings.get(key) is not None:
                continue
            try:
                if ct.can_build_harvester(nb):
                    ct.build_harvester(nb)
                    return True
            except GameError:
                continue

    # Otherwise walk to the tile *next to* the ore, not onto it: a Harvester is
    # built on an orthogonally adjacent tile and a Builder cannot act on its own.
    if ctx.can_move():
        approach = set()
        for key in targets:
            p = Position(key[0], key[1])
            for nb in geom.orth_neighbours(p, wm.w, wm.h):
                nk = (nb.x, nb.y)
                if nk in wm.walls or nk in wm.ore:
                    continue
                if wm.buildings.get(nk) is not None:
                    continue
                approach.add(nk)
        if approach:
            return nav.step_toward(ct, wm, approach)
    return False
