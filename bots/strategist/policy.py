"""Fixed, hand-written strategy selector (Phase 1 -- no RL yet).

select_strategy() re-encodes the same threshold bots/test/starter/main.py
uses (economy-first, then defense once TARGET_HARVESTERS is hit) as an
explicit index into strategies.STRATEGIES, plus a new opportunistic
sabotage rule, instead of inline if/elif. This is the seam a future
RL-learned selector replaces without touching main.py or the strategies
themselves.
"""

from __future__ import annotations

from fcode import Controller, EntityType

from state import BotState
from utils import CARDINALS, SLOT_HARVESTER_COUNT, in_bounds

TARGET_HARVESTERS = 3

IDX_HARVESTER_RUSH = 0
IDX_GUNNER_DEFENSE = 1
IDX_SABOTEUR_SCOUT = 2


def select_strategy(entity_type: EntityType, ct: Controller, state: BotState) -> int:
    if entity_type != EntityType.BUILDER_BOT:
        return 0

    pos = ct.get_position()
    my_team = ct.get_team()
    for d in CARDINALS:
        check = pos.add(d)
        if not in_bounds(ct, check):
            continue
        building_id = ct.get_tile_building_id(check)
        if building_id is not None and ct.get_team(building_id) != my_team:
            return IDX_SABOTEUR_SCOUT

    harvester_count = ct.read_store(SLOT_HARVESTER_COUNT)
    if harvester_count < TARGET_HARVESTERS:
        return IDX_HARVESTER_RUSH
    return IDX_GUNNER_DEFENSE
