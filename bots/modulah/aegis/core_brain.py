"""The Core: publish intel, keep the turrets fed, and pace the population.

Publishing is unchanged from beacon -- the arrival schedule, the damage
picture and the turret map are all things no other unit can see.

Two jobs beacon did not do at all:

**Ammo.** Turrets fire from a shared team pool, not from their own stock. A
Gunner with no ammo is 20 Ti of decoration, and `convert_ammo` is Core-only and
capped at one conversion per team per turn -- so if the Core does not do it,
nobody does. beacon built no turrets so it never noticed; that is the single
largest behavioural gap between the two bots.

**Cost scale.** Every building raises the price of the next one. Spawning
Builders to a hard cap therefore inflates everything the team builds later,
which is why steward's lineage records extra miners measuring negative every
time they were tried. Population here is paced against banked titanium rather
than against a fixed number.
"""

from __future__ import annotations

from fcode import Controller, EntityType, GameConstants, GameError

import comms
import econ
import roles
import threat
from geometry import core_footprint

# Keep roughly this many rounds of firing in the pool. Sized off the sustained
# threat rather than a flat number: a Sentinel costs 10 a shot and fires every
# other round, so a real siege drains a fixed reserve almost immediately.
AMMO_ROUNDS = 6
AMMO_FLOOR = GameConstants.SENTINEL_AMMO_COST * 2

# Titanium held back from spawning so a lost Harvester or conveyor can be
# replaced without waiting. steward moved its equivalent from 110 to 260 for
# +8.1pp; this is deliberately nearer the low end because aegis spends far less
# on siege than steward does.
REPLACEMENT_BANK = 160

# Minimum rounds between Builders.
SPAWN_INTERVAL = 12


class CoreBrain:
    def __init__(self):
        self.monitor = threat.CoreMonitor()
        self._footprint = None
        self._last_spawn = -99

    def run(self, ct: Controller) -> None:
        round_no = ct.get_current_round()
        if self._footprint is None:
            self._footprint = core_footprint(ct)

        self.monitor.observe(ct)
        burst = threat.max_burst(ct, self._footprint)
        self._publish(ct, round_no, burst)
        self._feed_turrets(ct, burst)
        self._spawn(ct, burst)

    def _publish(self, ct: Controller, round_no: int, burst: int) -> None:
        schedule = econ.published_schedule(ct, self._footprint)
        ct.write_store(comms.SLOT_CORE_ECON, comms.pack_econ(schedule, round_no))
        ct.write_store(
            comms.SLOT_CORE_THREAT,
            comms.pack_threat(self.monitor.hp, self.monitor.dhp(), burst, round_no),
        )
        anchor = ct.get_position()
        recs = threat.turret_records(ct, self._footprint, anchor, limit=4)
        ct.write_store(comms.SLOT_CORE_TURRET0, comms.pack_turrets(recs[:2], round_no))
        ct.write_store(comms.SLOT_CORE_TURRET1, comms.pack_turrets(recs[2:4], round_no))

    def _feed_turrets(self, ct: Controller, burst: int) -> None:
        """Top the shared ammo pool up to what our turrets could actually spend."""
        me = ct.get_team()
        appetite = 0
        for bid in ct.get_nearby_buildings():
            try:
                if ct.get_team(bid) != me:
                    continue
                kind = ct.get_entity_type(bid)
            except GameError:
                continue
            if kind == EntityType.GUNNER:
                appetite += GameConstants.GUNNER_AMMO_COST
            elif kind == EntityType.SENTINEL:
                appetite += GameConstants.SENTINEL_AMMO_COST // 2  # fires every other round
        # Keep a floor once anything is shooting at us, even with no turret
        # standing yet: a Gunner built into an empty ammo pool is 20 Ti that
        # cannot fire for the rounds it takes the Core to notice. Traced at
        # ammo=0 for an entire game while the Core died.
        if appetite == 0 and not burst:
            return

        want = max(AMMO_FLOOR, appetite * AMMO_ROUNDS)
        have = ct.get_global_ammo()
        if have >= want:
            return
        # Under fire the ammo matters more than the bank -- a Core that dies
        # with a full treasury still loses.
        spare = ct.get_global_resources() - (0 if burst else REPLACEMENT_BANK)
        amount = min(want - have, max(0, spare))
        if amount <= 0:
            return
        try:
            if ct.can_convert_ammo(amount):
                ct.convert_ammo(amount)
        except GameError:
            pass

    def _spawn(self, ct: Controller, burst: int) -> None:
        """Add a Builder only when the team can afford one without going broke.

        Capped by the store: one writer per slot is forced by the engine, so a
        Builder past BUILDER_SLOTS would be mute -- unable to claim a role or
        report a heal, which is worse than not existing.
        """
        if ct.get_unit_count() >= len(comms.BUILDER_SLOTS):
            return
        cost = GameConstants.BUILDER_BOT_BASE_COST
        try:
            cost = int(cost * (1.0 + ct.get_scale_percent() / 100.0))
        except GameError:
            pass
        # Spawn against banked titanium, and never faster than one every few
        # rounds: five Builders in five rounds drained the opening bank from
        # 434 to 108 and left nobody able to afford the Harvester they had
        # walked to. Every unit also raises the cost scale for everything
        # built afterwards.
        if ct.get_global_resources() < cost + REPLACEMENT_BANK:
            return
        if ct.get_current_round() - self._last_spawn < SPAWN_INTERVAL:
            return
        for pos in ct.get_nearby_tiles(dist_sq=GameConstants.CORE_SPAWNING_RADIUS_SQ):
            try:
                if ct.can_spawn(pos):
                    ct.spawn_builder(pos)
                    self._last_spawn = ct.get_current_round()
                    return
            except GameError:
                continue
