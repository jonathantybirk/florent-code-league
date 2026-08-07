"""beacon -- the reference consumer of bots/modulah/lib.

Not a frontier bot. It exists to prove the utility layer works against the
real engine and to show the intended shape: main.py only dispatches, each unit
type gets one brain module, and every shared calculation comes from lib/.

The economy here is deliberately plain -- one Harvester, one chain, mend when
the Core is in trouble. The point being demonstrated is the information layer:
the Core publishes an arrival schedule, a damage picture and a turret map, and
the Builders act on intel they could not have gathered themselves.
"""

from __future__ import annotations

from fcode import Controller, EntityType

import builder_brain
import core_brain


class Player:
    def __init__(self):
        self._core = core_brain.CoreBrain()
        self._builder = builder_brain.BuilderBrain()

    def run(self, ct: Controller) -> None:
        # An uncaught exception permanently kills the unit, which loses the
        # match far more reliably than any bad decision inside the brain.
        try:
            kind = ct.get_entity_type()
            if kind == EntityType.CORE:
                self._core.run(ct)
            elif kind == EntityType.BUILDER_BOT:
                self._builder.run(ct)
        except Exception:
            pass
