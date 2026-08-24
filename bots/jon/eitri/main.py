"""eitri -- the opening buildout, and for now nothing else.

The bot exists to answer one question well: given a published map and a Core,
how few rounds does it take to have every worthwhile deposit harvested and
draining home?  Combat, defence and harassment are deliberately absent.

An uncaught exception removes a unit from the match permanently -- unlike a
CPU overrun, which only costs it a round -- so every turn is wrapped.
"""

from fcode import Controller, EntityType

import builder
import core
import debug

_HANDLERS = {EntityType.CORE: core.run, EntityType.BUILDER_BOT: builder.run}


class Player:
    def __init__(self) -> None:
        self.spawned = 0
        self.crew = builder.Crewman()

    def run(self, ct: Controller) -> None:
        handler = _HANDLERS.get(ct.get_entity_type())
        if handler is None:
            return
        try:
            handler(self, ct)
        except Exception:
            if debug.ON:
                import traceback
                debug.log(f"r{ct.get_current_round()} id{ct.get_id()} "
                          + traceback.format_exc())
            return
