"""Gunner behaviour: fire, else turn to face the fight, else stand down.

The ladder meta this chases keeps every turret pointed at something. A Gunner
fires down one fixed ray, so a turret built to cover an approach the enemy then
walks around is a building that never fires again -- and, worse, it keeps
charging its +10% on every build the team makes for the rest of the game.

So a Gunner here does one of three things each round. It fires if it has a
target. Failing that it rotates onto the nearest enemy it can get a real firing
solution against. Failing that, and only after a long quiet stretch, it removes
itself and hands the scale back.
"""

from typing import TYPE_CHECKING

from fcode import Controller, EntityType, GameError, Position

from constants import (D8, HOLD_FIRE_ON_TENDED_BARRIER, HOME_GUARD_RADIUS_SQ,
                       ROTATE_TITANIUM_RESERVE, SLOT_OWN_CORE,
                       TURRET_QUIET_ROUNDS)
from utils import unpack_core

if TYPE_CHECKING:
    from main import Player


def run(player: "Player", ct: Controller) -> None:
    try:
        _run(player, ct)
    except GameError as error:
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            f"action=gunner run reason=GameError: {error}"
        )
        return


def _run(player: "Player", ct: Controller) -> None:
    if not hasattr(player, "quiet_rounds"):
        player.quiet_rounds = 0

    if _fire_at_ray_target(ct):
        player.quiet_rounds = 0
        return

    enemies = _visible_enemies(ct)
    if enemies:
        # Something is here, so this turret is doing its job even on a round it
        # cannot shoot. These rounds never count towards standing down.
        player.quiet_rounds = 0
        _rotate_towards(ct, enemies)
        return

    if _enemy_on_the_line(ct):
        # Covering something it cannot currently shoot -- no ammunition, or
        # reloading. Not idle, and not a candidate for retirement: destroying a
        # turret because the team ran out of ammunition answers the shortage by
        # removing the thing that was waiting on it.
        player.quiet_rounds = 0
        return
    player.quiet_rounds += 1
    _stand_down_if_pointless(player, ct)


def _enemy_on_the_line(ct: Controller) -> bool:
    """Anything of theirs inside the raw attack pattern, ammo and cooldown aside."""
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


def _fire_at_ray_target(ct: Controller) -> bool:
    """Fire down the current facing if an enemy is first on the ray."""
    target = ct.get_gunner_target()
    if target is None:
        return False
    target_id = ct.get_tile_builder_bot_id(target)
    if target_id is None:
        target_id = ct.get_tile_building_id(target)
    if target_id is None or ct.get_team(target_id) == ct.get_team():
        # One of our own bots walking across the ray is the ordinary case and
        # not worth a diagnostic line every round.
        return False
    if _is_tended_barrier(ct, target, target_id):
        return False
    if not ct.can_fire(target):
        return False
    ct.fire(target)
    return True


def _is_tended_barrier(ct: Controller, target: Position, target_id: int) -> bool:
    """A barrier with its Builder still beside it is a trade we lose.

    Firing is an explicit call, so holding fire is something this turret can
    actually choose. It should: a barrier is 30 HP for 3 Ti, the cheapest object
    on the board, and this Gunner needs five shots and 20 Ti of ammunition to
    break one. If the Builder that laid it is still standing next to it, the
    barrier is back up for 3 Ti the round after we finish -- we buy nothing and
    hand them a 17 Ti profit on every cycle.

    Hold instead, and take the same wall once its Builder has walked away. The
    wall is not going anywhere, and every round it stands is a round that Builder
    is laying barriers instead of carrying a turret towards our Core.

    Only barriers. A conveyor is worth breaking whoever is standing over it,
    because the income stops the moment the tile does, and a turret is worth
    breaking always.
    """
    if not HOLD_FIRE_ON_TENDED_BARRIER:
        return False
    if ct.get_entity_type(target_id) != EntityType.BARRIER:
        return False
    for direction in D8:
        neighbour = target.add(direction)
        bot_id = ct.get_tile_builder_bot_id(neighbour)
        if bot_id is not None and ct.get_team(bot_id) != ct.get_team():
            return True
    return False


def _visible_enemies(ct: Controller) -> list[int]:
    return [entity_id for entity_id in ct.get_nearby_entities()
            if ct.get_team(entity_id) != ct.get_team()]


def _rotate_towards(ct: Controller, enemies: list[int]) -> bool:
    """Turn onto the nearest enemy this Gunner could actually hit once turned.

    Rotation costs 10 Ti and a round of cooldown, so it is only worth paying
    when the new facing yields a real firing solution. can_fire_from checks the
    line for blockers; a bare compass bearing towards the enemy does not, and
    would happily spend 10 Ti to stare into a wall.
    """
    if ct.get_global_resources() < ROTATE_TITANIUM_RESERVE:
        return False
    here = ct.get_position()
    ranked = sorted(
        enemies,
        key=lambda entity_id: (
            here.distance_squared(ct.get_position(entity_id)), entity_id,
        ),
    )
    for entity_id in ranked:
        target = ct.get_position(entity_id)
        for direction in D8:
            if not ct.can_fire_from(here, direction, EntityType.GUNNER, target):
                continue
            if not ct.can_rotate(direction):
                continue
            ct.rotate(direction)
            return True
    return False


def _stand_down_if_pointless(player: "Player", ct: Controller) -> None:
    """Remove a turret that has watched an empty map for long enough.

    Cost scaling is a tally of what the team has standing, not of what it once
    spent: destroying a Gunner hands its +10% back and makes every later
    Harvester and Launcher cheaper. A turret covering a corner the enemy never
    uses is not merely idle, it is charging rent on everything else we build.

    Turrets near our own Core are exempt whatever they have seen. They are
    insurance against the one rush that does arrive, and the round they are
    needed is the round it is too late to rebuild them.
    """
    if player.quiet_rounds < TURRET_QUIET_ROUNDS:
        return
    home, _ = unpack_core(ct.read_store(SLOT_OWN_CORE))
    if home is not None:
        distance = ct.get_position().distance_squared(Position(*home))
        if distance <= HOME_GUARD_RADIUS_SQ:
            return
    # Nothing after this call runs; the engine tears the unit down inside it.
    ct.self_destruct()
