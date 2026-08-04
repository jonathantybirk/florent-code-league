"""Launcher relay and active enemy-displacement screen."""

from collections import deque

from atlas import identify_visible

from fcode import Controller, EntityType, GameError, Position

from constants import (D8, HOME_GUARD_RADIUS_SQ, LAUNCH_RANGE_SQ,
                       LAUNCHER_QUIET_ROUNDS, PANTHEON_FERRY_PASSENGERS,
                       PANTHEON_RAIDERS,
                       SLOT_ENEMY_CORE,
                       LAUNCH_DIRECTION_BITS, LAUNCH_DIRECTION_MASK,
                       LAUNCH_RANGE_SQ, LAUNCH_REJECTION_FLAG,
                       LAUNCH_REJECTION_POSITION_BITS,
                       LAUNCH_REQUEST_SLOTS, SLOT_OWN_CORE)
from utils import pack_pos, unpack_core, unpack_enemy, unpack_pos


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
    if not requests and _opening_throw(player, ct):
        return
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


def _ore_landing(player, ct, origin):
    """Land the economy passengers directly on ore, nearest our Core first.

    On duel Pantheon throws passengers three and four onto (1,11) and (4,10) --
    both ore tiles -- and each steps off and builds its harvester on the tile it
    just vacated. It takes them in order of distance from its own Core, not
    from the pad: (1,11) is farther from the pad and goes first.

    This is a correction to what the v16 replays seemed to say. Those looked
    like throws at "ore far enough out that a walking Builder would never reach
    it"; against the enemy Core they are near-home ore, and the ordering is
    plainly by distance from home.
    """
    if not hasattr(player, "atlas"):
        home, _ = unpack_core(ct.read_store(SLOT_OWN_CORE))
        player.atlas = identify_visible(ct, home) if home is not None else None
    if player.atlas is None:
        return None
    home, _ = unpack_core(ct.read_store(SLOT_OWN_CORE))
    if home is None:
        return None
    claimed = getattr(player, "ore_claimed", set())
    ores = sorted(player.atlas.ores,
                  key=lambda o: ((o[0] - home[0]) ** 2 + (o[1] - home[1]) ** 2,
                                 o))
    for ore in ores:
        if ore in claimed:
            continue
        tile = Position(*ore)
        try:
            if not ct.can_launch(origin, tile):
                continue
        except GameError:
            continue
        claimed.add(ore)
        player.ore_claimed = claimed
        return tile
    return None


def _walk_to_core(player, ct, enemy_core):
    """Walking distance from every tile to the enemy Core, over known walls."""
    cached = getattr(player, "walk_map", None)
    if cached is not None:
        return cached
    if not hasattr(player, "atlas"):
        home, _ = unpack_core(ct.read_store(SLOT_OWN_CORE))
        player.atlas = (identify_visible(ct, home) if home is not None
                        else None)
    walls = set(player.atlas.walls) if player.atlas is not None else set()
    w, h = ct.get_map_width(), ct.get_map_height()
    srcs = [(enemy_core[0] + a, enemy_core[1] + b) for a in (0, 1) for b in (0, 1)
            if 0 <= enemy_core[0] + a < w and 0 <= enemy_core[1] + b < h]
    dist = {s: 0 for s in srcs}
    queue = deque(srcs)
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if (0 <= n[0] < w and 0 <= n[1] < h and n not in dist
                    and n not in walls):
                dist[n] = dist[(x, y)] + 1
                queue.append(n)
    player.walk_map = dist
    return dist


def _opening_throw(player, ct):
    """Throw whoever is standing next to the pad, without waiting to be asked.

    Ragnarok's ferry is request-driven: a Builder writes a launch request into
    the store and the Launcher services it. Store writes only become visible
    the following round, so the earliest possible first throw is the round
    after the pad goes up -- and then one more for the Builder to notice it can
    ask. Pantheon throws on the very next round, r1 pad and r2 first passenger,
    in 116 of 116 v20 games. It cannot be asking; it just picks up whatever is
    adjacent.

    So during the opening the pad throws the lowest-id adjacent friendly
    Builder itself. Ids increase with spawn order, so this ferries them in the
    order they were built, which is the order the roles are assigned in.
    """
    if len(getattr(player, "thrown", set())) >= PANTHEON_FERRY_PASSENGERS:
        return False
    if ct.get_action_cooldown() != 0:
        return False
    packed = ct.read_store(SLOT_ENEMY_CORE)
    if packed == 0:
        return False
    enemy_core, _ = unpack_enemy(packed)
    here = ct.get_position()
    me = ct.get_team()
    thrown = getattr(player, "thrown", set())

    passenger = None
    for unit in sorted(ct.get_nearby_units(2)):
        try:
            if (unit in thrown or ct.get_team(unit) != me
                    or ct.get_entity_type(unit) != EntityType.BUILDER_BOT):
                continue
            where = ct.get_position(unit)
        except GameError:
            continue
        if where.distance_squared(here) <= 2:
            passenger = (unit, where)
            break
    if passenger is None:
        return False

    # Measured rule: land on the tile with the shortest *walk* to the enemy
    # Core -- 178 of 230 throws in the v20 games, against far fewer for
    # straight-line -- with ties going to the farthest tile from the pad (179
    # confirmations across both versions, no counterexample). Straight line is
    # not a safe stand-in: on duel it picks (8,5) over Pantheon's (7,5) because
    # it is nearer as the crow flies while the wall at (6,5) is in the way.
    if len(thrown) < PANTHEON_RAIDERS:
        walk = _walk_to_core(player, ct, enemy_core)
        best = None
        for tile in ct.get_nearby_tiles(LAUNCH_RANGE_SQ):
            if not ct.can_launch(passenger[1], tile):
                continue
            key = (walk.get(tuple(tile), 1 << 20), -tile.distance_squared(here),
                   tile.x, tile.y)
            if best is None or key < best[0]:
                best = (key, tile)
    else:
        best = _ore_landing(player, ct, passenger[1])
        if best is not None:
            best = (None, best)
    if best is None:
        return False
    ct.launch(passenger[1], best[1])
    thrown.add(passenger[0])
    player.thrown = thrown
    _retire_if_spent(player, ct)
    return True


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
