"""Secure: deny the enemy ore we are not going to take ourselves.

A barrier is 3 Ti and +1% scale -- the cheapest permanent object in the game --
and a barrier standing on an ore tile means no Harvester can ever be built there.
Against the round-1000 tiebreak that is worth more than it looks: it removes
2.5 Ti/round from their `titanium collected` and one from their `harvesters
alive`, for a twentieth of what a Harvester costs us.

This is deliberately the lowest-value productive behaviour. Walking a Builder
across the map to place 3 Ti of denial spends Builder-rounds, which are the real
scarce resource, so it only runs when we are cash-rich and nothing closer to home
needs doing.
"""
from __future__ import annotations

from fcode import GameError, Position

import config
import econ
import geom
import nav

NAME = "secure"

RICH_ENOUGH = 200          # only deny once our own economy is funded


def _enemy_side_ore(ctx):
    """Ore that is nearer their Core than ours and still unclaimed."""
    wm = ctx.wm
    if wm.my_core is None or wm.enemy_core is None:
        return []
    out = []
    for key in wm.ore:
        if wm.buildings.get(key) is not None:
            continue
        p = Position(key[0], key[1])
        if geom.manhattan(p, wm.enemy_core) < geom.manhattan(p, wm.my_core):
            out.append(key)
    out.sort(key=lambda k: abs(k[0] - wm.me.x) + abs(k[1] - wm.me.y))
    return out


def score(ctx) -> float:
    ct, wm = ctx.ct, ctx.wm
    if wm.me is None or ctx.titanium() < RICH_ENOUGH:
        return 0.0
    if wm.round > config.ECON_SOFT_CAP_ROUND:
        return 0.0
    cands = _enemy_side_ore(ctx)
    if not cands:
        return 0.0
    ctx.scratch["secure_targets"] = cands[:6]
    d = abs(cands[0][0] - wm.me.x) + abs(cands[0][1] - wm.me.y)
    return min(config.CEILINGS[NAME] - 0.01, 3.0 - 0.05 * min(d, 40))


def run(ctx) -> bool:
    ct, wm = ctx.ct, ctx.wm
    targets = ctx.scratch.get("secure_targets") or []
    if not targets or wm.me is None:
        return False

    if ctx.can_act():
        for nb in geom.orth_neighbours(wm.me, wm.w, wm.h):
            key = (nb.x, nb.y)
            if key not in wm.ore or wm.buildings.get(key) is not None:
                continue
            try:
                if ct.can_build_barrier(nb):
                    ct.build_barrier(nb)
                    return True
            except GameError:
                continue

    if ctx.can_move():
        approach = set()
        for key in targets:
            p = Position(key[0], key[1])
            for nb in geom.orth_neighbours(p, wm.w, wm.h):
                nk = (nb.x, nb.y)
                if nk in wm.walls or wm.buildings.get(nk) is not None:
                    continue
                approach.add(nk)
        if approach:
            return nav.step_toward(ct, wm, approach)
    return False
