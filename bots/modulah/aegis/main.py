"""aegis -- economy and home defence built on bots/modulah/lib.

Where beacon proved the information layer works, aegis is the first build that
tries to win with it. Three things beacon lacked, in the order they mattered
when beacon lost 0/12 to the current generation:

  * turrets at all, sited by traffic on the approach rather than by proximity;
  * ammo -- turrets fire from a shared pool the Core alone can fill, so a
    Gunner with no ammo is decoration;
  * roles, so mending starts on the first hit instead of at an hp threshold.

main.py only dispatches. Every shared calculation lives in lib/ and is
vendored, never re-implemented per bot.
"""

from __future__ import annotations

from fcode import Controller, EntityType

import builder_brain
import core_brain
import launcher_brain
import turret_brain


class Player:
    def __init__(self):
        self._core = core_brain.CoreBrain()
        self._builder = builder_brain.BuilderBrain()

    def run(self, ct: Controller) -> None:
        # An uncaught exception permanently kills the unit -- it keeps its
        # +% of cost scale and does nothing for the rest of the game. The
        # steward lineage found three such crashes by replaying with
        # tracebacks on, none of which a win rate had made visible.
        try:
            kind = ct.get_entity_type()
            if kind == EntityType.CORE:
                self._core.run(ct)
            elif kind == EntityType.BUILDER_BOT:
                self._builder.run(ct)
            elif kind in (EntityType.GUNNER, EntityType.SENTINEL):
                turret_brain.run(ct)
            elif kind == EntityType.LAUNCHER:
                launcher_brain.run(ct)
        except Exception:
            pass
