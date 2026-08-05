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

from constants import (D8, HOLD_FIRE_ON_TENDED_BARRIER,
                       HOME_GUARD_RADIUS_SQ, SLOT_ENEMY_CORE,
                       SLOT_OWN_CORE, TURRET_QUIET_ROUNDS)
from utils import unpack_core, unpack_enemy

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


def _run(player: "Player", ct: Controller) -> None:
    if not hasattr(player, "quiet_rounds"):
        player.quiet_rounds = 0
    packed = ct.read_store(SLOT_ENEMY_CORE)
    if packed:
        core, _ = unpack_enemy(packed)
        for dx in (0, 1):
            for dy in (0, 1):
                tile = Position(core[0] + dx, core[1] + dy)
                if ct.can_fire(tile):
                    ct.fire(tile)
                    player.quiet_rounds = 0
                    return
    # No Core tile on the line: fire at the lowest-HP visible enemy instead.
    targets = [entity_id for entity_id in ct.get_nearby_entities()
               if ct.get_team(entity_id) != ct.get_team()
               and ct.can_fire(ct.get_position(entity_id))
               and not _is_tended_barrier(ct, entity_id)]
    if targets:
        target = min(targets, key=ct.get_hp)
        ct.fire(ct.get_position(target))
        player.quiet_rounds = 0
        return

    _stand_down_if_pointless(player, ct)


def _stand_down_if_pointless(player: "Player", ct: Controller) -> None:
    """Retire a Sentinel that has had nothing to shoot for a long time.

    The Gunner has had this since vigil; the Sentinel never did, and it is the
    unit that needs it most. A Sentinel is 30 Ti and **+20%** on every price the
    team pays for as long as it stands, and unlike a Gunner it *cannot rotate* --
    so a Sentinel whose line has gone quiet has not merely stopped being useful,
    it has no way of ever becoming useful again. The enemy walked around it and
    it will point at that empty corridor for the remaining nine hundred rounds,
    charging rent on every Harvester and every barrier we build.

    Cost scale is a census of what is alive rather than what was ever built, so
    self-destructing refunds the 20% the moment it happens.

    Turrets close to our own Core are exempt whatever they have seen, exactly as
    for Gunners: they are insurance against the one rush that does arrive, and
    the round they are needed is the round it is too late to rebuild them.
    """
    if _enemy_on_the_line(ct):
        # Has a target and merely cannot shoot it: out of ammunition, or still
        # reloading. That is the opposite of pointless -- the turret is doing
        # its job and the team is failing to supply it, and retiring it would
        # answer an ammunition shortage by destroying the thing waiting on the
        # ammunition. `can_fire` folds ammo and cooldown into its answer, so
        # the raw attack pattern is what has to be consulted here.
        player.quiet_rounds = 0
        return
    player.quiet_rounds += 1
    if player.quiet_rounds < TURRET_QUIET_ROUNDS:
        return
    home, _ = unpack_core(ct.read_store(SLOT_OWN_CORE))
    if home is not None:
        if ct.get_position().distance_squared(Position(*home)) <= HOME_GUARD_RADIUS_SQ:
            return
    # Nothing after this call runs; the engine tears the unit down inside it.
    ct.self_destruct()


def _enemy_on_the_line(ct: Controller) -> bool:
    """Is anything of theirs standing in this turret's raw attack pattern?

    `get_attackable_tiles` ignores ammunition, cooldown and occupancy, which is
    exactly what is wanted: the question is whether this turret still covers
    something worth covering, not whether it can pull the trigger this round.
    """
    try:
        tiles = ct.get_attackable_tiles()
    except GameError:
        return False
    for tile in tiles:
        for lookup in (ct.get_tile_builder_bot_id, ct.get_tile_building_id):
            entity_id = lookup(tile)
            if entity_id is not None and ct.get_team(entity_id) != ct.get_team():
                return True
    return False


def _is_tended_barrier(ct: Controller, target_id: int) -> bool:
    """Skip a barrier whose Builder is still standing beside it.

    Same trade as the Gunner's, and worse: 18 damage for 10 Ti of ammunition
    against a 30 HP barrier they replace for 3. Two shots to break it, 20 Ti
    spent, and the Builder next to it puts it straight back. Every other target
    on this list is worth more than the wall, which is why this only filters
    barriers rather than deferring the whole volley -- with the wall skipped,
    min() simply picks the next-weakest real target.
    """
    if not HOLD_FIRE_ON_TENDED_BARRIER:
        return False
    if ct.get_entity_type(target_id) != EntityType.BARRIER:
        return False
    here = ct.get_position(target_id)
    for direction in D8:
        neighbour = here.add(direction)
        bot_id = ct.get_tile_builder_bot_id(neighbour)
        if bot_id is not None and ct.get_team(bot_id) != ct.get_team():
            return True
    return False
