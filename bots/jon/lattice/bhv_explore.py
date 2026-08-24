"""Explore: walk toward territory we have not seen.

The floor of the behaviour table. It exists so that a Builder with nothing to do
still converts its round into map knowledge, which is what feeds every other
module: ore we have not seen cannot be harvested, and symmetry cannot be resolved
from tiles we have not looked at.

Direction is taken from the frontier of our own knowledge rather than from a
fixed heading, and the very first Builders are pushed outward on distinct axes so
three units do not walk the same corridor. The unstick jitter is keyed on the
unit's own id so that a stalled group does not re-randomise in lockstep.
"""
from __future__ import annotations

from fcode import GameError, Position

import config
import geom
import nav

NAME = "explore"


def _frontier(ctx, limit=200):
    """Seen, passable tiles that touch something unseen."""
    wm = ctx.wm
    out = []
    for key in wm.seen:
        if key in wm.walls:
            continue
        x, y = key
        for dx, dy in geom.CARD_DELTAS:
            nk = (x + dx, y + dy)
            if not (0 <= nk[0] < wm.w and 0 <= nk[1] < wm.h):
                continue
            if nk not in wm.seen:
                out.append(key)
                break
        if len(out) >= limit:
            break
    return out


def score(ctx) -> float:
    if ctx.wm.me is None or not ctx.can_move():
        return 0.0
    return config.CEILINGS[NAME] - 0.01


def run(ctx) -> bool:
    ct, wm = ctx.ct, ctx.wm
    mem = ctx.memory

    # The warden does not explore. If it has drifted, it walks back to the Core;
    # if it is already there it holds station rather than wandering off station.
    if ctx.role == "warden" and wm.my_core is not None:
        import econ
        if geom.dist_sq(wm.me, wm.my_core) > 4:
            ring = set()
            for nb in geom.orth_neighbours(wm.my_core, wm.w, wm.h):
                ring.add((nb.x, nb.y))
            for key in list(econ.core_tiles(wm)):
                for dx, dy in geom.CARD_DELTAS:
                    ring.add((key[0] + dx, key[1] + dy))
            ring = {k for k in ring
                    if k not in wm.walls and wm.buildings.get(k) is None}
            if ring and nav.step_toward(ct, wm, ring, avoid_threat=False):
                return True
        return False

    # An assigned opening axis, held until we arrive or time out, keeps the first
    # Builders from bunching.
    seed = mem.get("explore_seed")
    if seed is not None and wm.round - mem.get("explore_seed_round", 0) < 40:
        if nav.step_toward(ct, wm, [seed], avoid_threat=True):
            return True
        mem.pop("explore_seed", None)

    frontier = _frontier(ctx)
    if frontier:
        # Bias away from home so exploration actually expands the known region.
        if wm.my_core is not None:
            frontier.sort(key=lambda k: -((k[0] - wm.my_core.x) ** 2
                                          + (k[1] - wm.my_core.y) ** 2))
        pick = frontier[: max(1, len(frontier) // 4)]
        if nav.step_toward(ct, wm, set(pick), avoid_threat=True):
            return True

    # Stuck: jitter, desynchronised by id so a jammed group does not move as one.
    try:
        uid = ct.get_id()
    except GameError:
        uid = 0
    order = geom.CARDINALS[uid % 4:] + geom.CARDINALS[: uid % 4]
    for d in order:
        if nav.try_move(ct, d):
            return True
    return False
