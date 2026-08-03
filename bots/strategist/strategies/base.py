"""Common interface every strategy implements.

Strategies hold no instance state of their own -- all persistent per-unit
memory lives in BotState, passed into run() each round. That's what lets
policy.py swap which Strategy executes without losing continuity across
rounds.
"""

from __future__ import annotations

from typing import Protocol

from fcode import Controller

from state import BotState


class Strategy(Protocol):
    def run(self, ct: Controller, state: BotState) -> None: ...
