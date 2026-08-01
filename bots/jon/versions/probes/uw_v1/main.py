"""Undertow: absorb committed pressure, then reverse the logistics race."""

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
    EntityType.SENTINEL: sentinel.run,
    EntityType.LAUNCHER: launcher.run,
}


class Player:
    """The game creates one Player instance for each controlled entity."""

    def run(self, ct: Controller) -> None:
        """Send this entity to its matching handler.

        Any exception that escapes run() permanently destroys the unit, so
        this is the last line of defence behind each handler's own guard.
        """
        try:
            handler = HANDLERS.get(ct.get_entity_type())
            if handler is not None:
                handler(self, ct)
        except Exception:  # noqa: BLE001
            pass
