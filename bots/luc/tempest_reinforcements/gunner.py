"""Gunner behavior."""

from typing import TYPE_CHECKING

from fcode import Controller

if TYPE_CHECKING:
    from main import Player


def run(player: "Player", ct: Controller) -> None:
    """Fire at the first target in the current ray when locally supplied."""
    target = ct.get_gunner_target()
    if target is None:
        return
    target_id = ct.get_tile_builder_bot_id(target)
    if target_id is None:
        target_id = ct.get_tile_building_id(target)
    if target_id is None:
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            f"action=fire target={tuple(target)} reason=no entity on target"
        )
        return
    if ct.get_team(target_id) == ct.get_team():
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            f"action=fire target={tuple(target)} reason=friendly entity blocks ray"
        )
        return
    if not ct.can_fire(target):
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            f"action=fire target={tuple(target)} reason=can_fire rejected target"
        )
        return
    ct.fire(target)
