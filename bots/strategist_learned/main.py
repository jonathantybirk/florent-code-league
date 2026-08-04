"""Learned-selector counterpart to bots/strategist, used only for the Phase 5
evaluation gate (training/evaluate.py) -- never intended for ladder submission.

bots/strategist/policy.py picks strategies via fixed hand-written thresholds;
this bot picks via argmax over training/train_bandit.py's fit ARM_WEIGHTS
(bots/strategist/policy_weights.py) instead, so the two can be compared
head-to-head and against the same opponent pool. They need separate bot
paths rather than one bot toggled by an env var, because a single `fcode
run` match shares one process/env between both sides -- an env var can't
tell bot_a to use fixed rules while bot_b uses the learned ones.

Reuses bots/strategist's state/strategies/utils/features modules unchanged
via sys.path (see the append below) rather than copying them, so this bot
can never drift from bots/strategist on anything except strategy selection.
Only policy.py differs.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "strategist"))

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

        try:
            idx = policy.select_strategy(etype, ct, self.state)
        except Exception:
            idx = self.fallback_idx

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
