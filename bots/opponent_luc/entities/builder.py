"""Role-based Builder Bot strategy.

The first Builder infers its attacker role; the Core preannounces every later
assignment. Attackers relay through launchers toward the enemy Core, then place
ammo-fed Sentinels on open conveyor outputs.
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
_GUNNER_RANGE_SQ = 13
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
    splitter_direction: Direction | None = None
    gunners: tuple[tuple[Position, Direction], ...] = ()


@dataclass(frozen=True, slots=True)
class ConveyorEndpoint:
    conveyor: Position
    turret: Position


class BuilderMixin:
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Builder 0 recognizes the untouched assignment word and becomes the
        # first attacker. The Core announces every later Builder one round
        # before spawning it. Each Builder decodes only its birth snapshot and
        # retains that role locally for the rest of its life.
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
        self.offensive_gunner_index = 0

    def run_builder(self, ct: Controller) -> None:
        if self.is_attacker is None:
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
        assignment = ct.read_store(SLOT_SPAWN_ASSIGNMENT)
        if assignment == 0:
            spawn_index, is_attacker = 0, True
        else:
            spawn_index, is_attacker = decode_spawn_assignment(assignment)
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

        if self._is_next_to_core(endpoint.turret, enemy_core):
            facing = self._gunner_facing_toward_core(
                km, endpoint.turret, core_footprint(enemy_core)
            )
            if facing is not None and ct.can_build_gunner(endpoint.turret, facing):
                ct.build_gunner(endpoint.turret, facing)
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

    @staticmethod
    def _is_next_to_core(position: Position, core_anchor: Position) -> bool:
        return any(
            max(abs(position.x - tile.x), abs(position.y - tile.y)) == 1
            for tile in core_footprint(core_anchor)
        )

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
            if self.conveyor_plan is None:
                self.conveyor_plan = self._plan_offensive_conveyors(
                    ct, km, self.active_harvester
                )
            self.conveyor_plan_ready = True
            self.conveyor_index = 0
            self.offensive_gunner_index = 0
            if self.conveyor_plan is None:
                # Some ore pockets are diagonally walkable but have no
                # cardinal route to either base or an enemy-Core battery.
                self._advance_infrastructure_target()
                return

        if self.conveyor_plan is not None and self._build_conveyor_plan(ct, km):
            if self.conveyor_plan.splitter_direction is None:
                self._advance_infrastructure_target()
            elif self._build_offensive_battery(ct, km):
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
        friendly_conveyors = self._friendly_conveyors(ct)
        conveyor_directions = {
            position: self.map[position].building.direction
            for position in friendly_conveyors
            if self.map[position].building is not None
        }
        blocked = {
            position
            for position, tile in self.map.items()
            if tile.occupancy_known and tile.building is not None
        }
        blocked |= set(km.cores)

        # Prefer joining the nearest friendly line, provided doing so never
        # sends titanium farther away from our Core. This prevents two
        # unfinished lines from turning toward one another. If the friendly
        # route fails that check, use the shortest direct route to the Core.
        if friendly_conveyors:
            friendly_plan = self._plan_conveyor_path(
                km,
                harvester,
                friendly_conveyors,
                conveyor_directions,
                blocked,
            )
            if friendly_plan is not None:
                sink_direction = conveyor_directions[friendly_plan.sink]
                sink_output = friendly_plan.sink.add(sink_direction)
                if self._plan_moves_toward_targets(
                    harvester, friendly_plan, core_tiles
                ) and self._target_distance(
                    sink_output, core_tiles
                ) < self._target_distance(friendly_plan.sink, core_tiles):
                    return friendly_plan

        return self._plan_conveyor_path(
            km,
            harvester,
            core_tiles,
            {},
            blocked,
        )

    def _plan_conveyor_path(
        self,
        km: KnownMap,
        source_building: Position,
        sinks: set[Position],
        sink_directions: dict[Position, Direction],
        blocked: set[Position],
    ) -> ConveyorPlan | None:
        """Return the shortest cardinal conveyor path to an accepted sink."""

        def accepts(source: Position, sink: Position) -> bool:
            if abs(source.x - sink.x) + abs(source.y - sink.y) != 1:
                return False
            direction = sink_directions.get(sink)
            return direction is None or source != sink.add(direction)

        ordered_sinks = sorted(sinks, key=lambda position: (position.y, position.x))
        for sink in ordered_sinks:
            if accepts(source_building, sink):
                return ConveyorPlan((), sink)

        previous: dict[Position, Position | None] = {}
        queue: deque[Position] = deque()
        for direction in CARDINAL_DIRECTIONS:
            candidate = source_building.add(direction)
            if self._conveyor_tile_available(km, candidate, blocked):
                previous[candidate] = None
                queue.append(candidate)

        reached: Position | None = None
        reached_sink: Position | None = None
        while queue:
            current = queue.popleft()
            for sink in ordered_sinks:
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

    @classmethod
    def _plan_moves_toward_targets(
        cls,
        source: Position,
        plan: ConveyorPlan,
        targets: set[Position],
    ) -> bool:
        positions = (*plan.positions, plan.sink)
        previous = source
        for position in positions:
            if cls._target_distance(position, targets) > cls._target_distance(
                previous, targets
            ):
                return False
            previous = position
        return True

    @staticmethod
    def _target_distance(position: Position, targets: set[Position]) -> int:
        return min(
            abs(position.x - target.x) + abs(position.y - target.y)
            for target in targets
        )

    def _plan_offensive_conveyors(
        self, ct: Controller, km: KnownMap, harvester: Position
    ) -> ConveyorPlan | None:
        """Route an otherwise stranded Harvester into a small Gunner battery."""

        _, enemy_core = core_positions(ct, km)
        enemy_tiles = core_footprint(enemy_core)
        blocked = {
            position
            for position, tile in self.map.items()
            if tile.occupancy_known and tile.building is not None
        }
        blocked |= set(km.cores)

        # One BFS gives a path to every possible input tile. Candidate
        # Splitters are evaluated afterward, preferring more Core-hitting
        # Gunners and then the shortest supply line.
        previous: dict[Position, Position | None] = {}
        distance: dict[Position, int] = {}
        queue: deque[Position] = deque()
        for direction in CARDINAL_DIRECTIONS:
            candidate = harvester.add(direction)
            if self._conveyor_tile_available(km, candidate, blocked):
                previous[candidate] = None
                distance[candidate] = 1
                queue.append(candidate)

        while queue:
            current = queue.popleft()
            for direction in CARDINAL_DIRECTIONS:
                candidate = current.add(direction)
                if candidate in previous or not self._conveyor_tile_available(
                    km, candidate, blocked
                ):
                    continue
                previous[candidate] = current
                distance[candidate] = distance[current] + 1
                queue.append(candidate)

        candidates: list[
            tuple[
                tuple[int, int, int, int, int],
                Position,
                Direction,
                tuple[tuple[Position, Direction], ...],
            ]
        ] = []
        for source in previous:
            for splitter_direction in CARDINAL_DIRECTIONS:
                splitter = source.add(splitter_direction)
                if not self._conveyor_tile_available(km, splitter, blocked):
                    continue
                if splitter.distance_squared(enemy_core) >= source.distance_squared(
                    enemy_core
                ):
                    continue
                gunners = self._offensive_gunner_layout(
                    km,
                    splitter,
                    source,
                    enemy_tiles,
                    blocked,
                )
                if not gunners:
                    continue
                candidates.append(
                    (
                        (
                            -len(gunners),
                            distance[source],
                            splitter.distance_squared(enemy_core),
                            splitter.y,
                            splitter.x,
                        ),
                        source,
                        splitter_direction,
                        gunners,
                    )
                )

        if not candidates:
            return None
        for _, source, splitter_direction, gunners in sorted(
            candidates, key=lambda item: item[0]
        ):
            splitter = source.add(splitter_direction)
            path = [source]
            while previous[path[-1]] is not None:
                path.append(previous[path[-1]])  # type: ignore[arg-type]
            path.reverse()

            # Do not lay the supply line through a future turret tile.
            gunner_positions = {position for position, _ in gunners}
            if any(
                position in gunner_positions or position == splitter
                for position in path
            ):
                continue
            return ConveyorPlan(
                tuple(path),
                splitter,
                splitter_direction=splitter_direction,
                gunners=gunners,
            )
        return None

    @classmethod
    def _offensive_gunner_layout(
        cls,
        km: KnownMap,
        splitter: Position,
        input_position: Position,
        enemy_tiles: set[Position],
        blocked: set[Position],
    ) -> tuple[tuple[Position, Direction], ...]:
        input_side = splitter.direction_to(input_position)
        result: list[tuple[Position, Direction]] = []
        for output_direction in CARDINAL_DIRECTIONS:
            if output_direction == input_side:
                continue
            gunner = splitter.add(output_direction)
            if gunner in blocked or not static_bot_passable(km, gunner):
                continue
            facing = cls._gunner_facing_toward_core(km, gunner, enemy_tiles)
            if facing is not None:
                result.append((gunner, facing))
        return tuple(result)

    @staticmethod
    def _gunner_facing_toward_core(
        km: KnownMap, gunner: Position, enemy_tiles: set[Position]
    ) -> Direction | None:
        for target in sorted(
            enemy_tiles,
            key=lambda position: (
                gunner.distance_squared(position),
                position.y,
                position.x,
            ),
        ):
            dx = target.x - gunner.x
            dy = target.y - gunner.y
            if gunner.distance_squared(target) > _GUNNER_RANGE_SQ:
                continue
            if dx != 0 and dy != 0 and abs(dx) != abs(dy):
                continue
            direction = gunner.direction_to(target)
            step_x, step_y = direction.delta()
            current = Position(gunner.x + step_x, gunner.y + step_y)
            clear = True
            while current != target:
                if not static_bot_passable(km, current):
                    clear = False
                    break
                current = Position(current.x + step_x, current.y + step_y)
            if clear:
                return direction
        return None

    def _friendly_conveyors(self, ct: Controller) -> set[Position]:
        return {
            position
            for position, tile in self.map.items()
            if tile.building is not None
            and tile.building.team == ct.get_team()
            and tile.building.entity_type == EntityType.CONVEYOR
            and tile.building.direction in CARDINAL_DIRECTIONS
        }

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

    def _build_offensive_battery(self, ct: Controller, km: KnownMap) -> bool:
        plan = self.conveyor_plan
        if plan is None or plan.splitter_direction is None:
            return True

        splitter_id = ct.get_tile_building_id(plan.sink)
        if splitter_id is None:
            build_positions = adjacent_positions(km, plan.sink)
            if ct.get_position() not in build_positions:
                self._move_toward(ct, km, build_positions)
                return False
            if ct.get_action_cooldown() != 0:
                return False
            if ct.can_build_splitter(plan.sink, plan.splitter_direction):
                ct.build_splitter(plan.sink, plan.splitter_direction)
                # Splitters are walkable, so use the independent movement
                # action to get into position for the first Gunner.
                self._move_toward(ct, km, {plan.sink})
            return False
        if (
            ct.get_team(splitter_id) != ct.get_team()
            or ct.get_entity_type(splitter_id) != EntityType.SPLITTER
        ):
            return True

        while self.offensive_gunner_index < len(plan.gunners):
            gunner_position, facing = plan.gunners[self.offensive_gunner_index]
            existing_id = ct.get_tile_building_id(gunner_position)
            if existing_id is not None:
                self.offensive_gunner_index += 1
                continue

            build_positions = adjacent_positions(km, gunner_position)
            if ct.get_position() not in build_positions:
                self._move_toward(ct, km, build_positions)
                return False
            if ct.get_action_cooldown() != 0:
                return False
            if ct.can_build_gunner(gunner_position, facing):
                ct.build_gunner(gunner_position, facing)
                self.offensive_gunner_index += 1
            return self.offensive_gunner_index >= len(plan.gunners)
        return True

    def _advance_infrastructure_target(self) -> None:
        self.infrastructure_target_index += 1
        self.active_harvester = None
        self.conveyor_plan = None
        self.conveyor_plan_ready = False
        self.conveyor_index = 0
        self.offensive_gunner_index = 0

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
