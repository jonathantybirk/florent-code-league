"""Map-agnostic online economy planner and explorer."""

from collections import deque
import os
import sys
from typing import TYPE_CHECKING

from fcode import Controller, EntityType, Environment, GameError, Position

from atlas import identify_visible
from constants import (
    CLAIM_SLOTS,
    D4_DELTAS,
    D8,
    ECONOMY_BUILDERS,
    FACING,
    LAUNCHER_BUILDER_INDEX,
    LAUNCH_DIRECTION_BITS,
    LAUNCH_REJECTION_FLAG,
    LAUNCH_REJECTION_POSITION_BITS,
    LAUNCH_REJECTION_POSITION_MASK,
    LAUNCH_REQUEST_SLOTS,
    SLOT_BUILDER_HEARTBEAT,
    SLOT_BUILDER_TICKET,
    SLOT_CONSTRUCTION_LOCK,
    SLOT_CORE_DAMAGED,
    SLOT_ENEMY_CORE,
    SLOT_OWN_CORE,
    SLOT_SYMMETRY_REJECT_START,
    WALKABLE_BUILDINGS,
)
from utils import pack_pos, unpack_pos

if TYPE_CHECKING:
    from main import Player


HARASS_PRIORITY = {EntityType.SPLITTER: 0, EntityType.CONVEYOR: 1}
GUNNER_RANGE_SQ = 13
PATH_FAILURES_BEFORE_LAUNCHER = 1
LAUNCH_REQUEST_ROUNDS = 4
BLOCKER_GUNNER_RETRY_ROUNDS = 4
RELAY_STOP_DISTANCE = 7


def run(p: "Player", ct: Controller) -> None:
    try:
        _run(p, ct)
    except GameError as error:
        if os.environ.get("JONBOT_DEBUG"):
            print("GameError", ct.get_current_round(), error, file=sys.stderr, flush=True)
        # An escaping GameError permanently destroys this unit.
        return


def _run(p, ct):
    # Store round + 1 so zero remains the unambiguous "no Builder seen" value.
    # All Builders publish the same value; the Core only needs proof that at
    # least one of them was alive during the preceding round.
    ct.write_store(SLOT_BUILDER_HEARTBEAT, ct.get_current_round() + 1)
    if not hasattr(p, "builder_index"):
        p.builder_index = ct.read_store(SLOT_BUILDER_TICKET)
        ct.write_store(SLOT_BUILDER_TICKET, p.builder_index + 1)
        p.w, p.h = ct.get_map_width(), ct.get_map_height()
        p.seen, p.terrain = set(), {}
        p.walls, p.ores, p.solids, p.conveyors = set(), set(), set(), {}
        p.bot_occupied, p.enemy_conveyors = set(), {}
        p.enemy_launchers, p.enemy_launcher_danger = set(), set()
        p.enemy_economy = {}
        p.core, p.foot = None, set()
        p.task, p.route, p.route_i, p.phase = None, [], 0, "scout"
        p.explored = set()
        p.rejected_symmetries = 0
        p.current_route_tiles = set()
        p.network_tiles = set()
        p.network_load = 0
        p.economy_lines_completed = 0
        p.is_launcher_builder = p.builder_index == LAUNCHER_BUILDER_INDEX
        p.is_attacker = (p.builder_index >= ECONOMY_BUILDERS
                         and not p.is_launcher_builder)
        p.lock_required = False
        p.home_gunners_built = 0
        p.attack_gunners_built = 0
        p.path_failures = 0
        p.awaiting_launch = 0
        p.launch_origin = None
        p.launch_blocked = False
        p.launch_blocking_launchers = set()
        p.launcher_breakers = set()
        p.next_blocker_gunner_round = 0
        own_core = unpack_pos(ct.read_store(SLOT_OWN_CORE))
        p.atlas = (identify_visible(ct, own_core) if own_core is not None
                   else None)
        if p.atlas is not None:
            atlas_tiles = {(x, y) for y in range(p.h) for x in range(p.w)}
            p.walls.update(p.atlas.walls)
            p.ores.update(p.atlas.ores)
            p.seen.update(atlas_tiles)
            p.terrain.update({tile: Environment.EMPTY for tile in atlas_tiles})
            p.terrain.update({tile: Environment.WALL for tile in p.atlas.walls})
            p.terrain.update({tile: Environment.ORE_TITANIUM
                              for tile in p.atlas.ores})
            ct.write_store(SLOT_ENEMY_CORE, pack_pos(p.atlas.enemy_core))
    _sense(p, ct)
    if p.atlas is None:
        _update_enemy_core_inference(p, ct)
    if p.core is None:
        return
    if p.builder_index == 0 and ct.read_store(SLOT_CORE_DAMAGED):
        _defend_core(p, ct)
        return
    if p.is_launcher_builder and not _run_launcher_wall(p, ct):
        return
    if p.is_attacker:
        p.phase = "rush"
    if p.phase == "rush":
        _rush(p, ct)
        return
    if p.network_load >= 4:
        p.phase = "harass"
    if p.phase == "harass":
        _harass(p, ct)
        return
    if p.phase == "scout":
        _pick(p, ct)
    if p.phase == "goto":
        _goto(p, ct)
    elif p.phase == "wait_lock":
        _wait_for_construction_lock(p, ct)
    elif p.phase == "prelay":
        if p.lock_required:
            _refresh_construction_lock(p, ct)
        _prelay(p, ct)
    elif p.phase == "lay":
        _lay(p, ct)
    else:
        _explore(p, ct)


def _sense(p, ct):
    for tile in ct.get_nearby_tiles():
        key = tuple(tile)
        p.seen.add(key)
        env = ct.get_tile_env(tile)
        p.terrain[key] = env
        if env == Environment.WALL:
            p.walls.add(key)
            p.enemy_launchers.discard(key)
            continue
        if env == Environment.ORE_TITANIUM:
            p.ores.add(key)
        bot_id = ct.get_tile_builder_bot_id(tile)
        if bot_id is not None and bot_id != ct.get_id():
            p.bot_occupied.add(key)
        else:
            p.bot_occupied.discard(key)
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            p.solids.discard(key)
            p.conveyors.pop(key, None)
            p.enemy_conveyors.pop(key, None)
            p.enemy_economy.pop(key, None)
            p.enemy_launchers.discard(key)
            continue
        kind = ct.get_entity_type(bid)
        enemy = ct.get_team(bid) != ct.get_team()
        if enemy and kind == EntityType.LAUNCHER:
            p.enemy_launchers.add(key)
        else:
            p.enemy_launchers.discard(key)
        if kind == EntityType.CORE and enemy:
            ct.write_store(SLOT_ENEMY_CORE, pack_pos(ct.get_position(bid)))
        if enemy and kind in HARASS_PRIORITY:
            p.enemy_economy[key] = kind
        else:
            p.enemy_economy.pop(key, None)
        if kind == EntityType.CORE:
            if ct.get_team(bid) == ct.get_team():
                p.core = tuple(ct.get_position(bid))
            p.solids.add(key)
        elif kind in WALKABLE_BUILDINGS:
            p.solids.discard(key)
            if ct.get_team(bid) == ct.get_team():
                p.conveyors[key] = ct.get_direction(bid)
                p.enemy_conveyors.pop(key, None)
            else:
                p.enemy_conveyors[key] = ct.get_direction(bid)
        else:
            p.solids.add(key)
    if p.core and not p.foot:
        x, y = p.core
        p.foot = {(x + dx, y + dy) for dx in (0, 1) for dy in (0, 1)}
    p.enemy_launcher_danger = {
        (launcher[0] + dx, launcher[1] + dy)
        for launcher in p.enemy_launchers
        for dx, dy in (direction.delta() for direction in D8)
        if _inside(p, (launcher[0] + dx, launcher[1] + dy))
    }
    p.launcher_breakers.intersection_update(p.enemy_launchers)
    if (p.launch_blocked and p.launch_blocking_launchers
            and not p.launch_blocking_launchers & p.enemy_launchers):
        p.launch_blocked = False
        p.launch_blocking_launchers.clear()


def _pick(p, ct):
    # A conveyor network carries one stack/round: exactly four Harvesters at
    # their 10-Ti-per-four-round cadence. Do not create silently idle deposits.
    if p.network_load >= 4:
        return
    claimed = {x for x in (unpack_pos(ct.read_store(s)) for s in CLAIM_SLOTS) if x}
    claimed |= p.ores & p.solids
    me, best = tuple(ct.get_position()), None
    candidates = sorted(
        p.ores - claimed,
        key=lambda ore: max(abs(ore[0] - me[0]), abs(ore[1] - me[1])),
    )
    for ore in candidates:
        route = _route(p, ore)
        travel = _distance(p, me, _adjacent(p, ore))
        if route is None or travel is None:
            continue
        # Nearest-first is robust under fog; route length breaks ties. The
        # offline planner supplies the upper bound for later score tuning.
        best = (travel, len(route), ore, route)
        break
    if best is None:
        return
    _, _, ore, route = best
    for slot in CLAIM_SLOTS:
        if ct.read_store(slot) == 0:
            ct.write_store(slot, pack_pos(ore))
            p.task, p.route = ore, route
            p.current_route_tiles.clear()
            if route:
                p.route_i = len(route) - 1
                # Only long routes justify serializing construction. Short
                # routes gain more from parallelism and rarely collide deeply.
                p.lock_required = len(route) >= 24
                p.phase = "wait_lock" if p.lock_required else "prelay"
            else:
                p.lock_required = False
                p.route_i, p.phase = 0, "goto"
            return


def _route(p, ore):
    """Shortest cardinal line to Core or this Builder's unsaturated network."""
    joinable = p.network_tiles if p.network_load < 4 else set()
    blocked = (p.walls | p.foot | (p.ores - {ore}) | p.solids
               | _launcher_hazards(p)
               | (set(p.conveyors) - joinable))
    prev, queue, goal = {ore: None}, deque([ore]), None
    while queue and goal is None:
        cur = queue.popleft()
        for dx, dy in D4_DELTAS:
            nxt = cur[0] + dx, cur[1] + dy
            if nxt in prev or not _inside(p, nxt):
                continue
            # An orthogonally adjacent Harvester feeds the Core directly.
            if nxt in p.foot:
                prev[nxt], goal = cur, nxt
                break
            if nxt in joinable:
                # A Conveyor accepts from every cardinal side except its own
                # output side; reject a head-on attempted join.
                direction = p.conveyors.get(nxt)
                if direction is not None:
                    receiver_output = (nxt[0] + direction.delta()[0],
                                       nxt[1] + direction.delta()[1])
                    if receiver_output != cur:
                        prev[nxt], goal = cur, nxt
                        break
            # Unknown terrain is not permission to spend. Builders scout until
            # an entire cardinal route is observed, then construct it.
            if nxt not in p.seen:
                continue
            if nxt in blocked:
                continue
            prev[nxt] = cur
            queue.append(nxt)
    if goal is None:
        return None
    path, cur = [], goal
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    tiles, result = path[1:-1], []
    for i, tile in enumerate(tiles):
        nxt = tiles[i + 1] if i + 1 < len(tiles) else path[-1]
        result.append((tile, FACING[(nxt[0] - tile[0], nxt[1] - tile[1])]))
    return result


def _goto(p, ct):
    me, target = ct.get_position(), Position(*p.task)
    if 0 < me.distance_squared(target) <= 2:
        if ct.can_build_harvester(target):
            ct.build_harvester(target)
            p.solids.add(p.task)
            p.economy_lines_completed += 1
            _done(p, ct)
        elif ct.get_tile_building_id(target) is not None:
            _done(p, ct)
        return
    _step(p, ct, target, False)


def _wait_for_construction_lock(p, ct):
    """Acquire a delayed-store lease before committing conveyor tiles."""
    owner, expires = _read_construction_lock(ct)
    me = p.builder_index + 1
    if owner == me:
        p.phase = "prelay"
        _refresh_construction_lock(p, ct)
        return
    if owner == 0 or expires < ct.get_current_round():
        ct.write_store(SLOT_CONSTRUCTION_LOCK,
                       me | ((ct.get_current_round() + 20) << 2))
    # Position at the Core/network end while the previous line finishes.
    if p.route:
        _step(p, ct, Position(*p.route[-1][0]), True)


def _read_construction_lock(ct):
    value = ct.read_store(SLOT_CONSTRUCTION_LOCK)
    return value & 0x3, value >> 2


def _refresh_construction_lock(p, ct):
    ct.write_store(SLOT_CONSTRUCTION_LOCK,
                   (p.builder_index + 1) | ((ct.get_current_round() + 20) << 2))


def _prelay(p, ct):
    """Build Core-to-ore so a Harvester is never committed without a line."""
    if p.route_i < 0:
        p.phase = "goto"
        return
    tile, facing = p.route[p.route_i]
    me, target = ct.get_position(), Position(*tile)
    if _cardinal_distance(tuple(me), tuple(target)) != 1:
        if tile in p.walls or tile in p.solids or (
            tile in p.conveyors and tile not in p.current_route_tiles
        ):
            _replace_route(p, outward=True)
            return
        _move_cardinal_adjacent(p, ct, tuple(target))
        return
    if ct.can_build_conveyor(target, facing):
        ct.build_conveyor(target, facing)
        p.conveyors[tile] = facing
        p.current_route_tiles.add(tile)
    else:
        building_id = ct.get_tile_building_id(target)
        compatible = (
            building_id is not None
            and tile in p.current_route_tiles
            and ct.get_team(building_id) == ct.get_team()
            and ct.get_entity_type(building_id) == EntityType.CONVEYOR
            and ct.get_direction(building_id) == facing
        )
        if not compatible:
            _replace_route(p, outward=True)
            return
    p.route_i -= 1
    if p.route_i >= 0:
        _step(p, ct, Position(*p.route[p.route_i][0]), True)
    else:
        p.phase = "goto"


def _lay(p, ct):
    if p.route_i >= len(p.route):
        _done(p, ct)
        return
    tile, facing = p.route[p.route_i]
    me, target = ct.get_position(), Position(*tile)
    if _cardinal_distance(tuple(me), tuple(target)) != 1:
        if tile in p.walls or tile in p.solids or (
            tile in p.conveyors and tile not in p.current_route_tiles
        ):
            _replace_route(p)
            return
        _move_cardinal_adjacent(p, ct, tuple(target))
        return
    if ct.can_build_conveyor(target, facing):
        ct.build_conveyor(target, facing)
        p.conveyors[tile] = facing
        p.current_route_tiles.add(tile)
    else:
        building_id = ct.get_tile_building_id(target)
        if building_id is None:
            return
        compatible = (
            tile in p.current_route_tiles
            and
            ct.get_team(building_id) == ct.get_team()
            and ct.get_entity_type(building_id) == EntityType.CONVEYOR
            and ct.get_direction(building_id) == facing
        )
        if not compatible:
            # The route was planned before this older line came into vision.
            # Never silently splice into a conflicting facing: recompute a
            # disjoint route with observed infrastructure blocked.
            _replace_route(p)
            return
    p.route_i += 1
    if p.route_i < len(p.route):
        _step(p, ct, Position(*p.route[p.route_i][0]), True)
    else:
        _done(p, ct)


def _replace_route(p, outward=False):
    """Replan after fog or another Builder invalidates the current line."""
    replacement = _route(p, p.task)
    if replacement is not None and replacement != p.route[p.route_i:]:
        p.route = replacement
        p.route_i = len(replacement) - 1 if outward else 0


def _done(p, ct):
    if p.task and p.current_route_tiles:
        p.network_tiles.update(p.current_route_tiles)
        p.network_load += 1
        p.current_route_tiles.clear()
    owner, _ = _read_construction_lock(ct)
    if owner == p.builder_index + 1:
        ct.write_store(SLOT_CONSTRUCTION_LOCK, 0)
    if p.task:
        value = pack_pos(p.task)
        for slot in CLAIM_SLOTS:
            if ct.read_store(slot) == value:
                ct.write_store(slot, 0)
                break
    p.task, p.route, p.route_i, p.phase = None, [], 0, "scout"
    p.lock_required = False
    p.path_failures = 0


def _step(p, ct, target, exact, allow_launcher=True):
    source = ct.get_position()
    launch_rejected = _consume_launch_rejection(p, ct)
    if p.awaiting_launch:
        if tuple(source) != p.launch_origin:
            # The Launcher moved us. Resume the original task immediately.
            p.awaiting_launch = 0
            p.launch_origin = None
            p.path_failures = 0
        else:
            adjacent = _adjacent_visible_launcher(ct, target)
            if adjacent is not None:
                _announce_launch(p, ct, target, adjacent[1])
                p.awaiting_launch -= 1
                return True
            # The requested Launcher disappeared before servicing us.
            p.awaiting_launch = 0
            p.launch_origin = None

    nxt = _bfs_step(p, tuple(source), tuple(target), exact)
    if nxt:
        # Cardinal only: a diagonal is not a legal Builder move in 2.3.3, and
        # this loop silently did nothing whenever the path asked for one.
        for direction in D8:
            if source.add(direction) == Position(*nxt) and ct.can_move(direction):
                ct.move(direction)
                p.path_failures = 0
                return True

    goals = {tuple(target)} if exact else _adjacent(p, tuple(target))
    if tuple(source) in goals:
        p.path_failures = 0
        return False

    p.path_failures += 1
    if (allow_launcher and not launch_rejected and not p.launch_blocked
            and p.path_failures >= PATH_FAILURES_BEFORE_LAUNCHER
            and _build_escape_launcher(p, ct, target)):
        return True
    if _build_blocker_gunner(p, ct, target):
        return True
    return _move_while_stuck(p, ct, target)


def _build_escape_launcher(p, ct, target):
    """Build a temporary ferry after repeated failures to find a walkable path."""
    launchers = _visible_friendly_launchers(ct)
    if launchers:
        adjacent = _adjacent_visible_launcher(ct, target, launchers)
        if adjacent is None:
            return False
        p.awaiting_launch = LAUNCH_REQUEST_ROUNDS
        p.launch_origin = tuple(ct.get_position())
        _announce_launch(p, ct, target, adjacent[1])
        return True

    if ct.get_global_resources() < ct.get_launcher_cost():
        return False

    here = tuple(ct.get_position())
    candidates = []
    for dx, dy in D4_DELTAS:
        spot = here[0] + dx, here[1] + dy
        position = Position(*spot)
        if (_inside(p, spot) and spot not in p.walls and spot not in p.solids
                and spot not in _launcher_hazards(p)
                and spot not in p.ores and ct.can_build_launcher(position)):
            candidates.append((position.distance_squared(target), spot, position))
    if not candidates:
        return False

    _, spot, position = min(candidates)
    ct.build_launcher(position)
    p.solids.add(spot)
    p.path_failures = 0
    p.awaiting_launch = LAUNCH_REQUEST_ROUNDS
    p.launch_origin = here
    _announce_launch(p, ct, target, position)
    return True


def _build_blocker_gunner(p, ct, target):
    """Build an immediately aligned Gunner against a visible path blocker."""
    if ct.get_current_round() < p.next_blocker_gunner_round:
        return False

    here = ct.get_position()
    enemies = [entity_id for entity_id in ct.get_nearby_entities()
               if ct.get_team(entity_id) != ct.get_team()]
    if not enemies:
        return False

    source, destination = tuple(here), tuple(target)
    target_dx = destination[0] - source[0]
    target_dy = destination[1] - source[1]
    unit_priority = {
        EntityType.BUILDER_BOT: 0,
        EntityType.LAUNCHER: 1,
        EntityType.GUNNER: 2,
        EntityType.SENTINEL: 3,
    }
    candidates = []
    for dx, dy in D4_DELTAS:
        spot = source[0] + dx, source[1] + dy
        position = Position(*spot)
        if (not _inside(p, spot) or spot in p.foot or spot in p.walls
                or spot in p.ores or spot in p.solids):
            continue
        for enemy_id in enemies:
            enemy = ct.get_position(enemy_id)
            facing = _ray_direction(spot, tuple(enemy))
            if (facing is None
                    or position.distance_squared(enemy) > GUNNER_RANGE_SQ
                    or not ct.can_build_gunner(position, facing)):
                continue
            enemy_dx = enemy.x - source[0]
            enemy_dy = enemy.y - source[1]
            ahead = enemy_dx * target_dx + enemy_dy * target_dy > 0
            deviation = abs(enemy_dx * target_dy - enemy_dy * target_dx)
            candidates.append((
                not ahead,
                deviation,
                unit_priority.get(ct.get_entity_type(enemy_id), 4),
                here.distance_squared(enemy),
                position.distance_squared(target),
                position.x,
                position.y,
                position,
                facing,
            ))
    if not candidates:
        return False

    *_, position, facing = min(candidates)
    ct.build_gunner(position, facing)
    p.solids.add(tuple(position))
    p.next_blocker_gunner_round = (
        ct.get_current_round() + BLOCKER_GUNNER_RETRY_ROUNDS
    )
    return True


def _visible_friendly_launchers(ct):
    """Return visible friendly Launcher ids and positions."""
    result = []
    for entity_id in ct.get_nearby_buildings():
        if (ct.get_team(entity_id) == ct.get_team()
                and ct.get_entity_type(entity_id) == EntityType.LAUNCHER):
            result.append((entity_id, ct.get_position(entity_id)))
    return result


def _adjacent_visible_launcher(ct, target, launchers=None):
    """Pick the adjacent Launcher furthest forward toward target."""
    here = ct.get_position()
    if launchers is None:
        launchers = _visible_friendly_launchers(ct)
    adjacent = [launcher for launcher in launchers
                if here.distance_squared(launcher[1]) <= 2]
    if not adjacent:
        return None
    return min(adjacent, key=lambda launcher: (
        launcher[1].distance_squared(target), launcher[1].x, launcher[1].y,
    ))


def _announce_launch(p, ct, target, launcher_position):
    """Publish this passenger and the launcher's requested compass direction."""
    dx = _sign(target.x - launcher_position.x)
    dy = _sign(target.y - launcher_position.y)
    direction_index = next(
        index for index, direction in enumerate(D8, start=1)
        if direction.delta() == (dx, dy)
    )
    slot = LAUNCH_REQUEST_SLOTS[p.builder_index % len(LAUNCH_REQUEST_SLOTS)]
    request = (ct.get_id() << LAUNCH_DIRECTION_BITS) | direction_index
    ct.write_store(slot, request)


def _consume_launch_rejection(p, ct):
    """Consume a rejection and remember the Launcher blocking safe landings."""
    slot = LAUNCH_REQUEST_SLOTS[p.builder_index % len(LAUNCH_REQUEST_SLOTS)]
    value = ct.read_store(slot)
    if not value & LAUNCH_REJECTION_FLAG:
        return False
    payload = value & (LAUNCH_REJECTION_FLAG - 1)
    passenger = payload >> LAUNCH_REJECTION_POSITION_BITS
    if passenger != ct.get_id():
        return False
    blocker = unpack_pos(payload & LAUNCH_REJECTION_POSITION_MASK)
    if blocker is not None:
        p.enemy_launchers.add(blocker)
        p.solids.add(blocker)
        p.enemy_launcher_danger.update(
            (blocker[0] + dx, blocker[1] + dy)
            for dx, dy in (direction.delta() for direction in D8)
            if _inside(p, (blocker[0] + dx, blocker[1] + dy))
        )
    ct.write_store(slot, 0)
    p.awaiting_launch = 0
    p.launch_origin = None
    p.launch_blocked = True
    p.launch_blocking_launchers = set(p.enemy_launchers)
    return True


def _sign(value):
    return (value > 0) - (value < 0)


def _move_while_stuck(p, ct, target):
    """Explore locally while waiting until a useful Launcher is affordable."""
    source = ct.get_position()
    candidates = []
    for direction in FACING.values():
        position = source.add(direction)
        if (tuple(position) not in _launcher_hazards(p)
                and ct.can_move(direction)):
            candidates.append((
                tuple(position) in p.seen,
                position.distance_squared(target),
                position.x,
                position.y,
                direction,
            ))
    if not candidates:
        return False
    *_, direction = min(candidates)
    ct.move(direction)
    return True


def _bfs_step(p, source, target, exact):
    goals = {target} if exact else _adjacent(p, target)
    if source in goals:
        return None
    blocked = (p.walls | p.foot | p.solids | (p.bot_occupied - {source})
               | (_launcher_hazards(p) - {source}))
    prev, queue = {source: None}, deque([source])
    found = None
    while queue:
        cur = queue.popleft()
        if cur in goals:
            found = cur
            break
        for dx, dy in D4_DELTAS:
            nxt = cur[0] + dx, cur[1] + dy
            if nxt in prev or not _inside(p, nxt) or nxt in blocked:
                continue
            prev[nxt] = cur
            queue.append(nxt)
    if found is None:
        return None
    while prev[found] != source:
        found = prev[found]
    return found


def _distance(p, source, goals):
    if source in goals:
        return 0
    blocked = (p.walls | p.foot | p.solids | (p.bot_occupied - {source})
               | (_launcher_hazards(p) - {source}))
    dist, queue = {source: 0}, deque([source])
    while queue:
        cur = queue.popleft()
        for dx, dy in D4_DELTAS:
            nxt = cur[0] + dx, cur[1] + dy
            if nxt in dist or not _inside(p, nxt) or nxt in blocked:
                continue
            dist[nxt] = dist[cur] + 1
            if nxt in goals:
                return dist[nxt]
            queue.append(nxt)
    return None


def _explore(p, ct):
    me, stride = tuple(ct.get_position()), 4

    # First resolve the enemy-Core hypotheses. This is map-agnostic: targets
    # come only from dimensions, our observed Core, and rejected symmetries.
    info_target = _enemy_scout_target(p, ct)
    if info_target is not None:
        _step(p, ct, Position(*info_target), False)
        return

    choices = [(x, y) for y in range(1, p.h, stride) for x in range(1, p.w, stride)
               if (x, y) not in p.explored and (x, y) not in p.walls
               and (x, y) not in p.solids
               and (x, y) not in _launcher_hazards(p)
               and (x // stride + y // stride) % 3 == p.builder_index % 3]
    if not choices:
        p.explored.clear()
        corners = ((0, 0), (p.w - 1, 0), (0, p.h - 1), (p.w - 1, p.h - 1))
        target = max(corners, key=lambda q: (
            max(abs(q[0] - me[0]), abs(q[1] - me[1])), q
        ))
        _step(p, ct, Position(*target), False)
        return
    target = min(choices, key=lambda q: max(abs(q[0] - me[0]), abs(q[1] - me[1])))
    # A Builder already observes radius^2 20; don't idle walking to the exact
    # centre of an area that is fully visible.
    if (target[0] - me[0]) ** 2 + (target[1] - me[1]) ** 2 <= 20:
        p.explored.add(target)
        _explore(p, ct)
        return
    _step(p, ct, Position(*target), False)


def _harass(p, ct):
    """Scout for the enemy economy and sabotage high-value logistics.

    The opening harasser deliberately ignores the Core and combat buildings.
    Builder attacks are too slow and expensive for a Core kill, while damaging
    logistics immediately denies income and forces an opposing Builder home.
    """
    me = tuple(ct.get_position())
    targets = sorted(
        p.enemy_economy,
        key=lambda tile: (
            HARASS_PRIORITY[p.enemy_economy[tile]],
            max(abs(tile[0] - me[0]), abs(tile[1] - me[1])),
            tile,
        ),
    )
    # 2.3.3 inverted the attack rule: a Builder damages an orthogonally
    # adjacent tile and never the one it stands on, so stand *beside* the
    # target rather than on it.
    for target in targets:
        if ct.can_fire(Position(*target)):
            ct.fire(Position(*target))
            return

    if targets:
        _step(p, ct, Position(*targets[0]), False)
        return

    # No remembered economy is reachable yet. Resolve the enemy-Core location
    # and continue normal partitioned exploration; infrastructure discovered on
    # the way is recorded by _sense and attacked on the following round.
    _explore(p, ct)


def _heal_core(p, ct):
    """Return the economy Builder to repair a Core under active fire."""
    for tile in sorted(p.foot):
        position = Position(*tile)
        if ct.can_heal(position):
            ct.heal(position)
            return
    _step(p, ct, Position(*p.core), False)


def _run_launcher_wall(p, ct):
    """Build the Launcher screen, returning true when economy work can resume."""
    packed = ct.read_store(SLOT_ENEMY_CORE)
    if packed == 0:
        _explore(p, ct)
        return False
    enemy_core = unpack_pos(packed)
    if not hasattr(p, "launcher_wall_targets"):
        p.launcher_wall_targets = _launcher_wall_targets(p, enemy_core)
        p.launcher_wall_done = set()

    for target in p.launcher_wall_targets:
        key = tuple(target)
        if key in p.launcher_wall_done:
            continue
        if ct.is_in_vision(target):
            building_id = ct.get_tile_building_id(target)
            if building_id is not None:
                p.launcher_wall_done.add(key)
                continue
        here = ct.get_position()
        if _cardinal_distance(tuple(here), key) != 1:
            _move_cardinal_adjacent(p, ct, key)
            return False
        if (ct.get_global_resources() >= ct.get_launcher_cost()
                and ct.can_build_launcher(target)):
            ct.build_launcher(target)
            p.solids.add(key)
            p.launcher_wall_done.add(key)
        return False
    return True


def _launcher_wall_targets(p, enemy_core):
    """Return center-first sites with two intervening tiles per Launcher."""
    core_x, core_y = p.core
    delta_x = enemy_core[0] - core_x
    delta_y = enemy_core[1] - core_y
    targets = []
    if abs(delta_x) >= abs(delta_y):
        line_x = core_x + (4 if delta_x >= 0 else -3)
        line_x = min(max(line_x, 0), p.w - 1)
        coordinates = list(range(1, p.h, 3))
        center = core_y + 1
        sites = [(line_x, coordinate) for coordinate in coordinates]
        sites.sort(key=lambda site: (abs(site[1] - center), site[1]))
    else:
        line_y = core_y + (4 if delta_y >= 0 else -3)
        line_y = min(max(line_y, 0), p.h - 1)
        coordinates = list(range(1, p.w, 3))
        center = core_x + 1
        sites = [(coordinate, line_y) for coordinate in coordinates]
        sites.sort(key=lambda site: (abs(site[0] - center), site[0]))

    for site in sites:
        if site not in p.walls and site not in p.ores and site not in p.foot:
            targets.append(Position(*site))
    return targets


def _defend_core(p, ct):
    """Answer a visible Core attack with an ordinary counter-firing Gunner.

    This deliberately has no opening layout or inferred firing position: the
    economy Builder must first see both the damage and a target it can align
    with from a locally buildable tile.  Otherwise it falls back to repairs.
    """
    me = ct.get_position()
    enemies = [entity_id for entity_id in ct.get_nearby_entities()
               if ct.get_team(entity_id) != ct.get_team()]
    combat_priority = {
        EntityType.GUNNER: 0,
        EntityType.SENTINEL: 1,
        EntityType.BUILDER_BOT: 2,
        EntityType.LAUNCHER: 3,
    }
    enemies.sort(key=lambda entity_id: (
        combat_priority.get(ct.get_entity_type(entity_id), 4),
        ct.get_position(entity_id).distance_squared(Position(*p.core)),
        entity_id,
    ))
    # Escalate slowly with sustained damage rather than committing a fixed
    # defensive formation before Jonbot knows whether one is needed.
    core_position = Position(*p.core)
    core_id = (ct.get_tile_building_id(core_position)
               if ct.is_in_vision(core_position) else None)
    damage = (ct.get_max_hp(core_id) - ct.get_hp(core_id)) if core_id else 0
    desired = min(4, 1 + damage // 180)
    if p.home_gunners_built < desired:
        candidates = []
        for direction in D8:
            position = me.add(direction)
            if not _inside(p, tuple(position)) or tuple(position) in p.foot:
                continue
            for enemy_id in enemies:
                target = ct.get_position(enemy_id)
                facing = _ray_direction(tuple(position), tuple(target))
                if (facing is not None
                        and position.distance_squared(target) <= GUNNER_RANGE_SQ
                        and ct.can_build_gunner(position, facing)):
                    candidates.append((
                        combat_priority.get(ct.get_entity_type(enemy_id), 4),
                        position.distance_squared(target),
                        position.x, position.y, D8.index(facing), position, facing,
                    ))
        if candidates:
            *_, position, facing = min(candidates)
            ct.build_gunner(position, facing)
            p.home_gunners_built += 1
            return
    _heal_core(p, ct)


def _rush(p, ct):
    """Walk in and build a small, conventional direct-fire attack."""
    packed = ct.read_store(SLOT_ENEMY_CORE)
    if packed == 0:
        _explore(p, ct)
        return
    enemy_core = unpack_pos(packed)
    if _opening_ferry(p, ct, enemy_core):
        return
    if p.attack_gunners_built < 5 and _build_basic_gunner(p, ct, enemy_core):
        return
    _harass(p, ct)


def _opening_ferry(p, ct, enemy_core):
    """Relay every attacker toward a sufficiently distant enemy Core."""
    if p.atlas is None:
        return False

    if _consume_launch_rejection(p, ct) or p.launch_blocked:
        return False

    here = tuple(ct.get_position())
    if (_chebyshev(p.core, enemy_core) <= RELAY_STOP_DISTANCE
            or _chebyshev(here, enemy_core) <= RELAY_STOP_DISTANCE):
        p.awaiting_launch = 0
        p.launch_origin = None
        return False

    target = Position(*enemy_core)
    launchers = _visible_friendly_launchers(ct)
    adjacent = _adjacent_visible_launcher(ct, target, launchers)
    if adjacent is not None:
        p.awaiting_launch = LAUNCH_REQUEST_ROUNDS
        p.launch_origin = here
        _announce_launch(p, ct, target, adjacent[1])
        return True

    if launchers:
        # Reuse a forward Launcher. If only the previous relay remains behind
        # us, keep walking toward the Core until it leaves vision; never build
        # a duplicate while any friendly Launcher is visible.
        current_distance = Position(*here).distance_squared(target)
        forward = [launcher for launcher in launchers
                   if launcher[1].distance_squared(target) < current_distance]
        destination = (min(forward, key=lambda launcher: (
            launcher[1].distance_squared(target), launcher[1].x, launcher[1].y,
        ))[1] if forward else target)
        _step(p, ct, destination, False, allow_launcher=False)
        return True

    return _build_escape_launcher(p, ct, target)


def _chebyshev(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _build_basic_gunner(p, ct, enemy_core):
    """Build on the nearest visible legal ray, without a special formation."""
    core_tiles = {(enemy_core[0] + dx, enemy_core[1] + dy)
                  for dx in (0, 1) for dy in (0, 1)}
    me = tuple(ct.get_position())
    choices = []
    for core_tile in sorted(core_tiles):
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                spot = core_tile[0] + dx, core_tile[1] + dy
                if (not _inside(p, spot) or spot in core_tiles
                        or spot in p.walls or spot in p.ores or spot in p.solids):
                    continue
                facing = _ray_direction(spot, core_tile)
                if (facing is None
                        or _distance_sq(spot, core_tile) > GUNNER_RANGE_SQ
                        or not ct.can_fire_from(
                            Position(*spot), facing, EntityType.GUNNER,
                            Position(*core_tile),
                        )):
                    continue
                goals = (_cardinal_adjacent(p, spot) - p.walls - p.solids
                         - _launcher_hazards(p))
                distance = _distance(p, me, goals)
                if distance is not None:
                    choices.append((distance, spot, D8.index(facing), facing))
    if not choices:
        if _build_launcher_breaker_gunner(p, ct):
            return True
        _explore(p, ct)
        return True
    _, spot, _, facing = min(choices)
    position = Position(*spot)
    if not ct.is_in_vision(position):
        _step(p, ct, position, False)
        return True
    if _cardinal_distance(me, spot) != 1:
        _move_cardinal_adjacent(p, ct, spot)
        return True
    if ct.can_build_gunner(position, facing):
        ct.build_gunner(position, facing)
        p.solids.add(spot)
        p.attack_gunners_built += 1
    return True


def _build_launcher_breaker_gunner(p, ct):
    """Reach a safe build tile and place a Gunner aimed at a blocking Launcher."""
    me = tuple(ct.get_position())
    choices = []
    for launcher_position in sorted(p.enemy_launchers):
        if launcher_position in p.launcher_breakers:
            continue
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                spot = launcher_position[0] + dx, launcher_position[1] + dy
                if (not _inside(p, spot) or spot in p.foot or spot in p.walls
                        or spot in p.ores or spot in p.solids):
                    continue
                facing = _ray_direction(spot, launcher_position)
                if (facing is None
                        or _distance_sq(spot, launcher_position) > GUNNER_RANGE_SQ
                        or not ct.can_fire_from(
                            Position(*spot), facing, EntityType.GUNNER,
                            Position(*launcher_position),
                        )):
                    continue
                goals = (_cardinal_adjacent(p, spot) - p.walls - p.solids
                         - p.bot_occupied - _launcher_hazards(p))
                distance = _distance(p, me, goals)
                if distance is not None:
                    choices.append((
                        distance,
                        _distance_sq(spot, launcher_position),
                        launcher_position,
                        spot,
                        D8.index(facing),
                        facing,
                    ))
    if not choices:
        return False

    _, _, launcher_position, spot, _, facing = min(choices)
    position = Position(*spot)
    if _cardinal_distance(me, spot) != 1:
        _move_cardinal_adjacent(p, ct, spot)
        return True
    if ct.can_build_gunner(position, facing):
        ct.build_gunner(position, facing)
        p.solids.add(spot)
        p.attack_gunners_built += 1
        p.launcher_breakers.add(launcher_position)
    return True


def _ray_direction(source, target):
    dx, dy = target[0] - source[0], target[1] - source[1]
    if not (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
        return None
    step = (0 if dx == 0 else (1 if dx > 0 else -1),
            0 if dy == 0 else (1 if dy > 0 else -1))
    return next((direction for direction in D8 if direction.delta() == step), None)


def _distance_sq(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _enemy_core_candidates(p):
    """Candidate top-left Core coordinates: rotation, x mirror, y mirror."""
    x, y = p.core
    return (
        (p.w - 2 - x, p.h - 2 - y),
        (p.w - 2 - x, y),
        (x, p.h - 2 - y),
    )


def _transform(p, tile, index):
    x, y = tile
    if index == 0:
        return p.w - 1 - x, p.h - 1 - y
    if index == 1:
        return p.w - 1 - x, y
    return x, p.h - 1 - y


def _update_enemy_core_inference(p, ct):
    """Reject symmetry hypotheses using only this Builder's observations."""
    rejected = p.rejected_symmetries | _team_rejected_symmetries(ct)
    candidates = _enemy_core_candidates(p)
    for index, candidate in enumerate(candidates):
        if rejected & (1 << index):
            continue
        # Seeing the predicted footprint without an enemy Core disproves it.
        footprint = {(candidate[0] + dx, candidate[1] + dy)
                     for dx in (0, 1) for dy in (0, 1)}
        if all(_inside(p, tile) and ct.is_in_vision(Position(*tile))
               for tile in footprint):
            found = False
            for tile in footprint:
                bid = ct.get_tile_building_id(Position(*tile))
                if (bid is not None and ct.get_team(bid) != ct.get_team()
                        and ct.get_entity_type(bid) == EntityType.CORE):
                    ct.write_store(SLOT_ENEMY_CORE, pack_pos(ct.get_position(bid)))
                    found = True
                    break
            if not found:
                rejected |= 1 << index
                continue
        # A terrain mismatch between two observed paired cells disproves it.
        for tile, env in p.terrain.items():
            paired = _transform(p, tile, index)
            if paired in p.terrain and p.terrain[paired] != env:
                rejected |= 1 << index
                break
    p.rejected_symmetries = rejected
    ct.write_store(SLOT_SYMMETRY_REJECT_START + min(p.builder_index, 1), rejected)

    surviving = {candidate for i, candidate in enumerate(candidates)
                 if not rejected & (1 << i)}
    if len(surviving) == 1 and ct.read_store(SLOT_ENEMY_CORE) == 0:
        ct.write_store(SLOT_ENEMY_CORE, pack_pos(next(iter(surviving))))


def _enemy_scout_target(p, ct):
    """Assign unresolved candidate footprints across the two Builders."""
    if ct.read_store(SLOT_ENEMY_CORE):
        return None
    rejected = p.rejected_symmetries | _team_rejected_symmetries(ct)
    candidates = []
    for index, candidate in enumerate(_enemy_core_candidates(p)):
        if not rejected & (1 << index) and candidate not in candidates:
            candidates.append(candidate)
    if not candidates:
        return None
    # Different builder ids investigate different candidates; after a rejection
    # the modulo assignment automatically closes ranks next round.
    assignment = (p.builder_index - ECONOMY_BUILDERS
                  if p.is_attacker else p.builder_index)
    return candidates[assignment % len(candidates)]


def _team_rejected_symmetries(ct):
    return ((ct.read_store(SLOT_SYMMETRY_REJECT_START)
             | ct.read_store(SLOT_SYMMETRY_REJECT_START + 1)) & 0x7)


def _adjacent(p, target):
    return {(target[0] + d.delta()[0], target[1] + d.delta()[1]) for d in D8
            if _inside(p, (target[0] + d.delta()[0], target[1] + d.delta()[1]))}


def _cardinal_adjacent(p, target):
    return {(target[0] + dx, target[1] + dy) for dx, dy in D4_DELTAS
            if _inside(p, (target[0] + dx, target[1] + dy))}


def _cardinal_distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _move_cardinal_adjacent(p, ct, target):
    me = tuple(ct.get_position())
    goals = (_cardinal_adjacent(p, target) - p.walls - p.solids
             - p.bot_occupied - _launcher_hazards(p))
    reachable = [(distance, goal) for goal in goals
                 if (distance := _distance(p, me, {goal})) is not None]
    if reachable:
        _, goal = min(reachable)
        _step(p, ct, Position(*goal), True)


def _inside(p, tile):
    return 0 <= tile[0] < p.w and 0 <= tile[1] < p.h


def _launcher_hazards(p):
    """Tiles where an enemy Launcher could pick this Builder up."""
    return getattr(p, "enemy_launcher_danger", set())
