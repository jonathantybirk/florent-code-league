"""Guard: answer an enemy that has walked up to our Core.

The trigger is *sighting*, not damage. Waiting for the Core to lose HP hands the
attacker the several rounds it needs to emplace a turret, after which answering
costs a turret duel instead of a few shots at a Builder.

What makes this cheap is the shape of the attack: it is usually carried by one
Builder, and their Core will not spawn a replacement while any of their Builders
still lives. A Builder killed on our doorstep is an attack that does not come
back.

The answer is a Sentinel rather than a Gunner. Under 2.3.4 both cost the same
+20% of permanent cost scale, and the Sentinel needs 3 shots to kill a 40 HP
Builder against the Gunner's 6, reaches r^2=32 against 13, and cannot be screened
by a barrier dropped in its lane.
"""
from __future__ import annotations

from fcode import EntityType, GameError

import config
import geom
import nav

NAME = "guard"


def _threats(ctx):
    """Anything hostile close enough to our Core to be worth answering.

    Both halves matter and they are urgent for different reasons. A Builder near
    home is about to *become* a turret, and killing it now is far cheaper than
    duelling what it builds -- their Core will not replace it while any of their
    Builders lives. An emplaced turret is already spending our Core's HP, and at
    6 damage a round against a mender's 4 it wins that race on its own.
    """
    wm = ctx.wm
    if wm.my_core is None:
        return []
    out = []
    for eid, pos, etype in wm.enemy_units:
        d = geom.dist_sq(pos, wm.my_core)
        if etype == EntityType.BUILDER_BOT:
            if d <= config.GUARD_RADIUS_SQ:
                out.append((d, pos))
        elif etype in (EntityType.SENTINEL, EntityType.GUNNER):
            # A Sentinel reaches r^2=32, so one seated anywhere near the Core is
            # already a live threat even if it has not fired yet.
            if d <= config.GUARD_TURRET_RADIUS_SQ:
                out.append((d - 100, pos))     # sorts ahead of any Builder
    out.sort(key=lambda t: t[0])
    return out


def _my_home_turrets(ctx) -> int:
    wm = ctx.wm
    if wm.my_core is None:
        return 0
    n = 0
    for s in wm.my_buildings():
        if s.etype in (EntityType.SENTINEL, EntityType.GUNNER):
            if geom.dist_sq(s.pos, wm.my_core) <= config.GUARD_RADIUS_SQ * 2:
                n += 1
    return n


def score(ctx) -> float:
    hits = _threats(ctx)
    if not hits:
        return 0.0
    ctx.scratch["guard_target"] = hits[0][1]
    ctx.scratch["guard_turrets"] = _my_home_turrets(ctx)
    # Closer is more urgent; anything here outranks every economic behaviour.
    d = hits[0][0]
    return min(config.CEILINGS[NAME] - 0.01, 6.0 + 3.0 / (1.0 + d))


def run(ctx) -> bool:
    ct, wm = ctx.ct, ctx.wm
    target = ctx.scratch.get("guard_target")
    if target is None or wm.me is None:
        return False

    # 1. Emplace a Sentinel covering the approach, if we can afford the seat and
    #    have not already saturated the home battery.
    if (ctx.can_act()
            and ctx.scratch.get("guard_turrets", 0) < config.MAX_GUARD_TURRETS):
        if _build_turret_at(ctx, target):
            return True

    # 2. Failing that, hit it directly. Two damage for two titanium is a poor
    #    exchange on its own, but it is free of cost scale and it denies the tile.
    if ctx.can_act():
        for nb in geom.orth_neighbours(wm.me, wm.w, wm.h):
            if nb.x == target.x and nb.y == target.y:
                try:
                    if ct.can_fire(nb):
                        ct.fire(nb)
                        return True
                except GameError:
                    pass

    # 3. Otherwise close the distance so that next round one of the above works.
    if ctx.can_move():
        return nav.step_toward(ct, wm, [(target.x, target.y)], avoid_threat=False)
    return False


def _build_turret_at(ctx, target) -> bool:
    """Seat a Sentinel on an orthogonally adjacent tile that bears on `target`."""
    ct, wm = ctx.ct, ctx.wm
    cost = _turret_cost(ct)
    if cost is None or ctx.titanium() < cost:
        return False
    kind = EntityType.SENTINEL if config.PREFER_SENTINEL else EntityType.GUNNER
    for nb in geom.orth_neighbours(wm.me, wm.w, wm.h):
        if (nb.x, nb.y) in wm.walls or wm.buildings.get((nb.x, nb.y)) is not None:
            continue
        facing = geom.facing_from_to(nb, target)
        try:
            if not ct.can_fire_from(nb, facing, kind, target):
                continue
            if ct.can_build(kind, nb, facing):
                ct.build(kind, nb, facing)
                return True
        except GameError:
            continue
    return False


def _turret_cost(ct):
    try:
        return (ct.get_sentinel_cost() if config.PREFER_SENTINEL
                else ct.get_gunner_cost())
    except GameError:
        return None
