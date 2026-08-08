"""Launcher relay and active enemy-displacement screen."""

from fcode import Controller, EntityType, GameError, Position

from constants import (D8, DEBUG_LAUNCH, HOME_GUARD_RADIUS_SQ,
                       LAUNCHER_QUIET_ROUNDS, LAUNCH_RANGE_SQ,
                       LAUNCH_REQUEST_SLOTS, SLOT_OWN_CORE)

# Kind codes shared with the Builder's rejection decoder.
KIND_INDEX = {EntityType.GUNNER: 0, EntityType.SENTINEL: 1,
              EntityType.LAUNCHER: 2}
from utils import (LAUNCH_PICKUP_SQ, is_request, landing_tile,
                   pack_response, pad_owner, unpack_core, unpack_request)


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

    me = tuple(ct.get_position())
    pads = _friendly_pads(ct)
    served = False
    for slot in LAUNCH_REQUEST_SLOTS:
        value = ct.read_store(slot)
        if not is_request(value):
            continue
        passenger, index = unpack_request(value)
        landing = landing_tile(me, index)
        if landing is None:
            continue
        if passenger not in set(ct.get_nearby_units(LAUNCH_PICKUP_SQ)):
            continue
        if ct.get_team(passenger) != ct.get_team():
            continue
        # Exactly one pad answers: the lowest-id friendly Launcher whose pickup
        # radius covers the passenger. Both halves derive this the same way, so
        # the pad that decodes the landing offset is always the pad the Builder
        # encoded it against -- which is what stopped a second pad resolving the
        # same word to a different tile and refusing a throw nobody asked for.
        if pad_owner(pads, tuple(ct.get_position(passenger))) != me:
            continue
        _service(player, ct, slot, passenger, landing)
        served = True
        break
    if not served:
        _idle(player, ct)
    return


def _friendly_pads(ct):
    """Every friendly Launcher this pad can see, position -> entity id."""
    pads = {}
    for entity_id in ct.get_nearby_buildings():
        if (ct.get_team(entity_id) == ct.get_team()
                and ct.get_entity_type(entity_id) == EntityType.LAUNCHER):
            pads[tuple(ct.get_position(entity_id))] = entity_id
    pads[tuple(ct.get_position())] = ct.get_id()
    return pads


def _idle(player, ct):
    """Nothing to throw: retire eventually, unless guarding the Core."""
    if any(ct.get_team(unit) != ct.get_team()
           and ct.get_entity_type(unit) == EntityType.BUILDER_BOT
           for unit in ct.get_nearby_units()):
        player.quiet_rounds = 0
        return
    player.quiet_rounds += 1
    if player.quiet_rounds < LAUNCHER_QUIET_ROUNDS:
        return
    home, _ = unpack_core(ct.read_store(SLOT_OWN_CORE))
    if home is None or (ct.get_position().distance_squared(Position(*home))
                        > HOME_GUARD_RADIUS_SQ):
        ct.self_destruct()


def _service(player, ct, slot, passenger, landing):
    """Throw the passenger where it asked, or refuse and say why."""
    player.quiet_rounds = 0
    origin = ct.get_position(passenger)
    destination = Position(*landing)
    me = tuple(ct.get_position())
    if ct.can_launch(origin, destination) and landing not in _covered_tiles(ct):
        if DEBUG_LAUNCH:
            import sys as _s
            print(f"LSERV r={ct.get_current_round()} pad={ct.get_id()} "
                  f"passenger={passenger} from={tuple(origin)} to={landing}",
                  file=_s.stderr, flush=True)
        ct.launch(origin, destination)
        ct.write_store(slot, pack_response(me, passenger, True))
        return
    _refuse_with_intel(player, ct, slot, passenger, landing, destination)


def _refuse_with_intel(player, ct, slot, passenger, landing, destination):
    """Refuse, and hand back what this pad can see that the Builder cannot.

    The pad stands where the passenger wanted to land, so it routinely sees
    turrets the Builder has never had line of sight to. Two of them fit in the
    reply -- the one covering the requested tile first, since that is the one
    the Builder's next plan has to account for.

    Nothing is deduplicated here. The Builder's map is the single source of
    truth: re-reporting a turret it already knows is idempotent, while tracking
    what has been "told" meant a second refusal could come back empty and teach
    nothing, which is exactly how a Builder ended up asking for the same tile
    every four rounds for the rest of the game.
    """
    me = tuple(ct.get_position())
    entries = []
    for entity_id in ct.get_nearby_buildings():
        if ct.get_team(entity_id) == ct.get_team():
            continue
        kind = ct.get_entity_type(entity_id)
        if kind not in KIND_INDEX:
            continue
        position = ct.get_position(entity_id)
        try:
            facing = D8.index(ct.get_direction(entity_id))
        except (ValueError, GameError):
            facing = 0
        covers = False
        if kind in (EntityType.GUNNER, EntityType.SENTINEL):
            try:
                covers = any(tuple(t) == tuple(destination) for t in
                             ct.get_attackable_tiles_from(position, D8[facing],
                                                          kind))
            except GameError:
                covers = False
        entries.append((not covers,
                        position.distance_squared(destination),
                        tuple(position), facing, KIND_INDEX[kind]))
    entries.sort()
    chosen = [(pos, facing, kind) for _, _, pos, facing, kind in entries]
    ct.write_store(slot, pack_response(me, passenger, False, chosen))
    if DEBUG_LAUNCH:
        import sys as _s
        print(f"LREJ r={ct.get_current_round()} pad={ct.get_id()} "
              f"passenger={passenger} landing={landing} intel={chosen[:2]}",
              file=_s.stderr, flush=True)


def _covered_tiles(ct):
    """Every tile a visible enemy turret can shoot."""
    covered = set()
    for entity_id in ct.get_nearby_buildings():
        if ct.get_team(entity_id) == ct.get_team():
            continue
        kind = ct.get_entity_type(entity_id)
        if kind not in (EntityType.GUNNER, EntityType.SENTINEL):
            continue
        try:
            tiles = ct.get_attackable_tiles_from(
                ct.get_position(entity_id), ct.get_direction(entity_id), kind)
        except GameError:
            continue
        covered.update(tuple(tile) for tile in tiles)
    return covered


def _visible_enemy_launchers(ct):
    """Return positions of enemy Launchers visible to this ferry."""
    return [ct.get_position(entity_id) for entity_id in ct.get_nearby_buildings()
            if ct.get_team(entity_id) != ct.get_team()
            and ct.get_entity_type(entity_id) == EntityType.LAUNCHER]


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
