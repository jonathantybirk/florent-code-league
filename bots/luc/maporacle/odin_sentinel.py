"""Sentinel behavior: snipe the enemy Core through anything, else clean up.

A Sentinel's shot is never blocked -- walls, buildings, and bodies are all
transparent to it -- so a siege Sentinel aligned with the enemy Core kills it
on a fixed clock (500 / 18 damage at a 3-round reload = 84 rounds) no matter
what the defender builds. The Core therefore outranks every other target,
and the store's enemy-Core position is enough: vision is not required for a
legal shot, only range and alignment, which can_fire checks for us.
"""

from typing import TYPE_CHECKING

from fcode import Controller, GameError, Position

from odin_constants import SLOT_ENEMY_CORE
from odin_utils import unpack_enemy

if TYPE_CHECKING:
    from odin_main import Player


def run(player: "Player", ct: Controller) -> None:
    try:
        _run(player, ct)
    except GameError as error:
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            f"action=sentinel run reason=GameError: {error}"
        )
        return


def _run(player: "Player", ct: Controller) -> None:
    packed = ct.read_store(SLOT_ENEMY_CORE)
    if packed:
        core, _ = unpack_enemy(packed)
        for dx in (0, 1):
            for dy in (0, 1):
                tile = Position(core[0] + dx, core[1] + dy)
                if ct.can_fire(tile):
                    ct.fire(tile)
                    return
    # No Core tile on the line: fire at the lowest-HP visible enemy instead.
    targets = [entity_id for entity_id in ct.get_nearby_entities()
               if ct.get_team(entity_id) != ct.get_team()
               and ct.can_fire(ct.get_position(entity_id))]
    if targets:
        target = min(targets, key=ct.get_hp)
        ct.fire(ct.get_position(target))
