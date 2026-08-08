"""Gunners and Sentinels: shoot the thing most worth shooting.

Turrets are cheap to run and expensive to re-aim -- `rotate` costs 10 Ti and a
round -- so the policy is: fire whenever there is a legal shot, and only turn
when there is nothing to shoot at and something worth turning towards.

Target priority follows the damage the target can do back. A Builder bot is
worth killing before a Conveyor because it rebuilds; a turret aimed at our
Core is worth killing before either.
"""

from __future__ import annotations

from fcode import Controller, EntityType, GameConstants, GameError

from geometry import COMPASS

# Lower sorts first. Builders rebuild everything else, so they outrank the
# buildings they place; turrets outrank Builders because they are already
# doing damage.
PRIORITY = {
    EntityType.SENTINEL: 0,
    EntityType.GUNNER: 1,
    EntityType.BUILDER_BOT: 2,
    EntityType.LAUNCHER: 3,
    EntityType.HARVESTER: 4,
    EntityType.SPLITTER: 5,
    EntityType.CONVEYOR: 6,
    EntityType.BARRIER: 7,
    EntityType.CORE: 8,
}

AMMO_FOR = {
    EntityType.GUNNER: GameConstants.GUNNER_AMMO_COST,
    EntityType.SENTINEL: GameConstants.SENTINEL_AMMO_COST,
}


def _enemies(ct: Controller):
    me = ct.get_team()
    out = []
    for eid in ct.get_nearby_entities():
        try:
            if ct.get_team(eid) == me:
                continue
            out.append((PRIORITY.get(ct.get_entity_type(eid), 9),
                        ct.get_position(eid).distance_squared(ct.get_position()),
                        eid))
        except GameError:
            continue
    out.sort()
    return out


def run(ct: Controller) -> None:
    kind = ct.get_entity_type()
    if ct.get_global_ammo() < AMMO_FOR.get(kind, 0):
        return  # nothing to fire; leave the ammo for a turret that can shoot

    targets = _enemies(ct)
    if not targets:
        return

    for _prio, _d, eid in targets:
        try:
            target = ct.get_position(eid)
            if ct.can_fire(target):
                ct.fire(target)
                return
        except GameError:
            continue

    # Nothing in the current lane. Only Gunners can turn at all -- a
    # Sentinel's facing is fixed at build time -- and turning costs 10 Ti and
    # a round, so it is worth doing only for a target we could actually hit
    # once turned.
    if kind != EntityType.GUNNER:
        return
    try:
        pos = ct.get_position()
    except GameError:
        return

    # Scan every facing rather than trusting direction_to, which returns the
    # nearest 45-degree approximation: for any target not exactly on a ray
    # that is a bearing the turret cannot actually shoot along, so the rotate
    # was being skipped for targets a different facing covers. Highest-value
    # target first, so the turn is spent on the thing most worth killing.
    for _prio, _d, eid in targets:
        try:
            target = ct.get_position(eid)
        except GameError:
            continue
        for facing in COMPASS:
            try:
                if not ct.can_fire_from(pos, facing, kind, target):
                    continue
                if ct.can_rotate(facing):
                    ct.rotate(facing)
                    return
            except GameError:
                continue
