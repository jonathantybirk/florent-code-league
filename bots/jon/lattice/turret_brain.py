"""Turrets: what to shoot, and when to hold fire.

Two rules carry almost all of the value here.

**Never shoot their turrets.** Cost scale is a live census refunded on death, so
destroying an enemy Sentinel hands back its +20% and makes everything they build
afterwards cheaper. We would be paying 10 ammo a shot to subsidise their economy.
Harvesters and conveyors are the opposite: killing a Harvester removes
2.5 Ti/round of income and one unit from the `harvesters alive` tiebreak while
refunding them only 5%.

**Do not shoot what a Builder can out-heal.** A Builder restores 4 HP for 1 Ti;
a Sentinel deals 18 for 10. Pouring 18 damage a shot into a target that is being
tended by two Builders is a losing exchange forever. So a target whose HP has not
fallen between our shots is abandoned rather than ground at.

Turrets also cannot see much on their own -- a Gunner's vision is r^2=13 -- so
target choice is made from what this turret can actually fire on, which the
engine answers exactly through `can_fire`.
"""
from __future__ import annotations

from fcode import EntityType, GameError

import config

# Mirrors the siege module's table: supply first, turrets never (by default).
VALUE = {
    EntityType.HARVESTER: 10.0,
    EntityType.BUILDER_BOT: 7.0,
    EntityType.CORE: 6.0,
    EntityType.SPLITTER: 4.0,
    EntityType.CONVEYOR: 3.0,
    EntityType.BARRIER: 0.5,
}
if not config.TARGET_SUPPLY_NOT_TURRETS:
    VALUE[EntityType.SENTINEL] = 8.0
    VALUE[EntityType.GUNNER] = 8.0


class TurretBrain:
    def __init__(self):
        self.last_target = None      # (x, y)
        self.last_hp = None
        self.stalled = 0

    def run(self, ct, wm) -> None:
        try:
            if ct.get_action_cooldown() != 0:
                return
            ammo = ct.get_global_ammo()
        except GameError:
            return
        etype = None
        try:
            etype = ct.get_entity_type()
        except GameError:
            return
        if etype == EntityType.LAUNCHER:
            return                    # launchers are handled by their own module
        need = (config.AMMO_FLOOR // 4) if etype == EntityType.GUNNER else 10
        if ammo < need:
            return

        # Which enemy turrets are actually shooting at something of ours. The
        # "never shoot their turrets" rule is an economic argument -- killing one
        # refunds its +20% of cost scale -- and it is correct right up until the
        # turret in question is killing our Core. Survival is not a trade.
        counter = set()
        for key in wm.threat:
            s2 = wm.buildings.get(key)
            if s2 is not None and s2.team == wm.team and s2.etype in (
                    EntityType.CORE, EntityType.SENTINEL, EntityType.GUNNER):
                for k2, s3 in wm.buildings.items():
                    if s3.team != wm.team and s3.etype in (
                            EntityType.SENTINEL, EntityType.GUNNER):
                        counter.add(k2)
                break

        best = None
        best_v = 0.0
        try:
            ids = ct.get_nearby_entities()
        except GameError:
            return
        for eid in ids:
            try:
                if ct.get_team(eid) == wm.team:
                    continue
                pos = ct.get_position(eid)
                t = ct.get_entity_type(eid)
            except GameError:
                continue
            v = VALUE.get(t)
            if (pos.x, pos.y) in counter:
                v = 14.0          # counter-battery beats every economic target
            if v is None:
                continue
            try:
                if not ct.can_fire(pos):
                    continue
            except GameError:
                continue
            try:
                hp = ct.get_hp(eid)
            except GameError:
                hp = 999
            # Prefer something we can finish this shot: a kill is permanent, a
            # scratch is titanium donated to their mender.
            if hp <= 18:
                v += 6.0
            if (pos.x, pos.y) == self.last_target and self.last_hp is not None and hp >= self.last_hp:
                v -= 8.0          # they are out-healing us; stop feeding it
            if v > best_v:
                best_v = v
                best = (pos, hp)

        if best is None or best_v <= 0.0:
            self.stalled += 1
            return
        pos, hp = best
        try:
            ct.fire(pos)
            self.last_target = (pos.x, pos.y)
            self.last_hp = hp
            self.stalled = 0
        except GameError:
            pass
