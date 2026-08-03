"""Gunner strategies."""

from __future__ import annotations

from fcode import Controller

from state import BotState


class AutoFire:
    """Fire at the first enemy in our line of sight.

    Ported from bots/test/starter/main.py's _run_gunner.
    """

    def run(self, ct: Controller, state: BotState) -> None:
        target = ct.get_gunner_target()
        if target is not None and ct.can_fire(target):
            ct.fire(target)
