"""Mode dispatch table for warden's Builder Bots.

MODE_HANDLERS maps constants.Mode -> a run(ct, state) function. main.py
looks a builder's current state.mode up here every round; policy.py owns
deciding what that mode *is* (ticket default + the threat-promotion
trigger), this module only wires the mode value to its behavior.
"""

from __future__ import annotations

from typing import Callable

from fcode import Controller

from constants import Mode
from state import BuilderState

from . import defence, economy, offence, scouting

MODE_HANDLERS: dict[Mode, Callable[[Controller, BuilderState], None]] = {
    Mode.ECONOMY: economy.run,
    Mode.DEFENCE: defence.run,
    Mode.SCOUTING: scouting.run,
    Mode.OFFENCE: offence.run,
}
