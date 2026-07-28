"""Shared constants and map-derived strategy helpers.

These only work once MapMatchState has inferred which bundled map we're on
(see utils/map.py). Every unit recomputes the same values independently
(each unit is its own Player instance with no shared memory), so results
must be a pure function of (team, inferred map) for different units to agree.
"""

from __future__ import annotations

from collections import deque
from typing import Collection
from warnings import warn

from fcode import Controller, Direction, Environment, Position

from utils.map import KnownMap, MapMatchState

# Launcher throw radius^2, measured from the Launcher (see game-rules-turrets.md)
MAX_THROW_DIST_SQ = 26

# Rounds of overhead before a launched bot lands: build the launcher (1),
# wait out its reload cooldown (1), the throw itself (1).
LAUNCH_SETUP_ROUNDS = 3

# Communication-store layout. Slots 0-9 belong to individual infrastructure
# workers. The final five slots coordinate launching, spawning, and economy.
INFRASTRUCTURE_STATUS_SLOTS = tuple(range(10))
SLOT_LAUNCH_REQUEST = 12
SLOT_SPAWN_COUNT = 13
SLOT_RESOURCE_PRESSURE = 14
SLOT_SPAWN_ASSIGNMENT = 15
ATTACKER_ROLE_BIT = 1

MAX_BUILDERS = 11

CARDINAL_DIRECTIONS = (
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
)
COMPASS_DIRECTIONS = tuple(d for d in Direction if d != Direction.CENTRE)


def nearest_cardinal(direction: Direction) -> Direction:
    return min(
        CARDINAL_DIRECTIONS,
        key=lambda cardinal: _direction_steps(cardinal, direction),
    )


def _direction_steps(a: Direction, b: Direction) -> int:
    order = (
        Direction.NORTH,
        Direction.NORTHEAST,
        Direction.EAST,
        Direction.SOUTHEAST,
        Direction.SOUTH,
        Direction.SOUTHWEST,
        Direction.WEST,
        Direction.NORTHWEST,
    )
    difference = abs(order.index(a) - order.index(b))
    return min(difference, len(order) - difference)


def known_map(match_state: MapMatchState) -> KnownMap | None:
    name = match_state.inferred_map_name
    if name is None:
        return None
    return match_state.known_maps[name]


def known_map_or_warn(match_state: MapMatchState) -> KnownMap | None:
    """Return the matched map, warning once for this unit when unavailable."""

    km = known_map(match_state)
    if km is None and not match_state.warned_unknown_map:
        warn(
            "Bot 1 no longer knows the current map at round "
            f"{match_state.last_processed_round}; this is expected after a Core disappears",
            RuntimeWarning,
            stacklevel=2,
        )
        match_state.warned_unknown_map = True
    return km


def encode_spawn_assignment(spawn_index: int, *, attacker: bool) -> int:
    """Pack a spawn sequence and role into the final communication slot."""

    return ((spawn_index + 1) << 1) | (ATTACKER_ROLE_BIT if attacker else 0)


def decode_spawn_assignment(value: int) -> tuple[int, bool]:
    """Unpack ``(spawn_index, is_attacker)`` from a role assignment word."""

    sequence = value >> 1
    if sequence == 0:
        raise RuntimeError("Builder Bot did not receive a spawn-role assignment")
    return sequence - 1, bool(value & ATTACKER_ROLE_BIT)


def is_attacker_spawn(spawn_index: int) -> bool:
    """Bots 1, 2, 5, 8, 11, ... are attackers (index is zero-based)."""

    return spawn_index < 2 or (spawn_index >= 4 and (spawn_index - 4) % 3 == 0)


def infrastructure_ordinal(spawn_index: int) -> int:
    """Return this infrastructure bot's zero-based status-slot ordinal."""

    if is_attacker_spawn(spawn_index):
        raise ValueError("attacker spawn has no infrastructure ordinal")
    return sum(
        not is_attacker_spawn(index) for index in range(spawn_index + 1)
    ) - 1


def pack_infrastructure_status(
    ore_index: int,
    *,
    harvested: bool = False,
    connector: Position | None = None,
    connector_direction: Direction | None = None,
) -> int:
    """Pack an ore claim and optional connected conveyor into one store slot."""

    value = ore_index + 1
    if harvested:
        value |= 1 << 6
    if connector is not None and connector_direction in CARDINAL_DIRECTIONS:
        value |= 1 << 7
        value |= (connector.x & 0x1F) << 8
        value |= (connector.y & 0x1F) << 13
        value |= CARDINAL_DIRECTIONS.index(connector_direction) << 18
    return value


def unpack_infrastructure_status(
    value: int,
) -> tuple[int, bool, Position | None, Direction | None] | None:
    if value == 0:
        return None
    ore_index = (value & 0x3F) - 1
    harvested = bool(value & (1 << 6))
    if not value & (1 << 7):
        return ore_index, harvested, None, None
    connector = Position((value >> 8) & 0x1F, (value >> 13) & 0x1F)
    direction = CARDINAL_DIRECTIONS[(value >> 18) & 0x3]
    return ore_index, harvested, connector, direction


def pack_launch_request(builder_id: int, target: Position) -> int:
    """Pack an exact 16-bit entity id and two 5-bit coordinates into one u32."""

    return (
        (1 << 31)
        | (builder_id & 0xFFFF)
        | ((target.x & 0x1F) << 16)
        | ((target.y & 0x1F) << 21)
    )


def unpack_launch_request(value: int) -> tuple[int, Position] | None:
    if not value & (1 << 31):
        return None
    return value & 0xFFFF, Position((value >> 16) & 0x1F, (value >> 21) & 0x1F)


def core_positions(ct: Controller, km: KnownMap) -> tuple[Position, Position]:
    """Return (my_core, enemy_core) anchor positions."""
    my_team = ct.get_team()
    anchors = {fixed_core.anchor: fixed_core.team for fixed_core in km.cores.values()}
    my_core = next(a for a, team in anchors.items() if team == my_team)
    enemy_core = next(a for a, team in anchors.items() if team != my_team)
    return my_core, enemy_core


def core_footprint(anchor: Position) -> set[Position]:
    return {
        Position(anchor.x + dx, anchor.y + dy)
        for dy in range(2)
        for dx in range(2)
    }


def core_perimeter(anchor: Position) -> list[Position]:
    footprint = core_footprint(anchor)
    return [
        Position(x, y)
        for y in range(anchor.y - 1, anchor.y + 3)
        for x in range(anchor.x - 1, anchor.x + 3)
        if Position(x, y) not in footprint
    ]


def ore_positions(km: KnownMap) -> list[Position]:
    return [
        Position(x, y)
        for y, row in enumerate(km.environments)
        for x, tile in enumerate(row)
        if tile == Environment.ORE_TITANIUM
    ]


def in_bounds(km: KnownMap, position: Position) -> bool:
    return 0 <= position.x < km.width and 0 <= position.y < km.height


def static_bot_passable(km: KnownMap, position: Position) -> bool:
    return (
        in_bounds(km, position)
        and km.environment_at(position) != Environment.WALL
        and position not in km.cores
    )


def path_distance(
    km: KnownMap,
    start: Position,
    goals: Collection[Position],
    *,
    cardinal_only: bool = False,
) -> int | None:
    key = (
        km.name,
        tuple(sorted(goals, key=lambda position: (position.y, position.x))),
        cardinal_only,
    )
    distances = _DISTANCE_FIELD_CACHE.get(key)
    if distances is None:
        distances = _distance_field(km, goals, cardinal_only=cardinal_only)
        _DISTANCE_FIELD_CACHE[key] = distances
    return distances.get(start)


_DISTANCE_FIELD_CACHE: dict[
    tuple[str, tuple[Position, ...], bool], dict[Position, int]
] = {}


def _distance_field(
    km: KnownMap,
    goals: Collection[Position],
    *,
    cardinal_only: bool,
) -> dict[Position, int]:
    """Compute shortest static distances to a goal set in one reverse BFS."""

    directions = CARDINAL_DIRECTIONS if cardinal_only else COMPASS_DIRECTIONS
    distances = {
        goal: 0 for goal in goals if static_bot_passable(km, goal)
    }
    queue = deque(distances)
    while queue:
        current = queue.popleft()
        for direction in directions:
            candidate = current.add(direction)
            if candidate in distances or not static_bot_passable(km, candidate):
                continue
            if not cardinal_only and direction not in CARDINAL_DIRECTIONS:
                dx, dy = direction.delta()
                side_a = Position(current.x + dx, current.y)
                side_b = Position(current.x, current.y + dy)
                if (
                    not static_bot_passable(km, side_a)
                    or not static_bot_passable(km, side_b)
                ):
                    continue
            distances[candidate] = distances[current] + 1
            queue.append(candidate)
    return distances


def adjacent_positions(
    km: KnownMap, position: Position, *, cardinal_only: bool = False
) -> set[Position]:
    directions = CARDINAL_DIRECTIONS if cardinal_only else COMPASS_DIRECTIONS
    return {
        candidate
        for direction in directions
        if static_bot_passable(km, candidate := position.add(direction))
    }


_ORDERED_ORE_CACHE: dict[tuple[str, Position], tuple[Position, ...]] = {}


def ordered_ores(km: KnownMap, my_core: Position) -> list[Position]:
    """Order ore by actual static walking distance from our Core."""

    cache_key = (km.name, my_core)
    cached = _ORDERED_ORE_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)

    starts = core_perimeter(my_core)

    def key(ore: Position) -> tuple[int, int, int]:
        goals = adjacent_positions(km, ore)
        distances = [
            distance
            for start in starts
            if (distance := path_distance(km, start, goals)) is not None
        ]
        return (min(distances, default=10**9), ore.y, ore.x)

    result = sorted(ore_positions(km), key=key)
    _ORDERED_ORE_CACHE[cache_key] = tuple(result)
    return result


_CHOKEPOINT_CACHE: dict[str, frozenset[Position]] = {}


def chokepoints(km: KnownMap) -> frozenset[Position]:
    """Return narrow cardinal articulation tiles in the static terrain graph."""

    cached = _CHOKEPOINT_CACHE.get(km.name)
    if cached is not None:
        return cached
    vertices = {
        Position(x, y)
        for y in range(km.height)
        for x in range(km.width)
        if static_bot_passable(km, Position(x, y))
    }
    neighbours = {
        position: [
            candidate
            for direction in CARDINAL_DIRECTIONS
            if (candidate := position.add(direction)) in vertices
        ]
        for position in vertices
    }
    discovery: dict[Position, int] = {}
    low: dict[Position, int] = {}
    parent: dict[Position, Position | None] = {}
    articulation: set[Position] = set()
    time = 0

    def visit(position: Position) -> None:
        nonlocal time
        time += 1
        discovery[position] = low[position] = time
        child_count = 0
        for candidate in neighbours[position]:
            if candidate not in discovery:
                parent[candidate] = position
                child_count += 1
                visit(candidate)
                low[position] = min(low[position], low[candidate])
                if parent[position] is None and child_count > 1:
                    articulation.add(position)
                if (
                    parent[position] is not None
                    and low[candidate] >= discovery[position]
                ):
                    articulation.add(position)
            elif candidate != parent[position]:
                low[position] = min(low[position], discovery[candidate])

    for vertex in vertices:
        if vertex not in discovery:
            parent[vertex] = None
            visit(vertex)

    result = frozenset(
        position
        for position in articulation
        if len(neighbours[position]) <= 2
        and km.environment_at(position) != Environment.ORE_TITANIUM
        and position not in km.cores
    )
    _CHOKEPOINT_CACHE[km.name] = result
    return result
