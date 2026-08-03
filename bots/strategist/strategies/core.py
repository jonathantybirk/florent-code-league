"""Core strategies."""

from __future__ import annotations

import random

from fcode import Controller

from state import BotState
from utils import DIRECTIONS, SLOT_CORE_X, SLOT_CORE_Y

MAX_BUILDERS = 5


class EconomyFirst:
    """Publish our position, then spawn builder bots up to MAX_BUILDERS.

    Ported from bots/test/starter/main.py's _run_core.
    """

    def run(self, ct: Controller, state: BotState) -> None:
        pos = ct.get_position()
        ct.write_store(SLOT_CORE_X, pos.x)
        ct.write_store(SLOT_CORE_Y, pos.y)

        if state.num_spawned >= MAX_BUILDERS:
            return

        ti = ct.get_global_resources()
        cost = ct.get_builder_bot_cost()
        if ti < cost:
            return

        dirs = list(DIRECTIONS)
        random.shuffle(dirs)
        for d in dirs:
            spawn_pos = pos.add(d)
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                state.num_spawned += 1
                return
