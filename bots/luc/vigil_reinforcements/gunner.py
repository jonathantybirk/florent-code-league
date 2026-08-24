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

from constants import (D8, HOME_GUARD_RADIUS_SQ, ROTATE_TITANIUM_RESERVE,
                       SLOT_OWN_CORE, TARGET_VALUE, TURRET_QUIET_ROUNDS)
from utils import unpack_pos

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
    predicted = _track(player, ct, enemies)
    if enemies:
        # Something is here, so this turret is doing its job even on a round it
        # cannot shoot. These rounds never count towards standing down.
        player.quiet_rounds = 0
        _rotate_towards(ct, enemies, predicted)
        return

    player.quiet_rounds += 1
    _stand_down_if_pointless(player, ct)


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
    if not ct.can_fire(target):
        return False
    ct.fire(target)
    return True


def _visible_enemies(ct: Controller) -> list[int]:
    return [entity_id for entity_id in ct.get_nearby_entities()
            if ct.get_team(entity_id) != ct.get_team()]


def _track(player: "Player", ct: Controller, enemies: list[int]) -> dict:
    """Remember where each enemy was, and guess where it is going.

    rotate() costs 10 Ti and sets action cooldown to 1, so a Gunner can never
    fire on the turn it turns. Turning onto where a bot stands therefore always
    hands it a free move, which is why a turret appears to follow a Builder
    around without ever landing a shot. Aim a step ahead instead: one round of
    displacement, repeated, is the whole prediction and it is right whenever
    the bot keeps going the way it was going.
    """
    round_now = ct.get_current_round()
    previous = getattr(player, "tracked", {})
    tracked, predicted = {}, {}
    for entity_id in enemies:
        position = ct.get_position(entity_id)
        tracked[entity_id] = (round_now, position)
        seen = previous.get(entity_id)
        if seen is not None and seen[0] == round_now - 1:
            step_x = position.x - seen[1].x
            step_y = position.y - seen[1].y
            predicted[entity_id] = Position(position.x + step_x,
                                            position.y + step_y)
        else:
            predicted[entity_id] = position
    player.tracked = tracked
    return predicted


def _rotate_towards(ct: Controller, enemies: list[int], predicted: dict) -> bool:
    """Turn onto the most valuable enemy this Gunner could hit once turned.

    Ranked by what the shot is worth rather than by which enemy happens to be
    closest -- a Core or a turret is worth turning past a passing Builder for.
    Distance only breaks ties.

    Rotation is paid for once and useless if the line is blocked, so
    can_fire_from vets the facing first; a bare compass bearing would happily
    spend 10 Ti to stare into a wall.
    """
    if ct.get_global_resources() < ROTATE_TITANIUM_RESERVE:
        return False
    here = ct.get_position()
    ranked = sorted(
        enemies,
        key=lambda entity_id: (
            -TARGET_VALUE.get(ct.get_entity_type(entity_id), 0),
            here.distance_squared(ct.get_position(entity_id)),
            entity_id,
        ),
    )
    for entity_id in ranked:
        # Lead a mover, but keep its current tile as the fallback for anything
        # that did not move or that we have only just seen.
        aims = [predicted.get(entity_id), ct.get_position(entity_id)]
        for target in aims:
            if target is None:
                continue
            for direction in D8:
                if not ct.can_fire_from(here, direction, EntityType.GUNNER,
                                        target):
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
    home = unpack_pos(ct.read_store(SLOT_OWN_CORE))
    if home is not None:
        distance = ct.get_position().distance_squared(Position(*home))
        if distance <= HOME_GUARD_RADIUS_SQ:
            return
    # Nothing after this call runs; the engine tears the unit down inside it.
    ct.self_destruct()
