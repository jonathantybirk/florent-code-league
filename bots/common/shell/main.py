"""Empty bot skeleton. Copy this directory to start a new bot."""

from fcode import Controller, EntityType, GameError


class Player:
    """One instance per unit, persisting across rounds."""

    def __init__(self):
        pass

    def run(self, ct: Controller) -> None:
        # An uncaught GameError destroys the unit, so never let one escape.
        try:
            etype = ct.get_entity_type()
            if etype == EntityType.CORE:
                self.run_core(ct)
            elif etype == EntityType.BUILDER_BOT:
                self.run_builder(ct)
            else:
                self.run_turret(ct)
        except GameError:
            pass

    def run_core(self, ct: Controller) -> None:
        pass

    def run_builder(self, ct: Controller) -> None:
        pass

    def run_turret(self, ct: Controller) -> None:
        pass
