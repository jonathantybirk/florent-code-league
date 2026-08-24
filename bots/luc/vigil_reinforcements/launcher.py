"""Launcher relay and active enemy-displacement screen."""

from fcode import Controller, EntityType, GameError, Position

from constants import (D8, LAUNCH_OVERHEAD_ROUNDS,
                       LAUNCH_TARGET_BITS, LAUNCH_TARGET_MASK,
                       LAUNCH_RANGE_SQ, LAUNCH_REJECTION_FLAG,
                       LAUNCH_REJECTION_POSITION_BITS,
                       LAUNCH_REQUEST_SLOTS, SLOT_OWN_CORE)
from utils import pack_pos, unpack_pos


def run(player, ct: Controller) -> None:
    try:
        _run(player, ct)
    except GameError as error:
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            f"action=launcher run reason=GameError: {error}"
        )
        return


def _run(player, ct):
    # Pickup is team-blind in engine 2.3.3. Defensive displacement gets the
    # action first: an enemy beside the screen is thrown maximally away from
    # our Core before friendly relay requests are considered.
    if _launch_enemy_away(ct):
        return

    requests = []
    for slot in LAUNCH_REQUEST_SLOTS:
        value = ct.read_store(slot)
        if value & LAUNCH_REJECTION_FLAG:
            continue
        packed_target = value & LAUNCH_TARGET_MASK
        passenger_id = value >> LAUNCH_TARGET_BITS
        if passenger_id and packed_target:
            requests.append((slot, passenger_id, packed_target))
    if not requests:
        return

    thrown = getattr(player, "thrown", set())
    nearby = set(ct.get_nearby_units(2))
    request = next(
        (request for request in requests
         if request[1] in nearby
         and request[1] not in thrown
         and ct.get_team(request[1]) == ct.get_team()),
        None,
    )
    if request is None:
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            "action=launch reason=no requested friendly passenger is adjacent"
        )
        return

    slot, passenger, packed_target = request
    origin = ct.get_position(passenger)
    launcher = ct.get_position()
    target = Position(*unpack_pos(packed_target))
    enemy_launchers = _visible_enemy_launchers(ct)
    unsafe_landings = _enemy_launcher_hazards(enemy_launchers)
    choices = []
    # Builders move cardinally, so the walk a throw saves is the difference in
    # Manhattan steps -- not in straight-line distance. A throw one tile
    # diagonally looks like progress by any radial measure and is worth exactly
    # two steps of walking, against the two rounds the passenger spends
    # announcing and waiting. It has to beat that margin, not merely improve
    # on standing still, or the ferry is slower than legs.
    here = _walk(origin, target)
    for tile in ct.get_nearby_tiles(LAUNCH_RANGE_SQ):
        if not ct.can_launch(origin, tile) or tuple(tile) in unsafe_landings:
            continue
        landing = _walk(tile, target)
        if here - landing <= LAUNCH_OVERHEAD_ROUNDS:
            continue
        choices.append((landing, tile.x, tile.y, tile))
    if not choices:
        # Return the nearest visible blocking Launcher to the passenger in the
        # same request slot, so it can stop waiting and build a demolition
        # Gunner instead of re-announcing forever.
        blocker = min(enemy_launchers, key=lambda position: (
            position.distance_squared(launcher), position.x, position.y,
        ), default=None)
        packed_blocker = pack_pos(tuple(blocker)) if blocker is not None else 0
        rejection = (LAUNCH_REJECTION_FLAG
                     | (passenger << LAUNCH_REJECTION_POSITION_BITS)
                     | packed_blocker)
        ct.write_store(slot, rejection)
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            f"action=launch passenger={passenger} "
            "reason=no safe legal forward landing"
        )
        return

    *_, destination = min(choices)
    ct.launch(origin, destination)
    thrown.add(passenger)
    player.thrown = thrown
    ct.write_store(slot, 0)


def _walk(a, b) -> int:
    """Cardinal steps between two tiles; Builders cannot move diagonally."""
    return abs(a.x - b.x) + abs(a.y - b.y)


def _visible_enemy_launchers(ct):
    """Return positions of enemy Launchers visible to this ferry."""
    return [ct.get_position(entity_id) for entity_id in ct.get_nearby_buildings()
            if ct.get_team(entity_id) != ct.get_team()
            and ct.get_entity_type(entity_id) == EntityType.LAUNCHER]


def _enemy_launcher_hazards(launchers):
    """Tiles from which the visible enemy Launchers could pick up a passenger."""
    hazards = set()
    for position in launchers:
        hazards.add(tuple(position))
        hazards.update(
            (position.x + dx, position.y + dy)
            for dx, dy in (direction.delta() for direction in D8)
        )
    return hazards


def _launch_enemy_away(ct):
    """Throw an adjacent enemy Builder to the legal tile farthest from home."""
    home = unpack_pos(ct.read_store(SLOT_OWN_CORE))
    if home is None:
        return False
    home_position = Position(*home)
    launcher = ct.get_position()
    enemies = [unit for unit in ct.get_nearby_units(2)
               if ct.get_team(unit) != ct.get_team()]
    choices = []
    for enemy_id in enemies:
        origin = ct.get_position(enemy_id)
        for tile in ct.get_nearby_tiles(LAUNCH_RANGE_SQ):
            if not ct.can_launch(origin, tile):
                continue
            choices.append((
                -tile.distance_squared(home_position),
                -tile.distance_squared(launcher),
                tile.x,
                tile.y,
                origin,
                tile,
            ))
    if not choices:
        return False
    *_, origin, destination = min(choices)
    ct.launch(origin, destination)
    return True
