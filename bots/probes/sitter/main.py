"""Opponent for the G49 launcher test: spawn exactly one Builder Bot and never move it.

On arena `close` Core B's anchor is (8,5), so (7,5) is on its spawn ring and sits orthogonally
adjacent to the Launcher the `launcher2` probe builds at (6,5).
"""

from fcode import Controller, EntityType, GameError, Position


class Player:
    def __init__(self):
        self.spawned = False

    def run(self, ct: Controller) -> None:
        try:
            if ct.get_entity_type() != EntityType.CORE or self.spawned:
                return
            p = Position(7, 5)
            if ct.can_spawn(p):
                ct.spawn_builder(p)
                self.spawned = True
        except Exception:
            pass
