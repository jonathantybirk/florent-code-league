"""Sentinel behaviour.

Vanguard does not currently build Sentinels: at 10 ammunition for 18 damage
they return 1.8 damage per titanium against a Gunner's 5, and the siege is
throughput-limited. The handler exists so a captured or future Sentinel still
shoots something useful.
"""

from fcode import Controller, GameError


def run(player, ct: Controller) -> None:
    try:
        targets = [entity for entity in ct.get_nearby_entities()
                   if ct.get_team(entity) != ct.get_team()
                   and ct.can_fire(ct.get_position(entity))]
        if targets:
            ct.fire(ct.get_position(min(targets, key=lambda e: (ct.get_hp(e), e))))
    except GameError:
        return
