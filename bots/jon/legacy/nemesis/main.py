"""Nemesis: a bot built to beat Vanguard, and only Vanguard.

Vanguard's siege needs one thing -- a free tile beside a producer with a firing
line to our Core. Everything here exists to make that tile not exist:

  * mine the deposits near our own Core first, so it cannot plant a forward
    Harvester on them;
  * brick every remaining tile that would give a Gunner a line to the Core,
    not just the twelve on the Core ring;
  * repair at 4 HP a round against its Builders' 2 damage a round, so nothing
    it chips ever actually falls;
  * post fed Gunners over the approach, because its attackers are 40 HP
    Builders with no ranged attack at all and it builds no defensive turrets.

Then win the round-1000 tiebreak on titanium delivered.
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
