"""Compact hand-crafted feature vector for Builder Bot strategy selection.

This is groundwork only (Phase 5's step 2 of the plan): it lets us log and
sanity-check that features actually vary meaningfully across a match before
any training loop exists. Nothing in policy.py consumes these values to make
decisions yet -- that wiring happens once Phase 2's learned selector replaces
the fixed thresholds.

Kept deliberately small (~10 dims) per the plan's "compact hand-crafted
features over raw/spatial ones" lever: the strategies themselves handle
spatial reasoning internally, so the selector only needs enough signal to
pick among a handful of arms, not a full map representation.
"""

from __future__ import annotations

import math

from fcode import Controller, EntityType

from state import BotState
from strategies import STRATEGIES
from utils import SLOT_HARVESTER_COUNT, SLOT_TEAM_POSTURE

MAX_ROUNDS = 1000.0
TITANIUM_NORM = 2000.0
AMMO_NORM = 200.0
TEAM_UNIT_CAP = 50.0
HARVESTER_NORM = 10.0
NEARBY_ENEMY_NORM = 10.0

NUM_BUILDER_STRATEGIES = len(STRATEGIES[EntityType.BUILDER_BOT])

FEATURE_NAMES = (
    "round_phase",
    "own_titanium",
    "own_ammo",
    "own_hp_frac",
    "own_unit_count",
    "own_harvester_count",
    "nearby_enemy_count",
    "distance_to_core",
    "team_posture",
    "last_strategy_idx",
)


def extract_features(ct: Controller, state: BotState) -> tuple[float, ...]:
    pos = ct.get_position()

    if state.core_pos is not None:
        map_diag = math.sqrt(ct.get_map_width() ** 2 + ct.get_map_height() ** 2)
        distance_to_core = min(math.sqrt(pos.distance_squared(state.core_pos)) / map_diag, 1.0)
    else:
        distance_to_core = 1.0

    my_team = ct.get_team()
    nearby_enemies = sum(1 for uid in ct.get_nearby_units() if ct.get_team(uid) != my_team)

    return (
        ct.get_current_round() / MAX_ROUNDS,
        min(ct.get_global_resources() / TITANIUM_NORM, 1.0),
        min(ct.get_global_ammo() / AMMO_NORM, 1.0),
        ct.get_hp() / ct.get_max_hp(),
        min(ct.get_unit_count() / TEAM_UNIT_CAP, 1.0),
        min(ct.read_store(SLOT_HARVESTER_COUNT) / HARVESTER_NORM, 1.0),
        min(nearby_enemies / NEARBY_ENEMY_NORM, 1.0),
        distance_to_core,
        ct.read_store(SLOT_TEAM_POSTURE) / 2.0,
        state.last_strategy_idx / (NUM_BUILDER_STRATEGIES - 1),
    )
