"""Heimdall: warden_walk, atlas-free, with a home guard.

The Builder standing at our own Core answers an enemy that walks up to it on
*sighting* rather than waiting for the Core to lose 50 HP and raise the damage
alarm. Their whole attack is one Builder, their Core will not replace it while
any of their Builders lives, and a Gunner kills a 40 HP Builder in four rounds
-- so the cheapest game to win is the one where their attacker never emplaces.
Measured at 145/168 against valkyrie, vigil, ragnarok and vanguard where the
same chassis without it takes 118. See README.md.

No map oracle: there is no atlas module and no import of one, so this plays a
generated map, the held-out set and the final the way it plays the pool.

Inherited below: vigil's turret meta and economy planner, Prospect's corner
doctrine, Casemate's walled piercing-Sentinel siege as the no-lane fallback,
GobbleGlitch's mender defence and cost-scale hygiene, and the capped Launcher
relay that warden_walk measured.
"""

import heimdall_builder as builder
import heimdall_core as core
import heimdall_gunner as gunner
import heimdall_launcher as launcher
import heimdall_sentinel as sentinel
from fcode import Controller, EntityType


HANDLERS = {
    EntityType.CORE: core.run,
    EntityType.BUILDER_BOT: builder.run,
    EntityType.GUNNER: gunner.run,
    EntityType.LAUNCHER: launcher.run,
    EntityType.SENTINEL: sentinel.run,
}


class Player:
    """The game creates one Player instance for each controlled entity."""

    def run(self, ct: Controller) -> None:
        """Send this entity to its matching handler."""
        handler = HANDLERS.get(ct.get_entity_type())
        if handler is not None:
            handler(self, ct)
