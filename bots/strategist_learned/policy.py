"""Learned strategy selector: argmax over training/train_bandit.py's fit
ARM_WEIGHTS (bots/strategist/policy_weights.py), in place of
bots/strategist/policy.py's fixed thresholds. See main.py's docstring for
why this lives in a separate bot directory instead of an env-var toggle.

No telemetry logging here -- this bot exists to be evaluated, not to
generate more training data.
"""

from __future__ import annotations

from fcode import Controller, EntityType

import features
from policy_weights import ARM_WEIGHTS
from state import BotState


def select_strategy(entity_type: EntityType, ct: Controller, state: BotState) -> int:
    if entity_type != EntityType.BUILDER_BOT:
        return 0

    feats = features.extract_features(ct, state)
    scores = [
        sum(w * f for w, f in zip(arm["w"], feats)) + arm["b"]
        for arm in ARM_WEIGHTS
    ]
    return max(range(len(scores)), key=scores.__getitem__)
