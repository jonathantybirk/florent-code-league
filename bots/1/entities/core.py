"""Core entity logic: spawn a single builder bot toward the northeast."""

from __future__ import annotations

from fcode import Controller, Direction

# Tried in order until one is a legal spawn tile
_SPAWN_DIRECTIONS = (Direction.NORTHEAST, Direction.NORTH, Direction.EAST)


class CoreMixin:
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.spawned = False

    def run_core(self, ct: Controller) -> None:
        if self.spawned:
            return

        pos = ct.get_position()
        for d in _SPAWN_DIRECTIONS:
            spawn_pos = pos.add(d)
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                self.spawned = True
                return
