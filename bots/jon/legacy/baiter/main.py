"""Baiter: a counter to Vanguard's scorched-earth rule.

Vanguard destroys its own Harvester whenever an enemy Gunner stands beside it,
to stop the Gunner being fed. The trigger is "a Gunner is adjacent" -- not "a
Gunner that can actually hurt us". So a Gunner planted next to their Harvester
with no line to anything still makes them burn a 20 Ti building and its whole
income, for our 10 Ti. And ours is fed by that same Harvester in the meantime.

This bot places Gunners beside enemy producers whether or not they have a shot.
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
