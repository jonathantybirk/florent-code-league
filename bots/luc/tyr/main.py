"""Valkyrie: ragnarok with the throw pad spawned first.

The pad Builder spawns before the attacker instead of after it, and the
opening ferry is gated on knowing where the enemy Core is rather than on
having looked it up, so the relay still runs on a map outside the pool.
Everything below is inherited unchanged.

Vigil's turret meta and economy planner, Prospect's corner doctrine,
Casemate's walled piercing-Sentinel siege as the no-lane fallback,
GobbleGlitch's mender defence and cost-scale hygiene, and the
farthest-first symmetry guess measured on the published pool.
"""

import builder
import core
import gunner
import launcher
import sentinel
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
