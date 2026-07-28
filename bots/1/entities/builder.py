"""Role-based Builder Bot strategy.

The Core publishes one assignment per spawn. Attackers relay through launchers
toward the enemy Core, then place ammo-fed Sentinels on open conveyor outputs.
Infrastructure bots claim disjoint ore sequences, build Harvesters, and connect
them to the nearest conveyor that is known to lead to our Core (or the Core
itself when no closer connected conveyor exists).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from fcode import Controller, Direction, EntityType, Position

from utils.common import (
    ATTACKER_COUNT,
    CARDINAL_DIRECTIONS,
    COMPASS_DIRECTIONS,
    LAUNCH_SETUP_ROUNDS,
    MAX_INFRASTRUCTURE_BUILDERS,
    MAX_THROW_DIST_SQ,
    SLOT_SPAWN_ASSIGNMENT,
    adjacent_positions,
    core_footprint,
    core_perimeter,
    core_positions,
    decode_spawn_assignment,
    in_bounds,
    ordered_ores,
    path_distance,
    known_map_or_warn,
    static_bot_passable,
)
from utils.map import KnownMap

_MAX_LAUNCH_WAIT_ROUNDS = 15
_DIRECTION_ORDER = (
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
)


@dataclass(frozen=True, slots=True)
class ConveyorPlan:
    positions: tuple[Position, ...]
    sink: Position


@dataclass(frozen=True, slots=True)
class ConveyorEndpoint:
    conveyor: Position
    turret: Position


class BuilderMixin:
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # A store write made during spawning is visible next round. Every new
        # Builder therefore skips its birth turn before reading this word.
        self.waited_for_assignment = False
        self.spawn_index: int | None = None
        self.is_attacker: bool | None = None

        # Attacker state.
        self.built_a_launcher = False
        self.waiting_launcher_id: int | None = None
        self.waiting_position: Position | None = None
        self.launch_wait_rounds = 0
        self.ignored_launchers: set[int] = set()

        # Infrastructure state.
        self.infrastructure_targets: list[Position] = []
        self.infrastructure_target_index = 0
        self.active_harvester: Position | None = None
        self.conveyor_plan: ConveyorPlan | None = None
        self.conveyor_plan_ready = False
        self.conveyor_index = 0

    def run_builder(self, ct: Controller) -> None:
        if self.is_attacker is None:
            if not self.waited_for_assignment:
                self.waited_for_assignment = True
                return
            km = known_map_or_warn(self.map_match_state)
            if km is None:
                return
            self._read_assignment(ct, km)
        else:
            km = known_map_or_warn(self.map_match_state)
            if km is None:
                return

        if self.is_attacker:
            self._run_attacker(ct, km)
        else:
            self._run_infrastructure(ct, km)

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def _read_assignment(self, ct: Controller, km: KnownMap) -> None:
        spawn_index, is_attacker = decode_spawn_assignment(
            ct.read_store(SLOT_SPAWN_ASSIGNMENT)
        )
        self.spawn_index = spawn_index
        self.is_attacker = is_attacker

        if not is_attacker:
            my_core, _ = core_positions(ct, km)
            infrastructure_index = spawn_index - ATTACKER_COUNT
            if infrastructure_index < 0:
                raise RuntimeError("Infrastructure bot received an attacker spawn index")
            ores = ordered_ores(km, my_core)
            self.infrastructure_targets = ores[
                infrastructure_index::MAX_INFRASTRUCTURE_BUILDERS
            ]

    # ------------------------------------------------------------------
    # Attackers and launcher relay
    # ------------------------------------------------------------------

    def _run_attacker(self, ct: Controller, km: KnownMap) -> None:
        _, enemy_core = core_positions(ct, km)
        if self._wait_for_launch(ct):
            return

        launcher = self._closest_forward_launcher(ct, km, enemy_core)
        if launcher is not None:
            launcher_id, launcher_pos = launcher
            if self._is_adjacent(ct.get_position(), launcher_pos):
                self._start_waiting_for_launcher(ct, launcher_id)
                return
            goals = adjacent_positions(km, launcher_pos)
            if self._move_toward(ct, km, goals):
                return

        force_first_launcher = self.spawn_index == 0 and not self.built_a_launcher
        launcher_position, launcher_is_faster = self._best_launcher_position(
            ct, km, enemy_core
        )
        if launcher_position is not None and (
            force_first_launcher or launcher_is_faster
        ):
            if ct.get_action_cooldown() != 0:
                return
            if ct.get_global_resources() < ct.get_launcher_cost():
                return
            candidates = list(adjacent_positions(km, ct.get_position()))
            candidates.sort(
                key=lambda position: (
                    position != launcher_position,
                    position.distance_squared(enemy_core),
                    position.y,
                    position.x,
                )
            )
            for candidate in candidates:
                if ct.can_build_launcher(candidate):
                    launcher_id = ct.build_launcher(candidate)
                    self.built_a_launcher = True
                    self._start_waiting_for_launcher(ct, launcher_id)
                    return

        self._seek_conveyor_endpoint(ct, km, enemy_core)

    def _wait_for_launch(self, ct: Controller) -> bool:
        launcher_id = self.waiting_launcher_id
        if launcher_id is None:
            return False
        if ct.get_position() != self.waiting_position:
            self.ignored_launchers.add(launcher_id)
            self._clear_launch_wait()
            return False

        self.launch_wait_rounds += 1
        if self.launch_wait_rounds >= _MAX_LAUNCH_WAIT_ROUNDS:
            self.ignored_launchers.add(launcher_id)
            self._clear_launch_wait()
            return False
        return True

    def _start_waiting_for_launcher(self, ct: Controller, launcher_id: int) -> None:
        self.waiting_launcher_id = launcher_id
        self.waiting_position = ct.get_position()
        self.launch_wait_rounds = 0

    def _clear_launch_wait(self) -> None:
        self.waiting_launcher_id = None
        self.waiting_position = None
        self.launch_wait_rounds = 0

    def _closest_forward_launcher(
        self, ct: Controller, km: KnownMap, enemy_core: Position
    ) -> tuple[int, Position] | None:
        position = ct.get_position()
        current_distance = self._distance_to_enemy(km, position, enemy_core)
        launchers: list[tuple[int, Position, int]] = []
        for tile_position, tile in self.map.items():
            building = tile.building
            if (
                tile.rounds_since_last_seen != 0
                or building is None
                or building.id in self.ignored_launchers
                or building.team != ct.get_team()
                or building.entity_type != EntityType.LAUNCHER
            ):
                continue
            launcher_distance = self._distance_to_enemy(km, tile_position, enemy_core)
            if launcher_distance > current_distance:
                continue
            goals = adjacent_positions(km, tile_position)
            walking_distance = path_distance(km, position, goals)
            if walking_distance is not None:
                launchers.append((building.id, tile_position, walking_distance))

        if not launchers:
            return None
        launcher_id, launcher_pos, _ = min(
            launchers,
            key=lambda item: (
                item[2],
                item[1].distance_squared(enemy_core),
                item[1].y,
                item[1].x,
            ),
        )
        return launcher_id, launcher_pos

    def _best_launcher_position(
        self, ct: Controller, km: KnownMap, enemy_core: Position
    ) -> tuple[Position | None, bool]:
        current = ct.get_position()
        walking_distance = self._distance_to_enemy(km, current, enemy_core)
        best_position: Position | None = None
        best_relay_distance: int | None = None

        for launcher_position in adjacent_positions(km, current):
            tile = self.map.get(launcher_position)
            if tile is not None and tile.occupancy_known and (
                tile.building is not None or tile.builder_bot is not None
            ):
                continue
            landing_distance = self._best_landing_distance(
                km, launcher_position, enemy_core
            )
            if landing_distance is None:
                continue
            relay_distance = LAUNCH_SETUP_ROUNDS + landing_distance
            if best_relay_distance is None or relay_distance < best_relay_distance:
                best_position = launcher_position
                best_relay_distance = relay_distance

        return (
            best_position,
            best_relay_distance is not None and best_relay_distance < walking_distance,
        )

    def _best_landing_distance(
        self, km: KnownMap, launcher: Position, enemy_core: Position
    ) -> int | None:
        best: int | None = None
        reach = int(MAX_THROW_DIST_SQ**0.5) + 1
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                if dx * dx + dy * dy == 0 or dx * dx + dy * dy > MAX_THROW_DIST_SQ:
                    continue
                landing = Position(launcher.x + dx, launcher.y + dy)
                if not static_bot_passable(km, landing):
                    continue
                distance = self._distance_to_enemy(km, landing, enemy_core)
                if best is None or distance < best:
                    best = distance
        return best

    # ------------------------------------------------------------------
    # Offensive turret placement
    # ------------------------------------------------------------------

    def _seek_conveyor_endpoint(
        self, ct: Controller, km: KnownMap, enemy_core: Position
    ) -> None:
        endpoints = self._visible_conveyor_endpoints(ct, km)
        if not endpoints:
            self._move_toward(ct, km, set(core_perimeter(enemy_core)))
            return

        current = ct.get_position()

        def endpoint_distance(endpoint: ConveyorEndpoint) -> int:
            distance = path_distance(
                km, current, adjacent_positions(km, endpoint.turret)
            )
            return distance if distance is not None else 10**9

        endpoints.sort(
            key=lambda endpoint: (
                endpoint_distance(endpoint),
                endpoint.turret.distance_squared(enemy_core),
                endpoint.turret.y,
                endpoint.turret.x,
            )
        )
        endpoint = endpoints[0]
        build_positions = adjacent_positions(km, endpoint.turret)
        if current not in build_positions:
            self._move_toward(ct, km, build_positions)
            return
        if ct.get_action_cooldown() != 0:
            return

        facing = self._sentinel_facing(ct, endpoint, enemy_core)
        if facing is not None and ct.can_build_sentinel(endpoint.turret, facing):
            ct.build_sentinel(endpoint.turret, facing)

    def _visible_conveyor_endpoints(
        self, ct: Controller, km: KnownMap
    ) -> list[ConveyorEndpoint]:
        endpoints: list[ConveyorEndpoint] = []
        for position, tile in self.map.items():
            building = tile.building
            if (
                tile.rounds_since_last_seen != 0
                or building is None
                or building.team == ct.get_team()
                or building.entity_type != EntityType.CONVEYOR
                or building.direction not in CARDINAL_DIRECTIONS
            ):
                continue
            output = position.add(building.direction)
            if not in_bounds(km, output) or not ct.is_in_vision(output):
                continue
            if (
                ct.get_tile_building_id(output) is None
                and ct.get_tile_builder_bot_id(output) is None
            ):
                endpoints.append(ConveyorEndpoint(position, output))
        return endpoints

    def _sentinel_facing(
        self, ct: Controller, endpoint: ConveyorEndpoint, enemy_core: Position
    ) -> Direction | None:
        desired = endpoint.turret.direction_to(enemy_core)
        feed_side = endpoint.turret.direction_to(endpoint.conveyor)
        directions = sorted(
            COMPASS_DIRECTIONS,
            key=lambda direction: self._direction_distance(direction, desired),
        )
        directions = [direction for direction in directions if direction != feed_side]

        enemy_tiles = core_footprint(enemy_core)
        for direction in directions:
            if any(
                ct.can_fire_from(
                    endpoint.turret,
                    direction,
                    EntityType.SENTINEL,
                    target,
                )
                for target in enemy_tiles
            ):
                return direction
        return directions[0] if directions else None

    @staticmethod
    def _direction_distance(a: Direction, b: Direction) -> int:
        a_index = _DIRECTION_ORDER.index(a)
        b_index = _DIRECTION_ORDER.index(b)
        difference = abs(a_index - b_index)
        return min(difference, len(_DIRECTION_ORDER) - difference)

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------

    def _run_infrastructure(self, ct: Controller, km: KnownMap) -> None:
        if self.infrastructure_target_index >= len(self.infrastructure_targets):
            return
        target = self.infrastructure_targets[self.infrastructure_target_index]

        if self.active_harvester is None:
            self._seek_and_build_harvester(ct, km, target)
            return

        if not self.conveyor_plan_ready:
            self.conveyor_plan = self._plan_conveyors(ct, km, self.active_harvester)
            self.conveyor_plan_ready = True
            self.conveyor_index = 0
            if self.conveyor_plan is None:
                # Some ore pockets are diagonally walkable but have no
                # cardinal route for conveyors. Keep the Harvester and move
                # on to this bot's next non-overlapping ore assignment.
                self._advance_infrastructure_target()
                return

        if self.conveyor_plan is not None and self._build_conveyor_plan(ct, km):
            self._advance_infrastructure_target()

    def _seek_and_build_harvester(
        self, ct: Controller, km: KnownMap, target: Position
    ) -> None:
        current = ct.get_position()
        goals = adjacent_positions(km, target)
        if current not in goals:
            self._move_toward(ct, km, goals)
            return

        building_id = ct.get_tile_building_id(target)
        if building_id is not None:
            if (
                ct.get_team(building_id) == ct.get_team()
                and ct.get_entity_type(building_id) == EntityType.HARVESTER
            ):
                self.active_harvester = target
            else:
                self._advance_infrastructure_target()
            return
        if ct.get_action_cooldown() == 0 and ct.can_build_harvester(target):
            ct.build_harvester(target)
            self.active_harvester = target

    def _plan_conveyors(
        self, ct: Controller, km: KnownMap, harvester: Position
    ) -> ConveyorPlan | None:
        my_core, _ = core_positions(ct, km)
        core_tiles = core_footprint(my_core)
        connected = self._connected_conveyors(ct, core_tiles)
        conveyor_directions = {
            position: self.map[position].building.direction
            for position in connected
            if self.map[position].building is not None
        }
        sinks = core_tiles | connected

        def accepts(source: Position, sink: Position) -> bool:
            if abs(source.x - sink.x) + abs(source.y - sink.y) != 1:
                return False
            if sink in core_tiles:
                return True
            direction = conveyor_directions[sink]
            return source != sink.add(direction)

        for sink in sinks:
            if accepts(harvester, sink):
                return ConveyorPlan((), sink)

        blocked = {
            position
            for position, tile in self.map.items()
            if tile.occupancy_known and tile.building is not None
        }
        blocked |= set(km.cores)
        previous: dict[Position, Position | None] = {}
        queue: deque[Position] = deque()
        for direction in CARDINAL_DIRECTIONS:
            candidate = harvester.add(direction)
            if self._conveyor_tile_available(km, candidate, blocked):
                previous[candidate] = None
                queue.append(candidate)

        reached: Position | None = None
        reached_sink: Position | None = None
        while queue:
            current = queue.popleft()
            for sink in sinks:
                if accepts(current, sink):
                    reached = current
                    reached_sink = sink
                    queue.clear()
                    break
            if reached is not None:
                break
            for direction in CARDINAL_DIRECTIONS:
                candidate = current.add(direction)
                if candidate in previous or not self._conveyor_tile_available(
                    km, candidate, blocked
                ):
                    continue
                previous[candidate] = current
                queue.append(candidate)

        if reached is None or reached_sink is None:
            return None
        path = [reached]
        while previous[path[-1]] is not None:
            path.append(previous[path[-1]])  # type: ignore[arg-type]
        path.reverse()
        return ConveyorPlan(tuple(path), reached_sink)

    def _connected_conveyors(
        self, ct: Controller, core_tiles: set[Position]
    ) -> set[Position]:
        conveyors = {
            position: tile.building
            for position, tile in self.map.items()
            if tile.building is not None
            and tile.building.team == ct.get_team()
            and tile.building.entity_type == EntityType.CONVEYOR
            and tile.building.direction in CARDINAL_DIRECTIONS
        }
        connected: set[Position] = set()
        visiting: set[Position] = set()

        def reaches_core(position: Position) -> bool:
            if position in connected:
                return True
            if position in visiting:
                return False
            visiting.add(position)
            next_position = position.add(conveyors[position].direction)
            result = next_position in core_tiles or (
                next_position in conveyors and reaches_core(next_position)
            )
            visiting.remove(position)
            if result:
                connected.add(position)
            return result

        for position in conveyors:
            reaches_core(position)
        return connected

    @staticmethod
    def _conveyor_tile_available(
        km: KnownMap, position: Position, blocked: set[Position]
    ) -> bool:
        return static_bot_passable(km, position) and position not in blocked

    def _build_conveyor_plan(self, ct: Controller, km: KnownMap) -> bool:
        plan = self.conveyor_plan
        if plan is None:
            return False
        if self.conveyor_index >= len(plan.positions):
            return True

        conveyor_position = plan.positions[self.conveyor_index]
        output = (
            plan.positions[self.conveyor_index + 1]
            if self.conveyor_index + 1 < len(plan.positions)
            else plan.sink
        )
        direction = conveyor_position.direction_to(output)
        if direction not in CARDINAL_DIRECTIONS:
            raise RuntimeError("Conveyor plan contains a non-cardinal segment")

        current = ct.get_position()
        build_positions = adjacent_positions(km, conveyor_position) | {
            conveyor_position
        }
        if current not in build_positions:
            self._move_toward(ct, km, build_positions)
            return False

        existing_id = ct.get_tile_building_id(conveyor_position)
        if existing_id is not None:
            if (
                ct.get_team(existing_id) == ct.get_team()
                and ct.get_entity_type(existing_id) == EntityType.CONVEYOR
                and ct.get_direction(existing_id) == direction
            ):
                self.conveyor_index += 1
                return self.conveyor_index >= len(plan.positions)
            self.conveyor_plan_ready = False
            return False

        if ct.get_action_cooldown() == 0 and ct.can_build_conveyor(
            conveyor_position, direction
        ):
            ct.build_conveyor(conveyor_position, direction)
            self.conveyor_index += 1
            return self.conveyor_index >= len(plan.positions)
        return False

    def _advance_infrastructure_target(self) -> None:
        self.infrastructure_target_index += 1
        self.active_harvester = None
        self.conveyor_plan = None
        self.conveyor_plan_ready = False
        self.conveyor_index = 0

    # ------------------------------------------------------------------
    # Shared movement helpers
    # ------------------------------------------------------------------

    def _move_toward(
        self, ct: Controller, km: KnownMap, goals: set[Position]
    ) -> bool:
        if ct.get_move_cooldown() != 0 or not goals:
            return False
        current = ct.get_position()
        choices: list[tuple[int, int, Direction]] = []
        for order, direction in enumerate(COMPASS_DIRECTIONS):
            if not ct.can_move(direction):
                continue
            candidate = current.add(direction)
            distance = path_distance(km, candidate, goals)
            if distance is not None:
                choices.append((distance, order, direction))
        if not choices:
            return False
        _, _, direction = min(choices)
        ct.move(direction)
        return True

    @staticmethod
    def _is_adjacent(a: Position, b: Position) -> bool:
        return max(abs(a.x - b.x), abs(a.y - b.y)) == 1

    @staticmethod
    def _distance_to_enemy(
        km: KnownMap, position: Position, enemy_core: Position
    ) -> int:
        distance = path_distance(km, position, set(core_perimeter(enemy_core)))
        return distance if distance is not None else 10**9
