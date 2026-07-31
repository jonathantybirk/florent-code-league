"""Map-agnostic online economy planner and explorer."""

from collections import deque
import os
import sys
from typing import TYPE_CHECKING

from fcode import Controller, EntityType, Environment, GameError, Position

from constants import (
    CLAIM_SLOTS,
    D4_DELTAS,
    D8,
    ECONOMY_BUILDERS,
    FACING,
    SLOT_BUILDER_TICKET,
    SLOT_CONSTRUCTION_LOCK,
    SLOT_CORE_DAMAGED,
    SLOT_ENEMY_CORE,
    SLOT_ALERT,
    SLOT_OWN_CORE,
    SLOT_SYMMETRY_REJECT_START,
    WALKABLE_BUILDINGS,
)
from utils import pack_pos, unpack_pos

if TYPE_CHECKING:
    from main import Player


HARASS_PRIORITY = {EntityType.SPLITTER: 0, EntityType.CONVEYOR: 1}
GUNNER_RANGE_SQ = 13


def run(p: "Player", ct: Controller) -> None:
    try:
        _run(p, ct)
    except GameError as error:
        if os.environ.get("JONBOT_DEBUG"):
            print("GameError", ct.get_current_round(), error, file=sys.stderr, flush=True)
        # An escaping GameError permanently destroys this unit.
        return


def _run(p, ct):
    if not hasattr(p, "builder_index"):
        p.builder_index = ct.read_store(SLOT_BUILDER_TICKET)
        ct.write_store(SLOT_BUILDER_TICKET, p.builder_index + 1)
        p.w, p.h = ct.get_map_width(), ct.get_map_height()
        p.seen, p.terrain = set(), {}
        p.walls, p.ores, p.solids, p.conveyors = set(), set(), set(), {}
        p.bot_occupied, p.enemy_conveyors = set(), {}
        p.enemy_economy = {}
        p.core, p.foot = None, set()
        p.task, p.route, p.route_i, p.phase = None, [], 0, "scout"
        p.explored = set()
        p.rejected_symmetries = 0
        p.current_route_tiles = set()
        p.network_tiles = set()
        p.network_load = 0
        p.economy_lines_completed = 0
        p.is_attacker = p.builder_index >= ECONOMY_BUILDERS
        p.offensive_gunner_built = False
        p.takeover_target = None
        p.takeover_predecessor = None
        p.takeover_stage = "terminal"
        p.blocked_terminal = None
        p.dislodge_gunner = None
        p.dislodge_started = None
        p.after_dislodge = False
        p.battery_gunners = []
        p.local_assault_plan = None
        p.local_assault_i = 0
        p.enemy_perimeter_seen = set()
        p.opening_launcher_built = False
        p.opening_launcher_pos = None
        p.lock_required = False
    _sense(p, ct)
    _update_enemy_core_inference(p, ct)
    if p.core is None:
        return
    if not p.is_attacker and ct.read_store(SLOT_CORE_DAMAGED):
        _heal_core(p, ct)
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
            continue
        kind = ct.get_entity_type(bid)
        enemy = ct.get_team(bid) != ct.get_team()
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
    if me != target:
        if tile in p.walls or tile in p.solids or (
            tile in p.conveyors and tile not in p.current_route_tiles
        ):
            _replace_route(p, outward=True)
            return
        _step(p, ct, target, True)
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
    if me != target:
        if tile in p.walls or tile in p.solids or (
            tile in p.conveyors and tile not in p.current_route_tiles
        ):
            _replace_route(p)
            return
        _step(p, ct, target, True)
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


def _step(p, ct, target, exact):
    source = ct.get_position()
    nxt = _bfs_step(p, tuple(source), tuple(target), exact)
    if nxt:
        for direction in D8:
            if source.add(direction) == Position(*nxt) and ct.can_move(direction):
                ct.move(direction)
                return


def _bfs_step(p, source, target, exact):
    goals = {target} if exact else _adjacent(p, target)
    if source in goals:
        return None
    blocked = p.walls | p.foot | p.solids | (p.bot_occupied - {source})
    prev, queue = {source: None}, deque([source])
    found = None
    while queue:
        cur = queue.popleft()
        if cur in goals:
            found = cur
            break
        for direction in D8:
            dx, dy = direction.delta()
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
    blocked = p.walls | p.foot | p.solids | (p.bot_occupied - {source})
    dist, queue = {source: 0}, deque([source])
    while queue:
        cur = queue.popleft()
        for direction in D8:
            dx, dy = direction.delta()
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
               and (x // stride + y // stride) % 3 == p.builder_index % 3]
    if not choices:
        p.explored.clear()
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
    for target in targets:
        if me == target:
            position = Position(*target)
            if ct.can_fire(position):
                ct.fire(position)
                return

    if targets:
        _step(p, ct, Position(*targets[0]), True)
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


def _rush(p, ct):
    if p.builder_index == ECONOMY_BUILDERS and not p.opening_launcher_built:
        if _build_opening_launcher(p, ct):
            return
    if p.opening_launcher_pos is not None:
        launcher = Position(*p.opening_launcher_pos)
        if ct.get_position().distance_squared(launcher) <= 2:
            return
        p.opening_launcher_pos = None
    packed = ct.read_store(SLOT_ENEMY_CORE)
    enemy_core = unpack_pos(packed) if packed else None
    if enemy_core is None:
        _explore(p, ct)
        return
    if p.offensive_gunner_built and p.takeover_stage == "done":
        _harass(p, ct)
        return
    if p.takeover_stage != "terminal":
        if _extend_takeover_battery(p, ct, enemy_core):
            return
        p.takeover_stage = "done"
        p.offensive_gunner_built = True
        _harass(p, ct)
        return
    if p.takeover_target is None:
        p.takeover_target = _supply_takeover_target(p, enemy_core)
        if p.takeover_target is not None:
            p.takeover_predecessor = _takeover_predecessor(
                p, tuple(p.takeover_target[0]))
    if p.takeover_target is None:
        if (p.builder_index <= ECONOMY_BUILDERS + 1
                and _build_local_assault(p, ct, enemy_core)):
            return
        _explore_enemy_perimeter(p, ct, enemy_core)
        return
    position, facing = p.takeover_target
    if p.takeover_predecessor is None:
        p.takeover_predecessor = _takeover_predecessor(p, tuple(position))
    if not ct.is_in_vision(position):
        _step(p, ct, position, False)
        return
    building_id = ct.get_tile_building_id(position)
    if building_id is not None:
        occupying_bot = ct.get_tile_builder_bot_id(position)
        if (occupying_bot is not None
                and ct.get_team(occupying_bot) != ct.get_team()):
            if p.takeover_predecessor is None:
                _step(p, ct, position, False)
                return
            visible_enemy_builders = sum(
                ct.get_team(entity_id) != ct.get_team()
                and ct.get_entity_type(entity_id) == EntityType.BUILDER_BOT
                for entity_id in ct.get_nearby_entities())
            # A through-line gun efficiently breaks a small terminal guard.  A
            # dense screen can continually replace blockers, so against one we
            # retain the ordinary lateral battery instead of sinking titanium
            # into a gun whose entire firing lane is contested.
            if visible_enemy_builders <= 4:
                choices = _supply_takeover_choices(p, enemy_core)
                if len(choices) > 1:
                    index = (p.builder_index - ECONOMY_BUILDERS) % len(choices)
                    assigned = choices[index]
                    if tuple(assigned[0]) != tuple(position):
                        p.takeover_target = assigned
                        p.takeover_predecessor = _takeover_predecessor(
                            p, tuple(assigned[0]))
                        return
                p.blocked_terminal = tuple(position)
            p.takeover_stage = "splitter"
            if _extend_takeover_battery(p, ct, enemy_core):
                return
            p.takeover_stage = "done"
            p.offensive_gunner_built = True
            return
        if (ct.get_team(building_id) == ct.get_team()
                and ct.get_entity_type(building_id) == EntityType.GUNNER):
            p.takeover_target = None
            _explore_enemy_perimeter(p, ct, enemy_core)
            return
        if tuple(ct.get_position()) != tuple(position):
            _step(p, ct, position, True)
        elif (ct.get_team(building_id) != ct.get_team()
              and ct.get_entity_type(building_id) == EntityType.CONVEYOR
              and ct.can_fire(position)):
            ct.fire(position)
        return
    if _cardinal_distance(tuple(ct.get_position()), tuple(position)) == 1:
        if ct.can_build_gunner(position, facing):
            ct.build_gunner(position, facing)
            if p.after_dislodge:
                p.takeover_stage = "done"
                p.offensive_gunner_built = True
            else:
                p.takeover_stage = "splitter"
            ct.write_store(SLOT_ALERT, 1)
        return
    _move_cardinal_adjacent(p, ct, tuple(position))


def _extend_takeover_battery(p, ct, enemy_core):
    """Fan a captured terminal line into every Core-facing firing lane.

    Replacing only the final belt captures one buffered ammunition stack.  The
    upstream Splitter lets the same line feed additional firing positions and
    also removes another enemy logistics tile.
    """
    predecessor = p.takeover_predecessor
    if predecessor is None:
        return False
    splitter_pos, splitter_direction = predecessor
    splitter_pos = Position(*splitter_pos)

    if p.takeover_stage == "splitter":
        if not ct.is_in_vision(splitter_pos):
            _step(p, ct, splitter_pos, False)
            return True
        building_id = ct.get_tile_building_id(splitter_pos)
        if building_id is not None:
            if (ct.get_team(building_id) == ct.get_team()
                    and ct.get_entity_type(building_id) == EntityType.SPLITTER):
                p.takeover_stage = (
                    "dislodge" if p.blocked_terminal is not None else "battery")
            elif (ct.get_team(building_id) != ct.get_team()
                  and ct.get_entity_type(building_id) == EntityType.CONVEYOR):
                if tuple(ct.get_position()) != tuple(splitter_pos):
                    _step(p, ct, splitter_pos, True)
                elif ct.can_fire(splitter_pos):
                    ct.fire(splitter_pos)
                return True
            else:
                return False
        else:
            if _cardinal_distance(tuple(ct.get_position()), tuple(splitter_pos)) != 1:
                _move_cardinal_adjacent(p, ct, tuple(splitter_pos))
                return True
            if ct.can_build_splitter(splitter_pos, splitter_direction):
                ct.build_splitter(splitter_pos, splitter_direction)
            return True

    if p.takeover_stage == "dislodge":
        terminal = Position(*p.blocked_terminal)
        if p.dislodge_gunner is None:
            options = _dislodge_layout(
                p, splitter_pos, splitter_direction, terminal, enemy_core)
            if not options:
                p.takeover_stage = "battery"
            else:
                p.dislodge_gunner = options[0]
        if p.takeover_stage == "dislodge" and p.dislodge_gunner is not None:
            position, facing = p.dislodge_gunner
            if not ct.is_in_vision(position):
                _step(p, ct, position, False)
                return True
            building_id = ct.get_tile_building_id(position)
            if building_id is None:
                if _cardinal_distance(tuple(ct.get_position()), tuple(position)) != 1:
                    _move_cardinal_adjacent(p, ct, tuple(position))
                    return True
                if ct.can_build_gunner(position, facing):
                    ct.build_gunner(position, facing)
                    p.dislodge_started = ct.get_current_round()
                return True
            if (ct.get_team(building_id) != ct.get_team()
                    or ct.get_entity_type(building_id) != EntityType.GUNNER):
                p.takeover_stage = "battery"
            else:
                if p.dislodge_started is None:
                    p.dislodge_started = ct.get_current_round()
                occupying_bot = (ct.get_tile_builder_bot_id(terminal)
                                  if ct.is_in_vision(terminal) else None)
                if occupying_bot is None:
                    p.blocked_terminal = None
                    p.after_dislodge = True
                    p.takeover_stage = "terminal"
                    return True
                if (p.dislodge_started is not None
                        and ct.get_current_round() - p.dislodge_started >= 12):
                    if ct.can_destroy(position):
                        ct.destroy(position)
                        p.solids.discard(tuple(position))
                        p.dislodge_gunner = None
                        p.blocked_terminal = None
                        p.takeover_stage = "battery"
                    else:
                        _move_cardinal_adjacent(p, ct, tuple(position))
                return True

    if p.takeover_stage == "battery":
        if not p.battery_gunners:
            p.battery_gunners = _battery_layout(
                p, splitter_pos, splitter_direction, enemy_core)
        while p.battery_gunners:
            position, facing = p.battery_gunners[0]
            if not ct.is_in_vision(position):
                _step(p, ct, position, False)
                return True
            building_id = ct.get_tile_building_id(position)
            if building_id is not None:
                p.battery_gunners.pop(0)
                continue
            if _cardinal_distance(tuple(ct.get_position()), tuple(position)) != 1:
                _move_cardinal_adjacent(p, ct, tuple(position))
                return True
            if ct.can_build_gunner(position, facing):
                ct.build_gunner(position, facing)
                p.battery_gunners.pop(0)
            return True
        p.takeover_stage = "done"
        return False
    return False


def _takeover_predecessor(p, terminal):
    choices = []
    for position, direction in p.enemy_conveyors.items():
        dx, dy = direction.delta()
        if (position[0] + dx, position[1] + dy) == terminal:
            choices.append((position, direction))
    return min(choices) if choices else None


def _battery_layout(p, splitter, splitter_direction, enemy_core):
    core_foot = {(enemy_core[0] + dx, enemy_core[1] + dy)
                 for dx in (0, 1) for dy in (0, 1)}
    input_direction = splitter_direction.opposite()
    result = []
    for direction in (d for d in FACING.values() if d != input_direction):
        position = splitter.add(direction)
        if not _inside(p, tuple(position)):
            continue
        facing = None
        for core_tile in sorted(core_foot):
            facing = _facing_toward(tuple(position), core_tile)
            if (facing is not None
                    and position.distance_squared(Position(*core_tile)) <= GUNNER_RANGE_SQ):
                break
            facing = None
        if facing is not None:
            result.append((position, facing))
    return result


def _dislodge_layout(p, splitter, splitter_direction, terminal, enemy_core):
    input_direction = splitter_direction.opposite()
    result = []
    for direction in (d for d in FACING.values() if d != input_direction):
        position = splitter.add(direction)
        if (not _inside(p, tuple(position)) or tuple(position) in p.solids
                or position == terminal):
            continue
        facing = _ray_direction(tuple(position), tuple(terminal))
        if facing is not None and position.distance_squared(terminal) <= GUNNER_RANGE_SQ:
            through_core = _ray_hits_core_after(
                position, terminal, enemy_core, facing)
            if through_core:
                result.append((position.x, position.y, position, facing))
    return [(position, facing) for _, _, position, facing in sorted(result)]


def _ray_direction(source, target):
    dx, dy = target[0] - source[0], target[1] - source[1]
    if not (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
        return None
    step = (0 if dx == 0 else (1 if dx > 0 else -1),
            0 if dy == 0 else (1 if dy > 0 else -1))
    return next((direction for direction in D8 if direction.delta() == step), None)


def _ray_hits_core_after(source, terminal, enemy_core, facing):
    core_foot = {(enemy_core[0] + dx, enemy_core[1] + dy)
                 for dx in (0, 1) for dy in (0, 1)}
    dx, dy = facing.delta()
    current = terminal.add(facing)
    while source.distance_squared(current) <= GUNNER_RANGE_SQ:
        if tuple(current) in core_foot:
            return True
        current = Position(current.x + dx, current.y + dy)
    return False


def _build_local_assault(p, ct, enemy_core):
    """Build a self-supplied battery when the opponent offers no line to steal."""
    if p.local_assault_plan is None:
        p.local_assault_plan = _plan_local_assault(p, enemy_core)
        p.local_assault_i = 0
    if not p.local_assault_plan:
        return False
    while p.local_assault_i < len(p.local_assault_plan):
        kind, position, direction = p.local_assault_plan[p.local_assault_i]
        position = Position(*position)
        if not ct.is_in_vision(position):
            _step(p, ct, position, False)
            return True
        building_id = ct.get_tile_building_id(position)
        if building_id is not None:
            if (ct.get_team(building_id) == ct.get_team()
                    and ct.get_entity_type(building_id) == kind):
                p.local_assault_i += 1
                continue
            p.local_assault_plan = None
            return False
        if _cardinal_distance(tuple(ct.get_position()), tuple(position)) != 1:
            _move_cardinal_adjacent(p, ct, tuple(position))
            return True
        if kind == EntityType.HARVESTER and ct.can_build_harvester(position):
            ct.build_harvester(position)
        elif kind == EntityType.CONVEYOR and ct.can_build_conveyor(position, direction):
            ct.build_conveyor(position, direction)
        elif kind == EntityType.SPLITTER and ct.can_build_splitter(position, direction):
            ct.build_splitter(position, direction)
        elif kind == EntityType.GUNNER and ct.can_build_gunner(position, direction):
            ct.build_gunner(position, direction)
        else:
            return True
        p.local_assault_i += 1
        return True
    p.offensive_gunner_built = True
    p.takeover_stage = "done"
    return False


def _plan_local_assault(p, enemy_core):
    """Shortest fully observed ore-to-battery plan beside the enemy Core."""
    core_foot = {(enemy_core[0] + dx, enemy_core[1] + dy)
                 for dx in (0, 1) for dy in (0, 1)}
    sources = [ore for ore in p.ores
               if ore in p.seen and ore not in p.solids
               and min((ore[0] - tile[0]) ** 2 + (ore[1] - tile[1]) ** 2
                       for tile in core_foot) <= 100]
    best = None
    for source in sources:
        prev, queue = {source: None}, deque([source])
        while queue:
            cur = queue.popleft()
            if cur != source:
                incoming = (cur[0] - prev[cur][0], cur[1] - prev[cur][1])
                splitter_direction = FACING[incoming]
                layout = _battery_layout(
                    p, Position(*cur), splitter_direction, enemy_core)
                layout = [(pos, facing) for pos, facing in layout
                          if tuple(pos) not in p.solids and tuple(pos) in p.seen]
                if len(layout) >= 2:
                    path, node = [], cur
                    while node is not None:
                        path.append(node)
                        node = prev[node]
                    path.reverse()
                    gunner_tiles = {tuple(pos) for pos, _ in layout}
                    if not any(tile in gunner_tiles for tile in path[:-1]):
                        score = (len(path), source, cur)
                        if best is None or score < best[0]:
                            best = (score, path, splitter_direction, layout)
                    break
            if len(prev) > 160:
                break
            for dx, dy in D4_DELTAS:
                nxt = cur[0] + dx, cur[1] + dy
                if (nxt in prev or not _inside(p, nxt) or nxt not in p.seen
                        or nxt in p.walls or nxt in p.foot or nxt in p.solids
                        or (nxt in p.ores and nxt != source)):
                    continue
                prev[nxt] = cur
                queue.append(nxt)
    if best is None:
        return None
    _, path, splitter_direction, layout = best
    supply = [(EntityType.HARVESTER, path[0], None)]
    for index, tile in enumerate(path[1:-1], start=1):
        nxt = path[index + 1]
        direction = FACING[(nxt[0] - tile[0], nxt[1] - tile[1])]
        supply.append((EntityType.CONVEYOR, tile, direction))
    gunners = [(EntityType.GUNNER, tuple(position), facing)
               for position, facing in layout]
    splitter = [(EntityType.SPLITTER, path[-1], splitter_direction)]
    return gunners + supply + splitter


def _build_opening_launcher(p, ct):
    own_core = unpack_pos(ct.read_store(SLOT_OWN_CORE))
    if own_core is None:
        return True
    target = _enemy_core_candidates(p)[0]
    me = ct.get_position()
    candidates = []
    for dx, dy in D4_DELTAS:
        position = Position(me.x + dx, me.y + dy)
        if _inside(p, tuple(position)) and ct.can_build_launcher(position):
            candidates.append(position)
    if not candidates:
        return False
    position = min(candidates, key=lambda tile: (
        tile.distance_squared(Position(*target)), tile.x, tile.y))
    ct.build_launcher(position)
    p.opening_launcher_built = True
    p.opening_launcher_pos = tuple(position)
    ct.write_store(SLOT_ALERT, ct.get_id())
    return True


def _explore_enemy_perimeter(p, ct, enemy_core):
    x, y = enemy_core
    candidates = [(x - 4, y), (x - 4, y + 1), (x, y - 4), (x + 1, y - 4),
                  (x + 5, y), (x + 5, y + 1), (x, y + 5), (x + 1, y + 5)]
    candidates = [tile for tile in candidates if _inside(p, tile)]
    if not candidates:
        _explore(p, ct)
        return
    me = tuple(ct.get_position())
    for tile in candidates:
        if ((tile[0] - me[0]) ** 2 + (tile[1] - me[1]) ** 2 <= 20
                or tile in p.walls or tile in p.solids):
            p.enemy_perimeter_seen.add(tile)
    remaining = [tile for tile in candidates if tile not in p.enemy_perimeter_seen]
    if not remaining:
        p.enemy_perimeter_seen.clear()
        remaining = candidates
    offset = (p.builder_index - ECONOMY_BUILDERS) % len(remaining)
    _step(p, ct, Position(*remaining[offset]), False)


def _supply_takeover_target(p, enemy_core):
    choices = _supply_takeover_choices(p, enemy_core)
    return choices[0] if choices else None


def _supply_takeover_choices(p, enemy_core):
    core_foot = {(enemy_core[0] + dx, enemy_core[1] + dy)
                 for dx in (0, 1) for dy in (0, 1)}
    choices = []
    for conveyor, output_direction in p.enemy_conveyors.items():
        out_dx, out_dy = output_direction.delta()
        if (conveyor[0] + out_dx, conveyor[1] + out_dy) not in core_foot:
            continue
        core_tile = min(core_foot, key=lambda tile:
                        (tile[0] - conveyor[0]) ** 2 + (tile[1] - conveyor[1]) ** 2)
        facing = _facing_toward(conveyor, core_tile)
        if facing is not None:
            choices.append((conveyor, facing))
    return [(Position(*conveyor), facing)
            for conveyor, facing in sorted(choices)]


def _facing_toward(source, target):
    dx, dy = target[0] - source[0], target[1] - source[1]
    if dx == 0 and dy:
        return FACING[(0, 1 if dy > 0 else -1)]
    if dy == 0 and dx:
        return FACING[(1 if dx > 0 else -1, 0)]
    return None


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
    goals = _cardinal_adjacent(p, target) - p.walls - p.solids - p.bot_occupied
    reachable = [(distance, goal) for goal in goals
                 if (distance := _distance(p, me, {goal})) is not None]
    if reachable:
        _, goal = min(reachable)
        _step(p, ct, Position(*goal), True)


def _inside(p, tile):
    return 0 <= tile[0] < p.w and 0 <= tile[1] < p.h
