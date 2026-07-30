"""Launcher behavior.

Launchers stay idle until a destination is positively assigned. Blindly
throwing an economy Builder is worse than doing nothing.
"""

from typing import TYPE_CHECKING

from fcode import Controller

if TYPE_CHECKING:
    from main import Player


def run(player: "Player", ct: Controller) -> None:
    return
