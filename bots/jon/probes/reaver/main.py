"""Reaver: a counter built on Vanguard's repair radius.

Vanguard repairs only what sits within four tiles of its Core, but it runs
belts of up to twenty-one tiles and plants its siege Harvesters right next to
*our* base. Everything beyond that radius is mended by nobody.

A Builder standing on a Conveyor chips it for 2 Ti a round and a Conveyor has
20 HP, so ten rounds of a single Builder permanently severs a supply line that
will never be healed -- and cutting near the Harvester end strands the whole
belt behind it. Reaver keeps Vanguard's economy and defence and spends its
attackers on that instead of on a siege.
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
