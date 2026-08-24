"""The Core: spawn policy and ammunition.

The Core is the only unit that can convert titanium into ammunition and the only
one that can make Builders, so both of the game's two flat-priced, scale-immune
levers are pulled from here.

**Ammunition.** `convert_ammo` is 1:1, costs no action cooldown, is usable the
same turn, and is not taxed by cost scale. A team that cannot shoot loses faster
than one that cannot build, so a floor is held -- but only after the opening,
because before then the same titanium is the difference between two Harvesters
and none, and an empty board has nothing to shoot at anyway.

**Headcount.** A Builder is +20% cost scale for as long as it lives, and the
scale multiplies every Harvester and conveyor we have not bought yet. That makes
opening headcount expensive and late headcount cheap: at round 250 the same +20%
falls almost entirely on 3 Ti conveyors, while every Harvester the extra Builder
connects returns 2.5 Ti/round for the rest of the match.
"""
from __future__ import annotations

from fcode import Direction, EntityType, GameError, Position

import comms
import config
import geom


class CoreBrain:
    def __init__(self):
        self.spawned = 0
        self.memory = {}

    def run(self, ct, wm) -> None:
        pos = None
        try:
            pos = ct.get_position()
        except GameError:
            return
        wm.my_core = pos
        comms.put_pos(ct, comms.CORE_X, comms.CORE_Y, pos)
        if wm.enemy_core is not None:
            comms.put_pos(ct, comms.ENEMY_CORE_X, comms.ENEMY_CORE_Y, wm.enemy_core)

        self._ammo(ct, wm)
        self._spawn(ct, wm)

    # -- ammunition ---------------------------------------------------------
    def _ammo(self, ct, wm) -> None:
        try:
            ammo = ct.get_global_ammo()
            bank = ct.get_global_resources()
        except GameError:
            return
        if wm.round < config.AMMO_RESERVE_ROUND:
            return
        if ammo >= config.AMMO_FLOOR:
            return
        want = config.AMMO_TOPUP - ammo
        # Never convert the construction reserve away: the belt is the win
        # condition and a stalled belt cannot be healed back into existence.
        spare = bank - 60
        amount = min(want, spare)
        if amount <= 0:
            return
        try:
            if ct.can_convert_ammo(amount):
                ct.convert_ammo(amount)
        except GameError:
            pass

    # -- headcount ----------------------------------------------------------
    def _spawn(self, ct, wm) -> None:
        try:
            if ct.get_action_cooldown() != 0:
                return
            cost = ct.get_builder_bot_cost()
            bank = ct.get_global_resources()
            units = ct.get_unit_count()
        except GameError:
            return
        if bank < cost or units >= 48:
            return

        want = config.OPENING_BUILDERS
        if wm.round >= config.INCOME_BUILDER_ROUND and bank >= config.INCOME_BUILDER_BANK:
            want += min(config.INCOME_BUILDER_MAX,
                        (wm.round - config.INCOME_BUILDER_ROUND) // 150 + 1)

        alive = self._count_builders(ct, wm)
        if alive >= want:
            return
        if not config.REPLACE_LOST_BUILDERS and self.spawned >= want:
            return

        target = self._spawn_tile(ct, wm)
        if target is None:
            return
        try:
            if ct.can_spawn(target):
                ct.spawn_builder(target)
                self.spawned += 1
        except GameError:
            pass

    def _count_builders(self, ct, wm) -> int:
        n = 0
        try:
            for eid in ct.get_nearby_entities():
                if (ct.get_entity_type(eid) == EntityType.BUILDER_BOT
                        and ct.get_team(eid) == wm.team):
                    n += 1
        except GameError:
            pass
        # Builders out of the Core's r^2=36 vision are invisible to this count, so
        # it under-reports. `get_unit_count` gives the true total; subtract the
        # Core and everything we know is a turret to recover the headcount.
        try:
            total = ct.get_unit_count() - 1
        except GameError:
            return n
        turrets = 0
        for s in wm.my_buildings():
            if s.etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.LAUNCHER):
                turrets += 1
        return max(n, total - turrets)

    def _spawn_tile(self, ct, wm):
        """Prefer the ring tile facing wherever this Builder should be going.

        The first few go outward on spread axes so the opening explores in
        different directions; later ones are pushed toward the centre, which is
        the contested ground and where the ore usually runs out first.
        """
        if wm.my_core is None:
            return None
        cx, cy = wm.my_core.x, wm.my_core.y
        ring = []
        for dx in range(-1, 3):
            for dy in range(-1, 3):
                if 0 <= dx <= 1 and 0 <= dy <= 1:
                    continue                      # the footprint itself
                p = Position(cx + dx, cy + dy)
                if 0 <= p.x < wm.w and 0 <= p.y < wm.h:
                    ring.append(p)
        if not ring:
            return None

        aim = wm.enemy_core if wm.enemy_core is not None else Position(wm.w // 2, wm.h // 2)
        if self.spawned < config.OPENING_BUILDERS:
            # Spread: rotate the preferred quadrant per spawn.
            quad = self.spawned % 4
            ring.sort(key=lambda p: ((p.x - cx) * (1 if quad in (0, 3) else -1)
                                     + (p.y - cy) * (1 if quad in (0, 1) else -1)),
                      reverse=True)
        else:
            ring.sort(key=lambda p: geom.dist_sq(p, aim))

        for p in ring:
            try:
                if ct.can_spawn(p):
                    return p
            except GameError:
                continue
        return None
