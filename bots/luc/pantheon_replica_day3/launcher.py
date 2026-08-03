"""Launcher relay and active enemy-displacement screen."""

from fcode import Controller, EntityType, GameError, Position

from constants import (D8, HOME_GUARD_RADIUS_SQ, LAUNCHER_QUIET_ROUNDS,
                       PANTHEON_FERRY_PASSENGERS,
                       LAUNCH_DIRECTION_BITS, LAUNCH_DIRECTION_MASK,
                       LAUNCH_RANGE_SQ, LAUNCH_REJECTION_FLAG,
                       LAUNCH_REJECTION_POSITION_BITS,
                       LAUNCH_REQUEST_SLOTS, SLOT_OWN_CORE)
from utils import pack_pos, unpack_core, unpack_pos


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
    if not hasattr(player, "quiet_rounds"):
        player.quiet_rounds = 0

    # Pickup is team-blind in engine 2.3.3. Defensive displacement gets the
    # action first: an enemy beside the screen is thrown maximally away from
    # our Core before friendly relay requests are considered.
    if _launch_enemy_away(ct):
        player.quiet_rounds = 0
        return

    requests = []
    for slot in LAUNCH_REQUEST_SLOTS:
        value = ct.read_store(slot)
        if value & LAUNCH_REJECTION_FLAG:
            continue
        direction_index = value & LAUNCH_DIRECTION_MASK
        passenger_id = value >> LAUNCH_DIRECTION_BITS
        if passenger_id and 1 <= direction_index <= len(D8):
            requests.append((slot, passenger_id, direction_index))
    if not requests:
        # A field ferry with nothing to throw and nothing to watch is a
        # standing +10% tax on every future build. Cost scale is a census of
        # what is alive, so retiring the Launcher refunds it immediately.
        # Ring Launchers near the Core are the throw pad and the displacement
        # screen: they never retire.
        # get_nearby_units returns buildings too; only a mobile enemy is a
        # reason for a displacement screen to stay armed.
        if any(ct.get_team(unit) != ct.get_team()
               and ct.get_entity_type(unit) == EntityType.BUILDER_BOT
               for unit in ct.get_nearby_units()):
            player.quiet_rounds = 0
        else:
            player.quiet_rounds += 1
        if player.quiet_rounds >= LAUNCHER_QUIET_ROUNDS:
            home, _ = unpack_core(ct.read_store(SLOT_OWN_CORE))
            if home is None or (ct.get_position().distance_squared(
                    Position(*home)) > HOME_GUARD_RADIUS_SQ):
                ct.self_destruct()
        return
    player.quiet_rounds = 0

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

    slot, passenger, direction_index = request
    origin = ct.get_position(passenger)
    launcher = ct.get_position()
    dx, dy = D8[direction_index - 1].delta()
    enemy_launchers = _visible_enemy_launchers(ct)
    unsafe_landings = _enemy_launcher_hazards(enemy_launchers)
    choices = []
    for tile in ct.get_nearby_tiles(LAUNCH_RANGE_SQ):
        if not ct.can_launch(origin, tile) or tuple(tile) in unsafe_landings:
            continue
        offset_x, offset_y = tile.x - launcher.x, tile.y - launcher.y
        projection = offset_x * dx + offset_y * dy
        if projection <= 0:
            continue
        deviation = abs(offset_x * dy - offset_y * dx)
        choices.append((-projection, deviation, -tile.distance_squared(launcher),
                        tile.x, tile.y, tile))
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
    _retire_if_spent(player, ct)


def _retire_if_spent(player, ct):
    """Raze the pad once it has ferried its four passengers.

    A live Launcher is +10% on every future build cost for as long as it
    exists, and cost scale is a census of what is alive rather than what was
    ever built -- so razing it refunds the 10% immediately. Pantheon does
    exactly this: 147 of 151 of its Launchers live precisely five rounds, built
    r1 and gone r6, the round after the fourth throw, with nothing adjacent and
    the removal falling inside the Launcher's own turn. It rents the throw
    range for four rounds and takes the tax off for the other ~995.

    Ragnarok never retires a ring Launcher, on the grounds that it doubles as
    the displacement screen. Keeping that: the pad only goes if the four
    opening passengers are away and no enemy is close enough to need screening.
    """
    if len(player.thrown) < PANTHEON_FERRY_PASSENGERS:
        return
    if any(ct.get_team(unit) != ct.get_team()
           and ct.get_entity_type(unit) == EntityType.BUILDER_BOT
           for unit in ct.get_nearby_units()):
        return
    ct.self_destruct()


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
    home, _ = unpack_core(ct.read_store(SLOT_OWN_CORE))
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
