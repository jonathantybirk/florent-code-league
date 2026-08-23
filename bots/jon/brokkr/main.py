"""brokkr -- an economy bot wired out of the shared bots/utils modules.

The engine builds one Player per unit and calls run() once a round, so each
unit's Brain accumulates its own memory of the map for the whole match.

Every turn is wrapped. An uncaught exception does not cost a round like a CPU
overrun does -- it removes the unit from the match permanently -- so the
outermost frame of every unit swallows everything and takes the lost turn
instead.
"""

from fcode import Controller, EntityType

import builder
import core
import debug
import turret
from brain import Brain

HANDLERS = {
    EntityType.CORE: core.run,
    EntityType.BUILDER_BOT: builder.run,
    EntityType.GUNNER: turret.run,
    EntityType.SENTINEL: turret.run,
    EntityType.LAUNCHER: turret.run,
}


class Player:
    def __init__(self) -> None:
        self.brain = Brain()
        self.spawned = 0
        self.last_hp = None
        self.last_damage = None

    def run(self, ct: Controller) -> None:
        handler = HANDLERS.get(ct.get_entity_type())
        if handler is None:
            return
        try:
            handler(self, ct)
        except Exception:
            if debug.ON:
                import traceback
                debug.log("EXC " + traceback.format_exc())
            return
