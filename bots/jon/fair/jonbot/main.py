"""A modular bot skeleton ready for your own strategy."""

import builder
import core
import gunner
import sentinel
from fcode import Controller, EntityType


HANDLERS = {
    EntityType.CORE: core.run,
    EntityType.BUILDER_BOT: builder.run,
    EntityType.GUNNER: gunner.run,
    EntityType.SENTINEL: sentinel.run,
}


class Player:
    """The game creates one Player instance for each controlled entity."""

    def run(self, ct: Controller) -> None:
        """Send this entity to its matching handler."""
        handler = HANDLERS.get(ct.get_entity_type())
        if handler is not None:
            handler(self, ct)
