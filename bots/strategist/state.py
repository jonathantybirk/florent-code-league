"""Persistent per-unit memory, passed into every Strategy.run() call.

Keeping all state here -- rather than as ad hoc self.* attributes on Player,
as in bots/test/starter/main.py -- is what lets policy.py swap which
Strategy runs a given round without losing continuity.
"""

from __future__ import annotations

from dataclasses import dataclass

from fcode import Position


@dataclass
class BotState:
    # Core
    num_spawned: int = 0

    # Builder bot navigation (shared across HarvesterRush / GunnerDefense)
    target: Position | None = None
    last_pos: Position | None = None
    stuck: int = 0
    core_pos: Position | None = None

    # SaboteurScout
    sabotage_target: Position | None = None

    # Set by main.py after each decision; read by features.py as context for
    # the *next* decision.
    last_strategy_idx: int = 0

    # policy.py's epsilon-greedy exploration override (FCL_EXPLORE_EPS): once
    # triggered, held for a fixed round window instead of re-rolled every
    # round, so a window is one coherent macro-decision instead of noise.
    # explore_until_round stays -1 (never >= any real round) until the first
    # override fires.
    explore_idx: int = 0
    explore_until_round: int = -1
