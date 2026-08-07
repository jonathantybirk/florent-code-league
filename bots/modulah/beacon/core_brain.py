"""The Core: publish what only the Core can see, then spawn.

Everything published here is information no other unit could obtain:

  * the arrival schedule, because only the Core sits at the end of the supply
    network and can walk it backwards;
  * the damage picture, because only the Core knows its own hp history;
  * the turret map, because CORE_VISION_RADIUS_SQ (36) exceeds the longest
    reach anything has against it (Sentinel, dist_sq 32), while a Builder sees
    radius ~4.5 and is blind to what is shooting at it.

The Core keeps its trend history in memory rather than in the store. Its
Player instance persists across rounds, so local state is free; store slots
are not.
"""

from __future__ import annotations

from fcode import Controller, GameConstants, GameError

import comms
import econ
import threat
from geometry import core_footprint


class CoreBrain:
    def __init__(self):
        self.monitor = threat.CoreMonitor()
        self._footprint = None

    def run(self, ct: Controller) -> None:
        round_no = ct.get_current_round()
        if self._footprint is None:
            # The footprint cannot move, so this is worth caching -- it costs
            # a get_nearby_tiles sweep and every published field needs it.
            self._footprint = core_footprint(ct)

        self.monitor.observe(ct)
        self._publish(ct, round_no)
        self._spawn(ct)

    # --- publishing ---------------------------------------------------------

    def _publish(self, ct: Controller, round_no: int) -> None:
        schedule = econ.published_schedule(ct, self._footprint)
        ct.write_store(comms.SLOT_CORE_ECON, comms.pack_econ(schedule, round_no))

        burst = threat.max_burst(ct, self._footprint)
        ct.write_store(
            comms.SLOT_CORE_THREAT,
            comms.pack_threat(self.monitor.hp, self.monitor.dhp(), burst, round_no),
        )

        anchor = ct.get_position()
        records = threat.turret_records(ct, self._footprint, anchor, limit=4)
        ct.write_store(
            comms.SLOT_CORE_TURRET0, comms.pack_turrets(records[:2], round_no)
        )
        ct.write_store(
            comms.SLOT_CORE_TURRET1, comms.pack_turrets(records[2:4], round_no)
        )

    # --- spawning -----------------------------------------------------------

    def _spawn(self, ct: Controller) -> None:
        """Keep a working population, capped by what the store can address.

        BUILDER_SLOTS is the real ceiling on broadcasting units -- one writer
        per slot is forced by the engine, since two units sharing a word lose
        each other's writes. Spawning past that is legal but the extra units
        would be mute, so the cap is a deliberate design limit rather than an
        oversight.
        """
        if ct.get_unit_count() >= len(comms.BUILDER_SLOTS):
            return
        if ct.get_global_resources() < GameConstants.BUILDER_BOT_BASE_COST * 2:
            return
        for pos in ct.get_nearby_tiles(dist_sq=GameConstants.CORE_SPAWNING_RADIUS_SQ):
            try:
                if ct.can_spawn(pos):
                    ct.spawn_builder(pos)
                    return
            except GameError:
                continue
