"""Siege: seat a turret that shoots the enemy's supply line.

Target selection is the part that matters, and it runs against the grain of
instinct: **we never shoot their turrets.** Cost scale is a live census of
everything a team owns, refunded in full the moment an entity dies, so killing an
enemy Sentinel hands back its +20% and makes every subsequent thing they build
cheaper. We would be paying 30-40 Ti of ammunition to subsidise their rebuild.

Harvesters and conveyors are the opposite trade. Destroying a Harvester removes
2.5 Ti/round of their income, subtracts one from the `harvesters alive` tiebreak,
and only refunds them 5% of scale.

Seats are validated with the engine's own `can_fire_from`, so the Sentinel's
obstacle-ignoring line is exact rather than approximated, and a seat already
covered by an enemy turret is rejected -- losing the opening exchange costs 30 Ti
and 20% of permanent scale for nothing.
"""
from __future__ import annotations

from fcode import EntityType, GameError, Position

import config
import geom
import nav

NAME = "siege"

# What a shot is worth. Turrets are absent on purpose -- see the module docstring.
TARGET_VALUE = {
    EntityType.HARVESTER: 10.0,
    EntityType.CORE: 8.0,
    EntityType.SPLITTER: 4.0,
    EntityType.CONVEYOR: 3.0,
    EntityType.BUILDER_BOT: 5.0,
    EntityType.BARRIER: 0.5,
}
if not config.TARGET_SUPPLY_NOT_TURRETS:
    TARGET_VALUE[EntityType.SENTINEL] = 6.0
    TARGET_VALUE[EntityType.GUNNER] = 6.0


def _my_siege_count(ctx) -> int:
    wm = ctx.wm
    n = 0
    for s in wm.my_buildings():
        if s.etype not in (EntityType.SENTINEL, EntityType.GUNNER):
            continue
        if wm.my_core is None or geom.dist_sq(s.pos, wm.my_core) > config.GUARD_RADIUS_SQ * 2:
            n += 1
    return n


def _enemy_targets(ctx):
    """Their economy, plus their Core, as (value, Position)."""
    wm = ctx.wm
    out = []
    for s in wm.their_buildings():
        v = TARGET_VALUE.get(s.etype)
        if v is None:
            continue
        out.append((v, s.pos))
    for eid, pos, etype in wm.enemy_units:
        if etype == EntityType.BUILDER_BOT:
            out.append((TARGET_VALUE[EntityType.BUILDER_BOT], pos))
    return out


def score(ctx) -> float:
    ct, wm = ctx.ct, ctx.wm
    if wm.me is None:
        return 0.0
    kind = EntityType.SENTINEL if config.PREFER_SENTINEL else EntityType.GUNNER
    try:
        cost = (ct.get_sentinel_cost() if config.PREFER_SENTINEL
                else ct.get_gunner_cost())
    except GameError:
        return 0.0
    if ctx.titanium() < cost + 40:      # keep ammunition money behind the seat
        return 0.0
    if _my_siege_count(ctx) >= config.MAX_SIEGE_TURRETS:
        return 0.0

    targets = _enemy_targets(ctx)
    if not targets:
        return 0.0

    best = None
    best_v = 0.0
    for nb in geom.orth_neighbours(wm.me, wm.w, wm.h):
        key = (nb.x, nb.y)
        if key in wm.walls or wm.buildings.get(key) is not None:
            continue
        if config.AVOID_COVERED_SEATS and key in wm.threat:
            continue
        total = 0.0
        facing_best = None
        for facing in geom.ALL_EIGHT:      # ALL_EIGHT already excludes CENTRE
            v = 0.0
            for value, tpos in targets:
                try:
                    if ct.can_fire_from(nb, facing, kind, tpos):
                        v += value
                except GameError:
                    continue
            if v > total:
                total = v
                facing_best = facing
        if total > best_v and facing_best is not None:
            best_v = total
            best = (nb, facing_best)

    if best is None or best_v <= 0.0:
        # Nothing bears from here. Walk toward their economy instead.
        ctx.scratch["siege_walk"] = [(p.x, p.y) for _, p in targets[:6]]
        return 2.0 if ctx.can_move() else 0.0

    ctx.scratch["siege_seat"] = best
    ctx.scratch["siege_kind"] = kind
    return min(config.CEILINGS[NAME] - 0.01, 3.0 + min(best_v, 30.0) * 0.12)


def run(ctx) -> bool:
    ct, wm = ctx.ct, ctx.wm
    seat = ctx.scratch.get("siege_seat")
    if seat is not None and ctx.can_act():
        nb, facing = seat
        kind = ctx.scratch.get("siege_kind", EntityType.SENTINEL)
        try:
            if ct.can_build(kind, nb, facing):
                ct.build(kind, nb, facing)
                return True
        except GameError:
            pass

    walk = ctx.scratch.get("siege_walk")
    if walk and ctx.can_move():
        approach = set()
        for key in walk:
            p = Position(key[0], key[1])
            for nb in geom.orth_neighbours(p, wm.w, wm.h):
                nk = (nb.x, nb.y)
                if nk in wm.walls or wm.buildings.get(nk) is not None:
                    continue
                approach.add(nk)
        if approach:
            return nav.step_toward(ct, wm, approach)
    return False
