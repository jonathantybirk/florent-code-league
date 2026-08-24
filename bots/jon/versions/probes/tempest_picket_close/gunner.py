"""Gunner behavior."""

from fcode import Controller, GameError


def run(player, ct: Controller) -> None:
    """Fire unless the ray is known to terminate on our own building."""
    try:
        target = ct.get_gunner_target()
        if target is None:
            return
        # Builders absorb the ray before a co-located building. Deliberately
        # accept friendly-Builder fire rather than losing a Core firing window.
        if ct.get_tile_builder_bot_id(target) is None:
            building = ct.get_tile_building_id(target)
            if building is not None and ct.get_team(building) == ct.get_team():
                return
        if ct.can_fire(target):
            ct.fire(target)
    except GameError:
        return
