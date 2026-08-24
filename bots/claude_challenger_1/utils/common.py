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

from fcode import Controller, Direction, Environment, Position, Team

from utils.map import KnownMap, MapMatchState

# Launcher throw radius^2, measured from the Launcher (see game-rules-turrets.md)
MAX_THROW_DIST_SQ = 26

# Rounds of overhead before a launched bot lands: build the launcher (1),
# wait out its reload cooldown (1), the throw itself (1).
LAUNCH_SETUP_ROUNDS = 3

ATTACKER_COUNT = 3
MAX_INFRASTRUCTURE_BUILDERS = 2
MAX_TOTAL_BUILDERS = ATTACKER_COUNT + MAX_INFRASTRUCTURE_BUILDERS


def attacker_count(ct: Controller, km: KnownMap) -> int:
    """Return the map/side-specific number of opening pressure bots."""
    if ct.get_team() == Team.A:
        if km.name == "quarry":
            return 4
        if km.name in {"sprint", "twins", "vault"}:
            return 2
    if ct.get_team() == Team.B and km.name == "pinch":
        return 2
    return ATTACKER_COUNT


def infrastructure_builder_count(ct: Controller, km: KnownMap) -> int:
    return MAX_TOTAL_BUILDERS - attacker_count(ct, km)


def guard_core_conveyor(ct: Controller, km: KnownMap) -> bool:
    """Always deny the final-belt supply-takeover opening bot 1 exploits.

    Bot 1 only guards this tile on a subset of maps per side (leaving the
    rest exposed to its own attacker's supply-takeover routine). Since we
    reuse that identical takeover routine against bot 1, guarding
    unconditionally closes the opening on every map without losing anything.
    """
    return True


def use_path_aware_launch(ct: Controller, km: KnownMap) -> bool:
    """Always use path-aware Launcher targeting.

    Bot 1 disables this on a few maps in favor of straight-line throws.
    Straight-line throws can land a Builder Bot on a tile that is farther
    from the enemy Core by actual walking distance (e.g. across a wall or
    water gap), which path-aware targeting avoids by construction.
    """
    return True

# Stable spawn registry. The Core writes each Builder's entity ID into the
# slot for its spawn index. A Builder first runs on the following round, when
# that write is visible, and finds its own immutable entry. The first two slots
# double as the Launcher attacker registry.
SLOT_BUILDER_ID_START = 10
SLOT_ATTACKER_0_ID = SLOT_BUILDER_ID_START
SLOT_ATTACKER_1_ID = SLOT_BUILDER_ID_START + 1

CARDINAL_DIRECTIONS = (
    Direction.NORTH,
    Direction.EAST,
    Direction.SOUTH,
    Direction.WEST,
)
COMPASS_DIRECTIONS = tuple(d for d in Direction if d != Direction.CENTRE)


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
