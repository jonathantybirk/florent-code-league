"""pantheon_clone: Pantheon's (#1, 1980) opening reconstructed from 150 replays.

Builder r0; Builder + Launcher r1; Builders r2-r3; four throws on r2-r5 (two
raiders at the enemy Core, two economy Builders at far ore); Launcher razes
itself on r6 to hand back its +10% build-cost scale.

See README.md for what is measured, what is inferred, and what the replays
cannot tell us.
"""

import builder
import core
import gunner
import launcher
from fcode import Controller, EntityType

HANDLERS = {
    EntityType.CORE: core.run,
    EntityType.BUILDER_BOT: builder.run,
    EntityType.GUNNER: gunner.run,
    EntityType.LAUNCHER: launcher.run,
}


class Player:
    """The engine creates one Player per controlled entity."""

    def __init__(self):
        # Core
        self.spawned = 0
        # Launcher
        self.throws = 0
        # Builder
        self.index: int | None = None
        self.built_launcher = False
        self.pad_attempts = 0
        self.airborne = False
        self.gunners = 0
        self.harvester: tuple[int, int] | None = None
        self.conveyors = 0
        self.target: tuple[int, int] | None = None
        self.last: tuple[int, int] | None = None
        self.stuck = 0

    def run(self, ct: Controller) -> None:
        handler = HANDLERS.get(ct.get_entity_type())
        if handler is None:
            return
        try:
            handler(self, ct)
        except Exception:
            # An uncaught exception permanently destroys the unit for the rest
            # of the match, which is far worse than losing a single turn.
            pass
