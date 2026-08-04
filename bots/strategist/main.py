"""Strategist bot -- pluggable per-round strategies with a fixed,
hand-written selector (Phase 1 of the multi-strategy architecture).

Each unit still gets its own Player instance, same as bots/test/starter,
but run() no longer hardcodes one behavior per entity type. Instead:
  1. policy.select_strategy() picks which strategy is active this round
  2. strategies.get() looks it up in the per-entity-type registry
  3. the strategy's run(ct, state) executes, with BotState carrying all
     persistent per-unit memory across rounds and across strategy switches

A future phase replaces select_strategy()'s fixed rules with an RL-learned
policy without touching main.py or the strategies themselves.
"""

from __future__ import annotations

from fcode import Controller

import policy
import strategies
from state import BotState


class Player:
    def __init__(self):
        self.state = BotState()
        # Every strategy list's index 0 is the safe/simple fallback -- see run().
        self.fallback_idx = 0

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()

        # An uncaught exception anywhere in this method permanently kills
        # the unit for the rest of the match, so both strategy *selection*
        # and strategy *execution* are guarded -- a broken/misbehaving
        # policy or strategy must never be allowed to propagate.
        try:
            idx = policy.select_strategy(etype, ct, self.state)
        except Exception:
            idx = self.fallback_idx

        # Recorded for features.py's next-round last_strategy_idx feature.
        self.state.last_strategy_idx = idx

        strategy = strategies.get(etype, idx)
        if strategy is None:
            return

        try:
            strategy.run(ct, self.state)
        except Exception:
            fallback = strategies.get(etype, self.fallback_idx)
            if fallback is not None and fallback is not strategy:
                try:
                    fallback.run(ct, self.state)
                except Exception:
                    pass
