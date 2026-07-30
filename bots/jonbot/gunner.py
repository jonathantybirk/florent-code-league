"""Gunner behavior."""

from typing import TYPE_CHECKING

from fcode import Controller

if TYPE_CHECKING:
    from main import Player


def run(player: "Player", ct: Controller) -> None:
    """Fire at the first target in the current ray when locally supplied."""
    target = ct.get_gunner_target()
    if target is not None and ct.can_fire(target):
        ct.fire(target)
