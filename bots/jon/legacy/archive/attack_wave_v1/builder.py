"""Focused opening economy: discover one ore, harvest it, connect it to Core."""

from __future__ import annotations

from typing import TYPE_CHECKING

from constants import (
    BUILDER_COUNT,
    ATTACKER_ROLES,
    CLAIM_LEASE_ROUNDS,
    DEFENDER_ROLES,
    DEFENSE_DEPOSIT_THRESHOLD,
    DIRECTIONS,
    SECTOR_COUNT,
    SECTOR_GRID_SIZE,
    SECTOR_MASK,
    SLOT_CORE_POSITION,
    SLOT_COVERAGE_START,
    SLOT_LATEST_ASSIGNMENT,
    SLOT_ENEMY_REPORT,
    SLOT_STRATEGY,
    SLOT_TARGET_CLAIM_START,
    STUCK_LIMIT,
)
from fcode import Controller, Direction, EntityType, Position
from utils import is_free_ore, on_map, pack_claim, pack_pos, unpack_claim, unpack_pos

if TYPE_CHECKING:
    from main import Player


CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def run(player: Player, ct: Controller) -> None:
    """Run the collector state machine; deliberately build no combat units."""
    _read_assignment(player, ct)
    if player.role is None:
        return

    if player.core_pos is None:
        player.core_pos = unpack_pos(ct.read_store(SLOT_CORE_POSITION))
    if player.core_pos is None:
        return

    _update_coverage(player, ct)
    _report_visible_enemy_core(player, ct)

    pos = ct.get_position()
    if player.last_pos == pos:
        player.stuck += 1
    else:
        player.stuck = 0
    player.last_pos = pos

    if player.phase == "explore" and _should_defend(player, ct):
        player.phase = "defense_seek"
        player.ore_target = None
        player.target = None

    if player.phase == "explore":
        _explore(player, ct)
    elif player.phase == "route":
        _route_to_core(player, ct)
    elif player.phase == "defense_seek":
        _seek_defense_anchor(player, ct)
    elif player.phase == "defense":
        _build_defense(player, ct)
    elif player.phase == "attack_scout":
        _attack_scout(player, ct)
    elif player.phase == "attack_build":
        _build_attack_cluster(player, ct)

    claim = player.ore_target if player.ore_target is not None else player.target
    if player.phase == "explore" and claim is not None:
        ct.write_store(
            SLOT_TARGET_CLAIM_START + player.role,
            pack_claim(claim, ct.get_current_round() + CLAIM_LEASE_ROUNDS),
        )
    else:
        ct.write_store(SLOT_TARGET_CLAIM_START + player.role, 0)


def _read_assignment(player: Player, ct: Controller) -> None:
    """Match this entity id to the role written by Core when it spawned us."""
    if player.role is not None:
        return
    assignment = ct.read_store(SLOT_LATEST_ASSIGNMENT)
    role = (assignment & 0x7) - 1
    if 0 <= role < BUILDER_COUNT and assignment >> 3 == ct.get_id():
        player.role = role
        claim = unpack_claim(
            ct.read_store(SLOT_TARGET_CLAIM_START + role), ct.get_current_round()
        )
        if claim is not None:
            if ct.is_in_vision(claim) and is_free_ore(ct, claim):
                player.ore_target = claim
            else:
                player.target = claim
                player.target_started_round = ct.get_current_round()
        if role in ATTACKER_ROLES:
            player.phase = "attack_scout"
            player.ore_target = None
            player.target = None


def _explore(player: Player, ct: Controller) -> None:
    """Reserve nearby ore, approach its Core-facing side, then harvest it."""
    if player.ore_target is not None and (
        not _target_is_available(ct, player.ore_target)
        or _reserved_by_lower_role(player, ct, player.ore_target)
    ):
        player.ore_target = None
        player.target = None

    if player.ore_target is None:
        visible = _unreserved_visible_ore(player, ct)
        if visible:
            visible.sort(key=lambda p: (ct.get_position().distance_squared(p), p.x, p.y))
            player.ore_target = visible[0]
            player.target = None

    if player.ore_target is None:
        _explore_sector(player, ct)
        return

    ore = player.ore_target
    staging = _core_facing_staging_tile(player, ct, ore)
    if staging is None:
        player.ore_target = None
        player.target = None
        return

    pos = ct.get_position()
    if pos != staging:
        _move_toward(player, ct, staging, allow_diagonal=True)
        return

    if ct.get_action_cooldown() == 0 and ct.can_build_harvester(ore):
        ct.build_harvester(ore)
        player.harvester_pos = ore
        player.phase = "route"
        player.target = None


def _target_is_available(ct: Controller, ore: Position) -> bool:
    if not on_map(ct, ore):
        return False
    if not ct.is_in_vision(ore):
        return True
    return is_free_ore(ct, ore)


def _reserved_by_lower_role(player: Player, ct: Controller, ore: Position) -> bool:
    """Resolve same-round discovery races after reservations become visible."""
    return any(
        unpack_claim(
            ct.read_store(SLOT_TARGET_CLAIM_START + role), ct.get_current_round()
        ) == ore
        for role in range(player.role)
    )


def _unreserved_visible_ore(player: Player, ct: Controller) -> list[Position]:
    reserved = {
        unpack_claim(
            ct.read_store(SLOT_TARGET_CLAIM_START + role), ct.get_current_round()
        )
        for role in range(BUILDER_COUNT)
        if role != player.role
    }
    return [
        tile
        for tile in ct.get_nearby_tiles()
        if tile not in reserved and is_free_ore(ct, tile)
    ]


def _core_facing_staging_tile(
    player: Player, ct: Controller, ore: Position
) -> Position | None:
    """Choose a cardinal neighbour so the first belt can accept ore."""
    candidates = [ore.add(d) for d in CARDINALS]
    candidates = [p for p in candidates if on_map(ct, p)]
    candidates.sort(key=lambda p: (p.distance_squared(player.core_pos), p.x, p.y))
    own_pos = ct.get_position()
    for tile in candidates:
        if tile == own_pos or (ct.is_in_vision(tile) and ct.is_tile_passable(tile)):
            return tile
    return None


def _explore_sector(player: Player, ct: Controller) -> None:
    """Move to the cheapest unvisited, unclaimed 5x5 map sector."""
    pos = ct.get_position()
    if player.target is not None and pos.distance_squared(player.target) <= 2:
        player.coverage_mask |= 1 << _sector_index(ct, player.target)
        player.target = None

    if (
        player.target is not None
        and ct.get_current_round() - player.target_started_round > 20
    ):
        # Treat an unreachable centre as explored enough and move on.
        player.coverage_mask |= 1 << _sector_index(ct, player.target)
        player.target = None

    if player.target is None:
        covered = player.coverage_mask
        for role in range(BUILDER_COUNT):
            covered |= ct.read_store(SLOT_COVERAGE_START + role) & SECTOR_MASK
        claimed = {
            unpack_claim(
                ct.read_store(SLOT_TARGET_CLAIM_START + role),
                ct.get_current_round(),
            )
            for role in range(BUILDER_COUNT)
            if role != player.role
        }
        candidates = [
            _sector_centre(ct, index)
            for index in range(SECTOR_COUNT)
            if not covered & (1 << index)
        ]
        if not candidates:
            # A completed sweep becomes a deterministic patrol instead of idle.
            index = (ct.get_current_round() // 12 + player.role * 7) % SECTOR_COUNT
            candidates = [_sector_centre(ct, index)]
        player.target = min(
            candidates,
            key=lambda target: (
                pos.distance_squared(target) + (1000 if target in claimed else 0),
                (_sector_index(ct, target) - player.role * 7) % SECTOR_COUNT,
            ),
        )
        player.target_started_round = ct.get_current_round()

    _move_toward(player, ct, player.target, allow_diagonal=True)


def _update_coverage(player: Player, ct: Controller) -> None:
    """Publish a single-writer 25-bit coverage map plus 7-bit deposit count."""
    centre = _sector_centre(ct, _sector_index(ct, ct.get_position()))
    if ct.get_position().distance_squared(centre) <= 2:
        player.coverage_mask |= 1 << _sector_index(ct, centre)
    value = player.coverage_mask | (min(player.deposits_built, 127) << 25)
    ct.write_store(SLOT_COVERAGE_START + player.role, value)


def _sector_index(ct: Controller, pos: Position) -> int:
    sx = min(SECTOR_GRID_SIZE - 1, pos.x * SECTOR_GRID_SIZE // ct.get_map_width())
    sy = min(SECTOR_GRID_SIZE - 1, pos.y * SECTOR_GRID_SIZE // ct.get_map_height())
    return sy * SECTOR_GRID_SIZE + sx


def _sector_centre(ct: Controller, index: int) -> Position:
    sx = index % SECTOR_GRID_SIZE
    sy = index // SECTOR_GRID_SIZE
    return Position(
        min(ct.get_map_width() - 1, (2 * sx + 1) * ct.get_map_width() // 10),
        min(ct.get_map_height() - 1, (2 * sy + 1) * ct.get_map_height() // 10),
    )


def _route_to_core(player: Player, ct: Controller) -> None:
    """Lay exactly one cardinal, contiguous conveyor segment per round."""
    if ct.get_action_cooldown() != 0 or ct.get_move_cooldown() != 0:
        return

    pos = ct.get_position()
    core_direction = _adjacent_core_direction(ct, pos)
    if core_direction is not None:
        if _ensure_conveyor(ct, pos, core_direction):
            player.deposits_built += 1
            if _should_defend(player, ct, include_current_deposit=True):
                player.phase = "defense"
                player.defense_anchor = pos
                player.defense_direction = core_direction
            else:
                player.phase = "explore"
            player.ore_target = None
            player.harvester_pos = None
            player.target = None
            player.route_seen.clear()
        return

    next_direction = _cardinal_step_toward_core(player, ct)
    if next_direction is None:
        return

    # Build on the bot's current tile, then walk onto the tile the belt points
    # at. This guarantees cardinal adjacency and matching output direction.
    if not _ensure_conveyor(ct, pos, next_direction):
        return
    if ct.can_move(next_direction):
        player.route_seen.add(pos)
        ct.move(next_direction)


def _team_deposit_count(ct: Controller) -> int:
    return sum(
        ct.read_store(SLOT_COVERAGE_START + role) >> 25
        for role in range(BUILDER_COUNT)
    )


def _should_defend(
    player: Player, ct: Controller, *, include_current_deposit: bool = False
) -> bool:
    deposits = _team_deposit_count(ct) + int(include_current_deposit)
    if deposits < DEFENSE_DEPOSIT_THRESHOLD:
        return False
    if player.role in DEFENDER_ROLES:
        return True
    return False


def _report_visible_enemy_core(player: Player, ct: Controller) -> None:
    for building_id in ct.get_nearby_buildings():
        if (
            ct.get_team(building_id) != ct.get_team()
            and ct.get_entity_type(building_id) == EntityType.CORE
        ):
            player.attack_core = ct.get_position(building_id)
            ct.write_store(
                SLOT_ENEMY_REPORT,
                pack_claim(player.attack_core, min(1023, ct.get_current_round() + 60)),
            )
            return


def _attack_scout(player: Player, ct: Controller) -> None:
    """Resolve map symmetry, stage near enemy ore, then build on phase signal."""
    reported = unpack_claim(ct.read_store(SLOT_ENEMY_REPORT), ct.get_current_round())
    if reported is not None:
        player.attack_core = reported

    if player.attack_core is None:
        candidates = _enemy_core_candidates(player, ct)
        candidate = candidates[player.attack_candidate % len(candidates)]
        if ct.is_in_vision(candidate):
            core_here = False
            building_id = ct.get_tile_building_id(candidate)
            if building_id is not None:
                core_here = (
                    ct.get_team(building_id) != ct.get_team()
                    and ct.get_entity_type(building_id) == EntityType.CORE
                )
            if core_here:
                player.attack_core = ct.get_position(building_id)
                ct.write_store(
                    SLOT_ENEMY_REPORT,
                    pack_claim(
                        player.attack_core,
                        min(1023, ct.get_current_round() + 60),
                    ),
                )
            else:
                player.attack_candidate = (player.attack_candidate + 1) % len(candidates)
                candidate = candidates[player.attack_candidate]
        if player.attack_core is None:
            player.target = candidate
            _move_toward(player, ct, candidate, allow_diagonal=True)
            return

    core = player.attack_core
    if player.attack_ore is None or (
        ct.is_in_vision(player.attack_ore)
        and not _usable_attack_ore(ct, player.attack_ore)
    ):
        player.attack_ore = None
    ore = [
        tile
        for tile in ct.get_nearby_tiles()
        if _usable_attack_ore(ct, tile)
        and _ore_can_attack_core(ct, tile, core)
    ]
    if ore:
        best_ore = min(
            ore,
            key=lambda tile: (
                tile.distance_squared(core),
                ct.get_position().distance_squared(tile),
            ),
        )
        if (
            player.attack_ore is None
            or best_ore.distance_squared(core)
            < player.attack_ore.distance_squared(core)
        ):
            player.attack_ore = best_ore

    if player.attack_ore is None:
        # Orbit different sides of the target until a usable ore deposit appears.
        offsets = (
            Direction.NORTH,
            Direction.EAST,
            Direction.SOUTH,
            Direction.WEST,
        )
        player.target = core.add(offsets[player.role % 4])
        _move_toward(player, ct, player.target, allow_diagonal=True)
        return

    staging = _attack_staging_tile(ct, player.attack_ore)
    if staging is None:
        player.attack_ore = None
        return
    if ct.get_position() != staging:
        player.target = staging
        _move_toward(player, ct, staging, allow_diagonal=True)
        return
    if ct.read_store(SLOT_STRATEGY) != 1:
        return
    existing = ct.get_tile_building_id(player.attack_ore)
    if existing is not None and ct.get_entity_type(existing) == EntityType.HARVESTER:
        player.phase = "attack_build"
        player.target = None
        return
    if ct.get_action_cooldown() == 0 and ct.can_build_harvester(player.attack_ore):
        ct.build_harvester(player.attack_ore)
        player.phase = "attack_build"
        player.target = None


def _usable_attack_ore(ct: Controller, tile: Position) -> bool:
    if is_free_ore(ct, tile):
        return True
    building_id = ct.get_tile_building_id(tile)
    return (
        building_id is not None
        and ct.get_entity_type(building_id) == EntityType.HARVESTER
    )


def _ore_can_attack_core(ct: Controller, ore: Position, core: Position) -> bool:
    targets = [
        Position(core.x + dx, core.y + dy)
        for dx in (0, 1)
        for dy in (0, 1)
        if on_map(ct, Position(core.x + dx, core.y + dy))
    ]
    for feed_direction in CARDINALS:
        turret = ore.add(feed_direction)
        if not on_map(ct, turret):
            continue
        for facing in DIRECTIONS:
            if facing == feed_direction:
                continue
            if any(_sentinel_pattern_hits(turret, facing, target) for target in targets):
                return True
    return False


def _sentinel_pattern_hits(
    turret: Position, facing: Direction, target: Position
) -> bool:
    if turret.distance_squared(target) > 32:
        return False
    cursor = turret
    while True:
        cursor = cursor.add(facing)
        if turret.distance_squared(cursor) > 32:
            return False
        if max(abs(cursor.x - target.x), abs(cursor.y - target.y)) <= 1:
            return True


def _enemy_core_candidates(player: Player, ct: Controller) -> list[Position]:
    core = player.core_pos
    reflected_x = ct.get_map_width() - 2 - core.x
    reflected_y = ct.get_map_height() - 2 - core.y
    values = (
        Position(reflected_x, core.y),
        Position(core.x, reflected_y),
        Position(reflected_x, reflected_y),
    )
    result: list[Position] = []
    for value in values:
        if value not in result and on_map(ct, value):
            result.append(value)
    return result


def _attack_staging_tile(ct: Controller, ore: Position) -> Position | None:
    pos = ct.get_position()
    candidates = [ore.add(direction) for direction in CARDINALS]
    candidates = [
        tile
        for tile in candidates
        if on_map(ct, tile)
        and ct.is_in_vision(tile)
        and (tile == pos or ct.is_tile_passable(tile))
    ]
    if not candidates:
        return None
    return min(candidates, key=pos.distance_squared)


def _build_attack_cluster(player: Player, ct: Controller) -> None:
    """Build supplied, Core-targeting gunners first; use sentinels for range."""
    ore = player.attack_ore
    core = player.attack_core
    if ore is None or core is None or ct.get_action_cooldown() != 0:
        return
    builder_pos = ct.get_position()
    target_tiles = _enemy_core_tiles(player, ct)
    if not target_tiles:
        player.phase = "attack_scout"
        return

    options = _attack_turret_options(ct, ore, target_tiles)
    for turret_type, turret_pos, facing in options:
        if turret_pos == builder_pos or builder_pos.distance_squared(turret_pos) > 2:
            continue
        if turret_type == EntityType.GUNNER:
            can_build = ct.can_build_gunner(turret_pos, facing)
        else:
            can_build = ct.can_build_sentinel(turret_pos, facing)
        if not can_build:
            continue
        if turret_type == EntityType.GUNNER:
            ct.build_gunner(turret_pos, facing)
        else:
            ct.build_sentinel(turret_pos, facing)
        player.attack_turrets_built += 1
        return

    # Reposition around the harvester if the firing tile is currently on the
    # far side of it and therefore outside this builder's action radius.
    staging_tiles = [ore.add(direction) for direction in CARDINALS]
    for staging in staging_tiles:
        if (
            not on_map(ct, staging)
            or staging == builder_pos
            or not ct.is_tile_passable(staging)
        ):
            continue
        if any(
            staging != turret_pos and staging.distance_squared(turret_pos) <= 2
            for _, turret_pos, _ in options
        ):
            _move_toward(player, ct, staging, allow_diagonal=True)
            return

    _try_heal_nearby(ct)


def _attack_turret_options(
    ct: Controller, ore: Position, target_tiles: list[Position]
) -> list[tuple[EntityType, Position, Direction]]:
    options: list[tuple[EntityType, Position, Direction]] = []
    for turret_type in (EntityType.GUNNER, EntityType.SENTINEL):
        for feed_direction in CARDINALS:
            turret_pos = ore.add(feed_direction)
            if (
                not on_map(ct, turret_pos)
                or not ct.is_in_vision(turret_pos)
                or ct.get_tile_building_id(turret_pos) is not None
            ):
                continue
            for facing in DIRECTIONS:
                if facing == feed_direction:
                    continue
                if any(
                    ct.can_fire_from(turret_pos, facing, turret_type, target)
                    for target in target_tiles
                ):
                    options.append((turret_type, turret_pos, facing))
                    break
    return options


def _enemy_core_tiles(player: Player, ct: Controller) -> list[Position]:
    core_ids = {
        building_id
        for building_id in ct.get_nearby_buildings()
        if ct.get_team(building_id) != ct.get_team()
        and ct.get_entity_type(building_id) == EntityType.CORE
    }
    if core_ids:
        return [
            tile
            for tile in ct.get_nearby_tiles()
            if ct.get_tile_building_id(tile) in core_ids
        ]
    if player.attack_core is None:
        return []
    anchor = player.attack_core
    return [
        Position(anchor.x + dx, anchor.y + dy)
        for dx in (0, 1)
        for dy in (0, 1)
        if on_map(ct, Position(anchor.x + dx, anchor.y + dy))
    ]


def _seek_defense_anchor(player: Player, ct: Controller) -> None:
    """Return to a supplied final conveyor beside Core."""
    pos = ct.get_position()
    candidates: list[tuple[int, Position, Direction]] = []
    for tile in ct.get_nearby_tiles():
        core_id = ct.get_tile_building_id(tile)
        if core_id is None or ct.get_entity_type(core_id) != EntityType.CORE:
            continue
        if ct.get_team(core_id) != ct.get_team():
            continue
        for direction in CARDINALS:
            anchor = tile.add(direction)
            if not on_map(ct, anchor) or not ct.is_in_vision(anchor):
                continue
            building_id = ct.get_tile_building_id(anchor)
            if building_id is None:
                continue
            if ct.get_team(building_id) != ct.get_team():
                continue
            if ct.get_entity_type(building_id) not in (
                EntityType.CONVEYOR,
                EntityType.SPLITTER,
            ):
                continue
            toward_core = direction.opposite()
            if ct.get_direction(building_id) == toward_core:
                sides = (
                    toward_core.rotate_left().rotate_left(),
                    toward_core.rotate_right().rotate_right(),
                )
                occupied = sum(
                    ct.get_tile_building_id(anchor.add(side)) is not None
                    for side in sides
                    if on_map(ct, anchor.add(side)) and ct.is_in_vision(anchor.add(side))
                )
                candidates.append((occupied, anchor, toward_core))

    if candidates:
        _, anchor, direction = min(
            candidates, key=lambda item: (item[0], pos.distance_squared(item[1]))
        )
        if pos == anchor:
            player.defense_anchor = anchor
            player.defense_direction = direction
            player.phase = "defense"
            return
        _move_toward(player, ct, anchor, allow_diagonal=True)
        return

    _move_toward(player, ct, player.core_pos, allow_diagonal=True)


def _build_defense(player: Player, ct: Controller) -> None:
    """Replace the last belt with a splitter and feed two lateral gunners."""
    anchor = player.defense_anchor
    direction = player.defense_direction
    if anchor is None or direction is None:
        player.phase = "defense_seek"
        return
    if ct.get_position() != anchor:
        _move_toward(player, ct, anchor, allow_diagonal=True)
        return
    if ct.get_action_cooldown() != 0:
        return

    building_id = ct.get_tile_building_id(anchor)
    if building_id is not None and ct.get_entity_type(building_id) == EntityType.CONVEYOR:
        if ct.can_destroy(anchor):
            ct.destroy(anchor)
        building_id = ct.get_tile_building_id(anchor)
    if building_id is None:
        if ct.can_build_splitter(anchor, direction):
            ct.build_splitter(anchor, direction)
        return
    if (
        ct.get_entity_type(building_id) != EntityType.SPLITTER
        or ct.get_direction(building_id) != direction
    ):
        player.phase = "defense_seek"
        player.defense_anchor = None
        return

    sides = (
        direction.rotate_left().rotate_left(),
        direction.rotate_right().rotate_right(),
    )
    while player.gunners_built < len(sides):
        feed_direction = sides[player.gunners_built]
        gunner_pos = anchor.add(feed_direction)
        if not on_map(ct, gunner_pos):
            player.gunners_built += 1
            continue
        existing = ct.get_tile_building_id(gunner_pos)
        if existing is not None:
            if ct.get_entity_type(existing) == EntityType.GUNNER:
                player.gunners_built += 1
                continue
            player.gunners_built += 1
            continue
        centre = Position(ct.get_map_width() // 2, ct.get_map_height() // 2)
        facing = gunner_pos.direction_to(centre)
        if facing == feed_direction:
            facing = facing.rotate_left()
        if ct.can_build_gunner(gunner_pos, facing):
            ct.build_gunner(gunner_pos, facing)
            player.gunners_built += 1
        return

    _try_heal_nearby(ct)


def _try_heal_nearby(ct: Controller) -> None:
    if ct.get_action_cooldown() != 0:
        return
    pos = ct.get_position()
    for direction in (*CARDINALS, Direction.CENTRE):
        tile = pos.add(direction)
        if on_map(ct, tile) and ct.can_heal(tile):
            ct.heal(tile)
            return


def _adjacent_core_direction(ct: Controller, pos: Position) -> Direction | None:
    for direction in CARDINALS:
        tile = pos.add(direction)
        if not on_map(ct, tile):
            continue
        building_id = ct.get_tile_building_id(tile)
        if building_id is not None and ct.get_entity_type(building_id) == EntityType.CORE:
            if ct.get_team(building_id) == ct.get_team():
                return direction
    return None


def _cardinal_step_toward_core(player: Player, ct: Controller) -> Direction | None:
    pos = ct.get_position()
    core = player.core_pos
    toward: list[Direction] = []
    if core.x < pos.x:
        toward.append(Direction.WEST)
    elif core.x > pos.x:
        toward.append(Direction.EAST)
    if core.y < pos.y:
        toward.append(Direction.NORTH)
    elif core.y > pos.y:
        toward.append(Direction.SOUTH)

    # Prefer the axis with more distance left, reducing total belt length.
    toward.sort(
        key=lambda d: abs(core.x - pos.x) if d in (Direction.EAST, Direction.WEST)
        else abs(core.y - pos.y),
        reverse=True,
    )
    fallback = [d for d in CARDINALS if d not in toward]
    for direction in toward + fallback:
        next_pos = pos.add(direction)
        if not on_map(ct, next_pos) or next_pos in player.route_seen:
            continue
        if ct.can_move(direction):
            return direction
    return None


def _ensure_conveyor(ct: Controller, pos: Position, direction: Direction) -> bool:
    building_id = ct.get_tile_building_id(pos)
    if building_id is not None:
        return (
            ct.get_entity_type(building_id) == EntityType.CONVEYOR
            and ct.get_direction(building_id) == direction
        )
    if ct.can_build_conveyor(pos, direction):
        ct.build_conveyor(pos, direction)
        return True
    return False


def _move_toward(
    player: Player, ct: Controller, target: Position, *, allow_diagonal: bool
) -> None:
    if ct.get_move_cooldown() != 0:
        return
    pos = ct.get_position()
    desired = pos.direction_to(target)
    candidates = [desired, desired.rotate_left(), desired.rotate_right()]
    candidates.extend(DIRECTIONS)
    for direction in candidates:
        if direction == Direction.CENTRE:
            continue
        if not allow_diagonal and not direction.is_cardinal():
            continue
        if ct.can_move(direction):
            ct.move(direction)
            return
