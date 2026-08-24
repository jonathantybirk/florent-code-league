"""Atlas-guided Tempest with reinforcements and proactive/fallback ferries."""

import vigil_builder as builder
import vigil_core as core
import vigil_gunner as gunner
import vigil_launcher as launcher
import vigil_sentinel as sentinel
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
