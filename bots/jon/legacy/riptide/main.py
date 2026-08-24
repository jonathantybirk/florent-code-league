"""Riptide: a counter built on a mechanic nobody here uses.

`ct.launch()` does not check ownership. A Launcher can pick up an *enemy*
Builder standing beside it and hurl it five tiles, for no ammunition and no
cooldown beyond one round. Every bot in this repository attacks with Builders
walking into the enemy base, so a Launcher parked on the approach simply
deletes the assault: each arrival is thrown back across the map and has to walk
the whole way again, while our own Gunners shoot it on the way in.
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
