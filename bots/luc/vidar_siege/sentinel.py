"""Sentinel behavior: snipe the enemy Core through anything, else clean up.

A Sentinel's shot is never blocked -- walls, buildings, and bodies are all
transparent to it -- so a siege Sentinel aligned with the enemy Core kills it
on a fixed clock (500 / 18 damage at a 3-round reload = 84 rounds) no matter
what the defender builds. The Core therefore outranks every other target,
and the store's enemy-Core position is enough: vision is not required for a
legal shot, only range and alignment, which can_fire checks for us.
"""

from typing import TYPE_CHECKING

from fcode import Controller, EntityType, GameError, Position

from constants import SLOT_ENEMY_CORE
from utils import unpack_enemy

if TYPE_CHECKING:
    from main import Player


def run(player: "Player", ct: Controller) -> None:
    try:
        _run(player, ct)
    except GameError as error:
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            f"action=sentinel run reason=GameError: {error}"
        )
        return


# A Builder Bot this close is worth the shot ahead of the Core, whichever end
# of the map this Sentinel is standing at. Builder vision is r^2=20, so this is
# "close enough to be doing something to us or to the Core we are shooting".
BUILDER_PRIORITY_RADIUS_SQ = 20


def _run(player: "Player", ct: Controller) -> None:
    team = ct.get_team()
    here = ct.get_position()
    enemies = [entity_id for entity_id in ct.get_nearby_entities()
               if ct.get_team(entity_id) != team
               and ct.can_fire(ct.get_position(entity_id))]
    # Builder Bots first, and for the same reason at both ends of the map.
    #
    # Defending, the intruder emplacing at our Core is the whole enemy attack:
    # their Core will not spawn a replacement while their other Builders still
    # answer the heartbeat, so a Builder killed on our doorstep is an attack
    # that does not come back. 40 HP is three Sentinel shots.
    #
    # Besieging, it is the arithmetic of healing. A Builder restores 4 HP for a
    # flat 1 Ti, unaffected by cost scale, so one mender standing on the Core
    # cancels two thirds of a Sentinel's 6 damage a round and two menders
    # outlast the whole battery. Shooting the Core past a mender is paying 10
    # ammunition a shot to lose slowly; shooting the mender ends it.
    builders = [entity_id for entity_id in enemies
                if ct.get_entity_type(entity_id) is EntityType.BUILDER_BOT
                and ct.get_position(entity_id).distance_squared(here)
                <= BUILDER_PRIORITY_RADIUS_SQ]
    if builders:
        ct.fire(ct.get_position(min(builders, key=ct.get_hp)))
        return
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
    if enemies:
        target = min(enemies, key=ct.get_hp)
        ct.fire(ct.get_position(target))
