"""Fixed, hand-written strategy selector (Phase 1 -- no RL yet).

select_strategy() re-encodes the same threshold bots/test/starter/main.py
uses (economy-first, then defense once TARGET_HARVESTERS is hit) as an
explicit index into strategies.STRATEGIES, plus a new opportunistic
sabotage rule, instead of inline if/elif. This is the seam a future
RL-learned selector replaces without touching main.py or the strategies
themselves.

When the FCL_TELEMETRY_PATH env var is set, every Builder Bot decision is
logged (features + chosen strategy) as one JSON line -- training-only
groundwork (Phase 5's step 2 of the plan) for sanity-checking that features
vary meaningfully before any training loop exists. Unset in the ladder
submission, this is a no-op.
"""

from __future__ import annotations

import json
import os
import random

from fcode import Controller, EntityType

import features
from state import BotState
from utils import CARDINALS, SLOT_HARVESTER_COUNT, in_bounds

TARGET_HARVESTERS = 3

IDX_HARVESTER_RUSH = 0
IDX_GUNNER_DEFENSE = 1
IDX_SABOTEUR_SCOUT = 2
NUM_ARMS = 3

_TELEMETRY_PATH = os.environ.get("FCL_TELEMETRY_PATH")

# Off-policy data collection only (training/train_bandit.py's per-arm
# regression). Unset (0.0) everywhere except a dedicated exploring harness
# run -- a no-op in the ladder submission and in fixed-rule-only runs.
_EXPLORE_EPS = float(os.environ.get("FCL_EXPLORE_EPS", "0.0"))
# Rounds an exploration override holds once triggered, so it reads as one
# coherent macro-decision window (matching the plan's K~25-50 temporal
# abstraction) instead of flipping every round.
_EXPLORE_WINDOW = 30


def _log_decision(ct: Controller, feats: tuple[float, ...], idx: int, team, explored: bool) -> None:
    if not _TELEMETRY_PATH:
        return
    # Each unit writes to its own file (FCL_TELEMETRY_PATH is a *prefix*, not
    # a literal path) rather than sharing one file per match. The engine
    # runs multiple Builder Bots' Player.run() concurrently within a match
    # (confirmed by observing interleaved/corrupted JSON lines when several
    # of strategist's own Builder Bots shared one telemetry file -- the same
    # reason Lucas's rl/ pipeline needed a whole separate inference-server
    # process rather than importing torch directly). A single unit only
    # ever writes from its own sequential round-by-round calls, so a
    # per-unit file needs no locking to stay race-free.
    path = f"{_TELEMETRY_PATH}.{team.value}.{ct.get_id()}.jsonl"
    record = {
        "round": ct.get_current_round(),
        "team": team.value,
        "unit_id": ct.get_id(),
        "features": feats,
        "strategy_idx": idx,
        "explored": explored,
    }
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def _maybe_explore(ct: Controller, state: BotState, fixed_idx: int) -> tuple[int, bool]:
    """With probability _EXPLORE_EPS, override the fixed rule with a uniform
    random arm held for _EXPLORE_WINDOW rounds.

    Off-policy data collection only. Needed because train_bandit.py's
    per-arm regression otherwise never observes e.g. GunnerDefense chosen at
    round 0 -- the fixed rule only ever picks it once harvester_count >=
    TARGET_HARVESTERS -- so it has to extrapolate blind outside that support
    and ends up picking a degenerate always-GunnerDefense policy (confirmed
    via training/evaluate.py: an unexplored fit lost 0-16 against the fixed
    rule, always choosing GunnerDefense including at turn 0). Overrides the
    sabotage rule too, deliberately: coverage needs HarvesterRush/
    GunnerDefense sampled even when adjacent to an enemy building, and
    SaboteurScout sampled even when not, neither of which the fixed rule
    alone would ever produce.
    """
    if _EXPLORE_EPS <= 0.0:
        return fixed_idx, False

    current_round = ct.get_current_round()
    if state.explore_until_round >= current_round:
        return state.explore_idx, True

    if random.random() < _EXPLORE_EPS:
        state.explore_idx = random.randrange(NUM_ARMS)
        state.explore_until_round = current_round + _EXPLORE_WINDOW
        return state.explore_idx, True

    return fixed_idx, False


def select_strategy(entity_type: EntityType, ct: Controller, state: BotState) -> int:
    if entity_type != EntityType.BUILDER_BOT:
        return 0

    # Extracted before the decision below so last_strategy_idx reflects the
    # *previous* round's choice -- main.py updates it after this returns.
    feats = features.extract_features(ct, state)

    pos = ct.get_position()
    my_team = ct.get_team()
    idx = None
    for d in CARDINALS:
        check = pos.add(d)
        if not in_bounds(ct, check):
            continue
        building_id = ct.get_tile_building_id(check)
        if building_id is not None and ct.get_team(building_id) != my_team:
            idx = IDX_SABOTEUR_SCOUT
            break

    if idx is None:
        harvester_count = ct.read_store(SLOT_HARVESTER_COUNT)
        idx = IDX_HARVESTER_RUSH if harvester_count < TARGET_HARVESTERS else IDX_GUNNER_DEFENSE

    idx, explored = _maybe_explore(ct, state, idx)

    _log_decision(ct, feats, idx, my_team, explored)
    return idx
