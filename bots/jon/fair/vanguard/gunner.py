"""Gunner behaviour.

Hold fire only when the ray stops on a building of ours -- shooting our own
barrier ring or supply line is never useful. Everything else is worth a shot,
including a tile whose occupant we cannot identify: a Core reports no building
id on the three footprint tiles that are not its anchor, and a Gunner that
refused those would never damage the thing it was built to kill.

Measured over the full 180-game field, additionally sparing a *friendly
Builder* standing in the line is not worth it (99-81 against 105-75): it burns
a firing window on a unit that walks out of the way by itself.

Re-aiming an idle Gunner with ct.rotate() was tried and dropped: 10 Ti flat to
turn round looks cheap against 25 plus cost scale for a new one, but the score
was byte-identical at thresholds of 8, 25 and 80 idle rounds, so the case
essentially never arises. Our Gunners are placed on a line to the Core and the
line stays worth shooting.
"""

from fcode import Controller, GameError


def run(player, ct: Controller) -> None:
    try:
        target = ct.get_gunner_target()
        if target is None:
            return
        # A Builder standing on a building soaks the hit, so it owns the tile.
        if ct.get_tile_builder_bot_id(target) is None:
            building = ct.get_tile_building_id(target)
            if building is not None and ct.get_team(building) == ct.get_team():
                return
        if ct.can_fire(target):
            ct.fire(target)
    except GameError:
        return
