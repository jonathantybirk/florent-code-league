"""Launcher relay and active enemy-displacement screen."""

from fcode import Controller, GameError, Position

from constants import (D8, LAUNCH_DIRECTION_BITS, LAUNCH_DIRECTION_MASK,
                       LAUNCH_RANGE_SQ, LAUNCH_REQUEST_SLOTS, SLOT_OWN_CORE)
from utils import unpack_pos


def run(player, ct: Controller) -> None:
    try:
        _run(player, ct)
    except GameError:
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
        direction_index = value & LAUNCH_DIRECTION_MASK
        passenger_id = value >> LAUNCH_DIRECTION_BITS
        if passenger_id and 1 <= direction_index <= len(D8):
            requests.append((slot, passenger_id, direction_index))
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
        return

    slot, passenger, direction_index = request
    origin = ct.get_position(passenger)
    launcher = ct.get_position()
    dx, dy = D8[direction_index - 1].delta()
    choices = []
    for tile in ct.get_nearby_tiles(LAUNCH_RANGE_SQ):
        if not ct.can_launch(origin, tile):
            continue
        offset_x, offset_y = tile.x - launcher.x, tile.y - launcher.y
        projection = offset_x * dx + offset_y * dy
        if projection <= 0:
            continue
        deviation = abs(offset_x * dy - offset_y * dx)
        choices.append((-projection, deviation, -tile.distance_squared(launcher),
                        tile.x, tile.y, tile))
    if not choices:
        return

    *_, destination = min(choices)
    ct.launch(origin, destination)
    thrown.add(passenger)
    player.thrown = thrown
    ct.write_store(slot, 0)


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
