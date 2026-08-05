"""Warden -- Builder Bots ticket-assigned to Economy/Scouting on spawn,
switching mode only via the reactive triggers in policy.maybe_reassign()
(Defence and Offence are both 100% reactive -- neither is ever a ticket
default; see constants.QUOTA_CYCLE). See policy.py/modes/*.py for the
assignment mechanism and per-mode behavior; this file is just
entity-type dispatch and the exception-safety boundary.
"""

from __future__ import annotations

from fcode import Controller, EntityType

import core
import policy
from modes import MODE_HANDLERS, economy
from state import BuilderState
from toolbox import auto_fire, locate_own_core


class Player:
    def __init__(self) -> None:
        self.state = BuilderState()

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        try:
            if etype == EntityType.CORE:
                core.run(ct, self.state)
            elif etype == EntityType.GUNNER:
                auto_fire(ct)
            elif etype == EntityType.BUILDER_BOT:
                self._run_builder(ct)
        except Exception:
            pass  # an uncaught exception here permanently kills the unit

    def _run_builder(self, ct: Controller) -> None:
        policy.acquire_ticket(ct, self.state)
        if self.state.core_pos is None:
            self.state.core_pos = locate_own_core(ct)
        policy.maybe_reassign(ct, self.state)

        handler = MODE_HANDLERS[self.state.mode]
        try:
            handler(ct, self.state)
        except Exception:
            # ECONOMY is the best-tested baseline -- same role
            # strategist's fallback_idx=0 plays -- so a broken mode
            # handler falls back to it instead of stranding the unit
            # for the round.
            try:
                economy.run(ct, self.state)
            except Exception:
                pass
