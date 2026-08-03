"""Registry of available strategies per entity type.

policy.select_strategy() returns an index into these lists; main.py looks
the strategy up here and calls its run(). Index 0 in every list doubles as
the fallback strategy if the selected one raises (see main.py).
"""

from __future__ import annotations

from fcode import EntityType

from strategies.base import Strategy
from strategies.builder import GunnerDefense, HarvesterRush, SaboteurScout
from strategies.core import EconomyFirst
from strategies.gunner import AutoFire

STRATEGIES: dict[EntityType, list[Strategy]] = {
    EntityType.CORE: [EconomyFirst()],
    EntityType.BUILDER_BOT: [HarvesterRush(), GunnerDefense(), SaboteurScout()],
    EntityType.GUNNER: [AutoFire()],
}


def get(entity_type: EntityType, idx: int) -> Strategy | None:
    available = STRATEGIES.get(entity_type)
    if not available:
        return None
    return available[idx % len(available)]
