"""Sentinel behavior."""

from typing import TYPE_CHECKING

from fcode import Controller

if TYPE_CHECKING:
    from main import Player


def run(player: "Player", ct: Controller) -> None:
    """Run one turn of Sentinel behavior."""
    pass
