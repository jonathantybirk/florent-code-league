"""Route: connect a Harvester to the Core.

This outranks `harvest` on purpose. The round-1000 tiebreak counts titanium
*collected* -- stacks that physically landed on a Core tile -- so an unconnected
Harvester scores exactly zero no matter how long it has been mining. Finishing
the belt we already started is always worth more than starting another hole.

Conveyors are 3 Ti and +1% scale each, which is the cheapest thing in the game by
a wide margin, so the limit on belt-laying is Builder-rounds rather than money.
That is why the route is planned once, cached, and then walked: re-planning every
turn would spend the rounds that are supposed to be laying tile.
"""
from __future__ import annotations

from fcode import EntityType, GameError

import config
import econ
import geom
import nav

NAME = "route"


def score(ctx) -> float:
    ct, wm = ctx.ct, ctx.wm
    if wm.me is None or wm.my_core is None:
        return 0.0
    try:
        cost = ct.get_conveyor_cost()
    except GameError:
        return 0.0
    if ctx.titanium() < cost:
        return 0.0
    if wm.round > config.ECON_SOFT_CAP_ROUND:
        return 0.0

    plan = _plan(ctx)
    if plan is None:
        return 0.0
    missing, path = plan
    if not missing:
        return 0.0
    ctx.scratch["route_plan"] = (missing, path)
    # A nearly-finished belt is the most valuable thing on the board; a fresh
    # 15-tile run competes with putting a Harvester down first.
    return min(config.CEILINGS[NAME] - 0.01, 5.5 - 0.1 * min(len(missing), 20))


def _plan(ctx):
    """Cached route to the nearest orphan Harvester.

    The cache is invalidated when the target stops being an orphan or when the
    next tile we meant to build on has been taken, which is the only way the plan
    can go stale that matters.
    """
    ct, wm = ctx.ct, ctx.wm
    mem = ctx.memory
    cached = mem.get("route")
    if cached is not None:
        src_key, missing, path = cached
        s = wm.buildings.get(src_key)
        if (s is not None and s.team == wm.team
                and s.etype == EntityType.HARVESTER
                and not econ.delivers_to_core(ct, wm, s.pos)):
            missing = [p for p in missing if wm.buildings.get((p.x, p.y)) is None]
            if missing:
                mem["route"] = (src_key, missing, path)
                return missing, path
        mem.pop("route", None)

    orphans = econ.orphan_harvesters(ct, wm)
    if not orphans:
        return None
    orphans.sort(key=lambda s: geom.manhattan(s.pos, wm.me))
    for s in orphans[:3]:
        missing, path = econ.plan_route(ct, wm, s.pos)
        if missing:
            mem["route"] = ((s.pos.x, s.pos.y), missing, path)
            return missing, path
    return None


def run(ctx) -> bool:
    ct, wm = ctx.ct, ctx.wm
    plan = ctx.scratch.get("route_plan")
    if plan is None or wm.me is None:
        return False
    missing, path = plan

    # Build the first missing tile we happen to be standing beside, so that a
    # Builder walking the line lays tile continuously instead of only at the end.
    if ctx.can_act():
        for nb in geom.orth_neighbours(wm.me, wm.w, wm.h):
            key = (nb.x, nb.y)
            if wm.buildings.get(key) is not None or key in wm.walls:
                continue
            idx = _index_of(path, key)
            if idx is None:
                continue
            facing = econ.facing_along(path, idx)
            try:
                if ct.can_build_conveyor(nb, facing):
                    ct.build_conveyor(nb, facing)
                    ctx.memory.pop("route", None)   # re-plan next turn, cheaply
                    return True
            except GameError:
                continue

    if ctx.can_move():
        approach = set()
        for p in missing[:4]:
            for nb in geom.orth_neighbours(p, wm.w, wm.h):
                nk = (nb.x, nb.y)
                if nk in wm.walls or wm.buildings.get(nk) is not None:
                    continue
                approach.add(nk)
        if approach:
            return nav.step_toward(ct, wm, approach)
    return False


def _index_of(path, key):
    for i, p in enumerate(path):
        if (p.x, p.y) == key:
            return i
    return None
