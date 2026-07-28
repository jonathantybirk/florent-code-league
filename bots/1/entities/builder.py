"""Role-based Builder Bot strategy.

The Core records every Builder in a stable spawn-index registry. Attackers
relay through launchers toward the enemy Core, capture complete enemy supply
lines, and place ammo-fed turrets.
Infrastructure bots claim disjoint ore sequences, build Harvesters, and connect
them to the nearest conveyor that is known to lead to our Core (or the Core
itself when no closer connected conveyor exists).
"""

from __future__ import annotations

from collections.abc import Callable
from collections import deque
from dataclasses import dataclass

from fcode import (
    Controller,
    Direction,
    EntityType,
    Environment,
    Position,
    ResourceType,
    Team,
)

from utils.common import (
    CARDINAL_DIRECTIONS,
    COMPASS_DIRECTIONS,
    LAUNCH_SETUP_ROUNDS,
    MAX_TOTAL_BUILDERS,
    MAX_THROW_DIST_SQ,
    SLOT_BUILDER_ID_START,
    adjacent_positions,
    attacker_count,
    core_footprint,
    core_perimeter,
    core_positions,
    guard_core_conveyor,
    in_bounds,
    infrastructure_builder_count,
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
    sabotage: frozenset[Position] = frozenset()
    sink_conveyor_direction: Direction | None = None


@dataclass(frozen=True, slots=True)
class ConveyorEndpoint:
    conveyor: Position
    turret: Position


@dataclass(frozen=True, slots=True)
class EnemySupplyChain:
    harvester: Position
    conveyors: tuple[Position, ...]


class BuilderMixin:
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # The Core records each Builder ID in a stable slot for its spawn
        # index. Each Builder finds its own slot on its first execution, then
        # retains that role locally for the rest of its life.
        self.spawn_index: int | None = None
        self.is_attacker: bool | None = None

        # Attacker state.
        self.built_a_launcher = False
        self.waiting_launcher_id: int | None = None
        self.waiting_position: Position | None = None
        self.launch_wait_rounds = 0
        self.ignored_launchers: set[int] = set()
        self.enemy_supply_chain: EnemySupplyChain | None = None
        self.supply_takeover_stage = 0
        self.supply_takeover_gunners: tuple[tuple[Position, Direction], ...] | None = (
            None
        )
        self.supply_takeover_gunner_index = 0

        # Infrastructure state.
        self.infrastructure_targets: list[Position] = []
        self.infrastructure_target_index = 0
        self.active_harvester: Position | None = None
        self.conveyor_plan: ConveyorPlan | None = None
        self.conveyor_plan_ready = False
        self.conveyor_index = 0
        self.offensive_gunner_index = 0
        self.survey_waypoint_index = 0
        self.guard_position: Position | None = None

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
        builder_id = ct.get_id()
        total_slots = MAX_TOTAL_BUILDERS
        spawn_index = next(
            (
                index
                for index in range(total_slots)
                if ct.read_store(SLOT_BUILDER_ID_START + index) == builder_id
            ),
            None,
        )
        if spawn_index is None:
            raise RuntimeError(
                f"Builder Bot {builder_id} is missing from the spawn registry"
            )
        attackers = attacker_count(ct, km)
        is_attacker = spawn_index < attackers
        self.spawn_index = spawn_index
        self.is_attacker = is_attacker

        if not is_attacker:
            my_core, _ = core_positions(ct, km)
            infrastructure_index = spawn_index - attackers
            if infrastructure_index < 0:
                raise RuntimeError("Infrastructure bot received an attacker spawn index")
            ores = ordered_ores(km, my_core)
            infrastructure_count = infrastructure_builder_count(ct, km)
            self.infrastructure_targets = ores[infrastructure_index::infrastructure_count]

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

        if self._seek_satisfying_gunner_endpoint(ct, km, enemy_core):
            return
        if self._seek_conveyor_endpoint(ct, km, enemy_core):
            return
        if self._run_enemy_supply_takeover(ct, km, enemy_core):
            return
        self._move_toward(ct, km, set(core_perimeter(enemy_core)))

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

    def _seek_satisfying_gunner_endpoint(
        self, ct: Controller, km: KnownMap, enemy_core: Position
    ) -> bool:
        """Pursue an open conveyor output from which a Gunner can hit the Core."""

        current = ct.get_position()
        enemy_tiles = core_footprint(enemy_core)
        fed_conveyors = self._fed_conveyors()
        candidates: list[
            tuple[tuple[int, int, int, int, int], ConveyorEndpoint, Direction]
        ] = []
        for endpoint in self._visible_conveyor_endpoints(ct, km):
            facing = self._gunner_facing_toward_core(
                km, endpoint.turret, enemy_tiles
            )
            if facing is None:
                continue
            distance = path_distance(
                km, current, adjacent_positions(km, endpoint.turret)
            )
            if distance is not None:
                candidates.append(
                    (
                        self._gunner_endpoint_priority(
                            endpoint,
                            fed_conveyors,
                            enemy_tiles,
                            distance,
                        ),
                        endpoint,
                        facing,
                    )
                )

        if not candidates:
            return False
        _, endpoint, facing = min(candidates, key=lambda item: item[0])
        if current not in adjacent_positions(km, endpoint.turret):
            self._move_toward(ct, km, adjacent_positions(km, endpoint.turret))
            return True
        if ct.get_action_cooldown() != 0:
            return True
        if ct.can_build_gunner(endpoint.turret, facing):
            ct.build_gunner(endpoint.turret, facing)
            return True
        return False

    @staticmethod
    def _gunner_endpoint_priority(
        endpoint: ConveyorEndpoint,
        fed_conveyors: set[Position],
        enemy_core_tiles: set[Position],
        walking_distance: int,
    ) -> tuple[int, int, int, int, int]:
        return (
            0 if endpoint.conveyor in fed_conveyors else 1,
            min(
                endpoint.turret.distance_squared(core_tile)
                for core_tile in enemy_core_tiles
            ),
            walking_distance,
            endpoint.turret.y,
            endpoint.turret.x,
        )

    def _fed_conveyors(self) -> set[Position]:
        """Conveyors connected to any Harvester or observed titanium."""

        conveyors = {
            position: tile.building
            for position, tile in self.map.items()
            if tile.building is not None
            and tile.building.entity_type == EntityType.CONVEYOR
            and tile.building.direction in CARDINAL_DIRECTIONS
        }
        harvesters = {
            position
            for position, tile in self.map.items()
            if tile.building is not None
            and tile.building.entity_type == EntityType.HARVESTER
        }

        fed: set[Position] = set()
        queue: deque[Position] = deque()
        for position, building in conveyors.items():
            input_positions = {
                position.add(direction)
                for direction in CARDINAL_DIRECTIONS
                if position.add(direction) != position.add(building.direction)
            }
            if harvesters.intersection(input_positions) or (
                getattr(building, "stored_resource", None)
                == ResourceType.TITANIUM
            ):
                fed.add(position)
                queue.append(position)

        while queue:
            position = queue.popleft()
            building = conveyors[position]
            output = position.add(building.direction)
            downstream = conveyors.get(output)
            if downstream is None or output in fed:
                continue
            # A Conveyor does not accept input from its own output side.
            if position == output.add(downstream.direction):
                continue
            fed.add(output)
            queue.append(output)
        return fed

    def _run_enemy_supply_takeover(
        self, ct: Controller, km: KnownMap, enemy_core: Position
    ) -> bool:
        """Capture a complete enemy Harvester-to-Core conveyor supply line."""

        if self.enemy_supply_chain is None:
            chains = self._supply_chains_to_core(core_footprint(enemy_core))
            viable = [
                chain
                for chain in chains
                if self._gunner_facing_toward_core(
                    km, chain.conveyors[-1], core_footprint(enemy_core)
                )
                is not None
            ]
            if not viable:
                return False
            current = ct.get_position()

            def takeover_distance(chain: EnemySupplyChain) -> int:
                distance = path_distance(km, current, {chain.conveyors[-1]})
                return distance if distance is not None else 10**9

            self.enemy_supply_chain = min(
                viable,
                key=lambda chain: (
                    takeover_distance(chain),
                    len(chain.conveyors),
                    chain.conveyors[-1].y,
                    chain.conveyors[-1].x,
                ),
            )
            self.supply_takeover_stage = 0
            self.supply_takeover_gunners = None
            self.supply_takeover_gunner_index = 0

        chain = self.enemy_supply_chain
        if self.supply_takeover_stage == 0:
            return self._replace_final_conveyor_with_gunner(
                ct, km, chain, enemy_core
            )
        if self.supply_takeover_stage == 1:
            return self._replace_penultimate_conveyor_with_splitter(
                ct, km, chain, enemy_core
            )
        if self.supply_takeover_stage == 2:
            return self._build_supply_takeover_gunners(
                ct, km, chain, enemy_core
            )
        return False

    def _replace_final_conveyor_with_gunner(
        self,
        ct: Controller,
        km: KnownMap,
        chain: EnemySupplyChain,
        enemy_core: Position,
    ) -> bool:
        target = chain.conveyors[-1]
        facing = self._gunner_facing_toward_core(
            km, target, core_footprint(enemy_core)
        )
        if facing is None:
            self._clear_supply_takeover()
            return False

        building_id = self._visible_building_id(ct, km, target)
        if building_id is None:
            if not ct.is_in_vision(target):
                return self._move_toward(ct, km, {target})
            return self._build_takeover_building(
                ct,
                km,
                target,
                lambda: ct.can_build_gunner(target, facing),
                lambda: ct.build_gunner(target, facing),
            )

        # A defender can deny sabotage simply by parking a Builder Bot on the
        # walkable final Conveyor. Do not deadlock trying to enter that tile:
        # cut the penultimate Conveyor instead, replace it with the Splitter,
        # and feed the same core-facing battery one tile farther upstream.
        occupying_bot = ct.get_tile_builder_bot_id(target)
        if (
            occupying_bot is not None
            and ct.get_team(occupying_bot) != ct.get_team()
            and len(chain.conveyors) >= 2
        ):
            self.supply_takeover_stage = 1
            return True

        if (
            ct.get_team(building_id) == ct.get_team()
            and ct.get_entity_type(building_id) == EntityType.GUNNER
            and ct.get_direction(building_id) == facing
        ):
            self.supply_takeover_stage = 1
            return True
        if ct.get_entity_type(building_id) != EntityType.CONVEYOR:
            self._clear_supply_takeover()
            return False
        return self._remove_conveyor(ct, km, target, building_id)

    def _replace_penultimate_conveyor_with_splitter(
        self,
        ct: Controller,
        km: KnownMap,
        chain: EnemySupplyChain,
        enemy_core: Position,
    ) -> bool:
        if len(chain.conveyors) < 2:
            self.supply_takeover_stage = 3
            return False

        target = chain.conveyors[-2]
        predecessor = (
            chain.harvester
            if len(chain.conveyors) == 2
            else chain.conveyors[-3]
        )
        direction = predecessor.direction_to(target)
        if direction not in CARDINAL_DIRECTIONS:
            self._clear_supply_takeover()
            return False

        building_id = self._visible_building_id(ct, km, target)
        if building_id is None:
            if not ct.is_in_vision(target):
                return self._move_toward(ct, km, {target})
            return self._build_takeover_building(
                ct,
                km,
                target,
                lambda: ct.can_build_splitter(target, direction),
                lambda: ct.build_splitter(target, direction),
            )

        if (
            ct.get_team(building_id) == ct.get_team()
            and ct.get_entity_type(building_id) == EntityType.SPLITTER
            and ct.get_direction(building_id) == direction
        ):
            self.supply_takeover_stage = 2
            self.supply_takeover_gunners = None
            return True
        if ct.get_entity_type(building_id) != EntityType.CONVEYOR:
            self._clear_supply_takeover()
            return False
        return self._remove_conveyor(ct, km, target, building_id)

    def _build_supply_takeover_gunners(
        self,
        ct: Controller,
        km: KnownMap,
        chain: EnemySupplyChain,
        enemy_core: Position,
    ) -> bool:
        splitter = chain.conveyors[-2]
        predecessor = (
            chain.harvester
            if len(chain.conveyors) == 2
            else chain.conveyors[-3]
        )
        if self.supply_takeover_gunners is None:
            blocked = {
                position
                for position, tile in self.map.items()
                if tile.building is not None
            }
            self.supply_takeover_gunners = self._offensive_gunner_layout(
                km,
                splitter,
                predecessor,
                core_footprint(enemy_core),
                blocked,
            )
            self.supply_takeover_gunner_index = 0

        gunners = self.supply_takeover_gunners
        while self.supply_takeover_gunner_index < len(gunners):
            position, facing = gunners[self.supply_takeover_gunner_index]
            if not ct.is_in_vision(position):
                return self._move_toward(
                    ct, km, adjacent_positions(km, position)
                )
            building_id = ct.get_tile_building_id(position)
            if building_id is not None:
                self.supply_takeover_gunner_index += 1
                continue
            acted = self._build_takeover_building(
                ct,
                km,
                position,
                lambda: ct.can_build_gunner(position, facing),
                lambda: ct.build_gunner(position, facing),
            )
            if acted:
                return True
            return False

        self.supply_takeover_stage = 3
        return False

    def _build_takeover_building(
        self,
        ct: Controller,
        km: KnownMap,
        target: Position,
        can_build: Callable[[], bool],
        build: Callable[[], int],
    ) -> bool:
        build_positions = adjacent_positions(km, target)
        if ct.get_position() not in build_positions:
            return self._move_toward(ct, km, build_positions)
        if ct.get_action_cooldown() != 0:
            return True
        if can_build():
            build()
        return True

    def _sabotage_enemy_conveyor(
        self, ct: Controller, km: KnownMap, target: Position
    ) -> bool:
        if ct.get_position() != target:
            return self._move_toward(ct, km, {target})
        if ct.get_action_cooldown() == 0 and ct.can_fire(target):
            ct.fire(target)
        return True

    def _remove_conveyor(
        self, ct: Controller, km: KnownMap, target: Position, building_id: int
    ) -> bool:
        """Clear a Conveyor; only the required engine action depends on owner."""

        if ct.get_team(building_id) != ct.get_team():
            return self._sabotage_enemy_conveyor(ct, km, target)
        build_positions = adjacent_positions(km, target)
        if ct.get_position() not in build_positions:
            return self._move_toward(ct, km, build_positions)
        if ct.can_destroy(target):
            ct.destroy(target)
        return True

    @staticmethod
    def _visible_building_id(
        ct: Controller, km: KnownMap, position: Position
    ) -> int | None:
        if not in_bounds(km, position) or not ct.is_in_vision(position):
            return None
        return ct.get_tile_building_id(position)

    def _clear_supply_takeover(self) -> None:
        self.enemy_supply_chain = None
        self.supply_takeover_stage = 0
        self.supply_takeover_gunners = None
        self.supply_takeover_gunner_index = 0

    def _supply_chains_to_core(
        self, core_tiles: set[Position]
    ) -> list[EnemySupplyChain]:
        """Return discovered directed Conveyor paths into the given Core."""

        conveyors = {
            position: tile.building
            for position, tile in self.map.items()
            if tile.building is not None
            and tile.building.entity_type == EntityType.CONVEYOR
            and tile.building.direction in CARDINAL_DIRECTIONS
        }
        harvesters = {
            position
            for position, tile in self.map.items()
            if tile.building is not None
            and tile.building.entity_type == EntityType.HARVESTER
        }
        predecessors: dict[Position, list[Position]] = {}
        for position, building in conveyors.items():
            output = position.add(building.direction)
            predecessors.setdefault(output, []).append(position)

        chains: list[EnemySupplyChain] = []
        finals = sorted(
            (
                position
                for position, building in conveyors.items()
                if position.add(building.direction) in core_tiles
            ),
            key=lambda position: (position.y, position.x),
        )
        for final in finals:
            stack: list[tuple[Position, tuple[Position, ...]]] = [
                (final, (final,))
            ]
            while stack:
                current, reversed_chain = stack.pop()
                current_building = conveyors[current]
                input_positions = [
                    current.add(direction)
                    for direction in CARDINAL_DIRECTIONS
                    if current.add(direction)
                    != current.add(current_building.direction)
                ]
                source_harvesters = sorted(
                    harvesters.intersection(input_positions),
                    key=lambda position: (position.y, position.x),
                )
                if source_harvesters:
                    chains.append(
                        EnemySupplyChain(
                            source_harvesters[0],
                            tuple(reversed(reversed_chain)),
                        )
                    )
                    break

                for predecessor in sorted(
                    predecessors.get(current, []),
                    key=lambda position: (position.y, position.x),
                    reverse=True,
                ):
                    if (
                        predecessor not in reversed_chain
                        and predecessor in input_positions
                    ):
                        stack.append(
                            (predecessor, (*reversed_chain, predecessor))
                        )
        return chains

    def _seek_conveyor_endpoint(
        self, ct: Controller, km: KnownMap, enemy_core: Position
    ) -> bool:
        endpoints = self._visible_conveyor_endpoints(ct, km)
        if not endpoints:
            return False

        current = ct.get_position()

        def endpoint_distance(endpoint: ConveyorEndpoint) -> int:
            distance = path_distance(
                km, current, adjacent_positions(km, endpoint.turret)
            )
            return distance if distance is not None else 10**9

        reachable_endpoints = [
            endpoint for endpoint in endpoints if endpoint_distance(endpoint) < 10**9
        ]
        if not reachable_endpoints:
            return False
        reachable_endpoints.sort(
            key=lambda endpoint: (
                endpoint_distance(endpoint),
                endpoint.turret.distance_squared(enemy_core),
                endpoint.turret.y,
                endpoint.turret.x,
            )
        )
        endpoint = reachable_endpoints[0]
        build_positions = adjacent_positions(km, endpoint.turret)
        if current not in build_positions:
            self._move_toward(ct, km, build_positions)
            return True
        if ct.get_action_cooldown() != 0:
            return True

        facing = self._sentinel_facing(ct, endpoint, enemy_core)
        if facing is not None and ct.can_build_sentinel(endpoint.turret, facing):
            ct.build_sentinel(endpoint.turret, facing)
            return True
        return False

    def _visible_conveyor_endpoints(
        self, ct: Controller, km: KnownMap
    ) -> list[ConveyorEndpoint]:
        endpoints: list[ConveyorEndpoint] = []
        for position, tile in self.map.items():
            building = tile.building
            if (
                tile.rounds_since_last_seen != 0
                or building is None
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
        if self.guard_position is not None:
            if ct.get_position() != self.guard_position:
                self._move_toward(ct, km, {self.guard_position})
            return

        if self.infrastructure_target_index >= len(self.infrastructure_targets):
            self._run_infrastructure_survey(ct, km)
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
                my_core, _ = core_positions(ct, km)
                if (
                    self.conveyor_plan.positions
                    and self.conveyor_plan.sink in core_footprint(my_core)
                    and guard_core_conveyor(ct, km)
                ):
                    self.guard_position = self.conveyor_plan.positions[-1]
                    if ct.get_position() != self.guard_position:
                        self._move_toward(ct, km, {self.guard_position})
                else:
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
            if ct.get_entity_type(building_id) == EntityType.HARVESTER:
                self.active_harvester = target
            else:
                self._advance_infrastructure_target()
            return
        if ct.get_action_cooldown() == 0 and ct.can_build_harvester(target):
            ct.build_harvester(target)
            self.active_harvester = target

    def _run_infrastructure_survey(self, ct: Controller, km: KnownMap) -> None:
        """Survey for abandoned or enemy ore supplies and route them home."""

        if self.conveyor_plan_ready:
            if self.conveyor_plan is None:
                self._invalidate_conveyor_plan()
                return
            if self._build_conveyor_plan(ct, km):
                self._invalidate_conveyor_plan()
            return

        plan = self._plan_survey_recovery(ct, km)
        if plan is not None:
            self.conveyor_plan = plan
            self.conveyor_plan_ready = True
            self.conveyor_index = 0
            if self._build_conveyor_plan(ct, km):
                self._invalidate_conveyor_plan()
            return

        self._survey_map(ct, km)

    def _plan_survey_recovery(
        self, ct: Controller, km: KnownMap
    ) -> ConveyorPlan | None:
        """Plan a home route for a visible dangling line or unused Harvester."""

        my_core, _ = core_positions(ct, km)
        core_tiles = core_footprint(my_core)
        connected = self._core_connected_conveyors(core_tiles)
        current = ct.get_position()
        candidates: list[
            tuple[int, int, int, int, Position, tuple[Position, ...] | None]
        ] = []

        # Preserve work already done: continue from the open output of a
        # visible line before starting another line at its Harvester.
        for position in self._conveyors() - connected:
            tile = self.map[position]
            building = tile.building
            if (
                tile.rounds_since_last_seen != 0
                or building is None
                or building.direction not in CARDINAL_DIRECTIONS
            ):
                continue
            output = position.add(building.direction)
            output_tile = self.map.get(output)
            if (
                not static_bot_passable(km, output)
                or output_tile is None
                or output_tile.rounds_since_last_seen != 0
                or output_tile.building is not None
            ):
                continue
            distance = path_distance(km, current, adjacent_positions(km, output))
            if distance is not None:
                candidates.append(
                    (0, distance, position.y, position.x, position, (output,))
                )

        for position, tile in self.map.items():
            building = tile.building
            if (
                tile.rounds_since_last_seen != 0
                or building is None
                or building.entity_type != EntityType.HARVESTER
                or self._source_feeds_connected_line(position, connected)
            ):
                continue
            distance = path_distance(km, current, adjacent_positions(km, position))
            if distance is None:
                continue
            candidates.append(
                (1, distance, position.y, position.x, position, None)
            )

        for _, _, _, _, source, starts in sorted(candidates):
            plan = self._plan_conveyors(ct, km, source, starts=starts)
            if plan is not None and plan.positions:
                return plan
        return None

    def _source_feeds_connected_line(
        self, source: Position, connected: set[Position]
    ) -> bool:
        for conveyor_position in connected:
            if (
                abs(source.x - conveyor_position.x)
                + abs(source.y - conveyor_position.y)
                != 1
            ):
                continue
            building = self.map[conveyor_position].building
            if (
                building is not None
                and source != conveyor_position.add(building.direction)
            ):
                return True
        return False

    def _survey_map(self, ct: Controller, km: KnownMap) -> None:
        """Walk a sparse serpentine grid whose vision discs cover the map."""

        rows = list(range(1, km.height, 4))
        columns = list(range(1, km.width, 4))
        waypoints: list[Position] = []
        for row_index, y in enumerate(rows):
            xs = columns if row_index % 2 == 0 else list(reversed(columns))
            waypoints.extend(
                Position(x, y)
                for x in xs
                if static_bot_passable(km, Position(x, y))
            )
        if not waypoints:
            return
        if self.survey_waypoint_index == 0 and self.spawn_index is not None:
            attackers = attacker_count(ct, km)
            infrastructure_count = infrastructure_builder_count(ct, km)
            infrastructure_index = max(0, self.spawn_index - attackers)
            self.survey_waypoint_index = (
                infrastructure_index * len(waypoints) // infrastructure_count
            )
        waypoint = waypoints[self.survey_waypoint_index % len(waypoints)]
        if ct.get_position().distance_squared(waypoint) <= 2:
            self.survey_waypoint_index = (self.survey_waypoint_index + 1) % len(
                waypoints
            )
            waypoint = waypoints[self.survey_waypoint_index]
        self._move_toward(ct, km, {waypoint})

    def _plan_conveyors(
        self,
        ct: Controller,
        km: KnownMap,
        harvester: Position,
        *,
        starts: tuple[Position, ...] | None = None,
    ) -> ConveyorPlan | None:
        my_core, _ = core_positions(ct, km)
        core_tiles = core_footprint(my_core)
        connected_conveyors = self._core_connected_conveyors(core_tiles)
        conveyor_directions = {
            position: self.map[position].building.direction
            for position in connected_conveyors
            if self.map[position].building is not None
        }
        blocked = {
            position
            for position, tile in self.map.items()
            if tile.occupancy_known and tile.building is not None
        }
        blocked |= set(km.cores)
        blocking_conveyors = self._conveyors() - connected_conveyors

        # Prefer joining the nearest connected line, provided doing so never
        # sends titanium farther away from our Core. This prevents two
        # unfinished lines from turning toward one another. If the connected
        # route fails that check, use the shortest direct route to the Core.
        if connected_conveyors:
            connected_plan = self._plan_route_with_optional_sabotage(
                km,
                harvester,
                connected_conveyors,
                conveyor_directions,
                blocked,
                blocking_conveyors,
                starts=starts,
            )
            if connected_plan is not None:
                sink_direction = conveyor_directions[connected_plan.sink]
                sink_output = connected_plan.sink.add(sink_direction)
                if self._plan_moves_toward_targets(
                    harvester, connected_plan, core_tiles
                ) and self._target_distance(
                    sink_output, core_tiles
                ) < self._target_distance(connected_plan.sink, core_tiles):
                    return connected_plan

        return self._plan_route_with_optional_sabotage(
            km,
            harvester,
            core_tiles,
            {},
            blocked,
            blocking_conveyors,
            starts=starts,
        )

    def _plan_route_with_optional_sabotage(
        self,
        km: KnownMap,
        source_building: Position,
        sinks: set[Position],
        sink_directions: dict[Position, Direction],
        blocked: set[Position],
        blocking_conveyors: set[Position],
        *,
        starts: tuple[Position, ...] | None = None,
    ) -> ConveyorPlan | None:
        avoiding = self._plan_conveyor_path(
            km,
            source_building,
            sinks,
            sink_directions,
            blocked,
            starts=starts,
        )
        if not blocking_conveyors:
            return avoiding

        through_conveyors = self._plan_conveyor_path(
            km,
            source_building,
            sinks,
            sink_directions,
            blocked - blocking_conveyors,
            starts=starts,
        )
        if through_conveyors is None:
            return avoiding
        sabotage = frozenset(through_conveyors.positions).intersection(
            blocking_conveyors
        )
        if not sabotage:
            return through_conveyors
        if avoiding is not None and len(avoiding.positions) <= len(
            through_conveyors.positions
        ) + 5:
            return avoiding
        return ConveyorPlan(
            through_conveyors.positions,
            through_conveyors.sink,
            sabotage=sabotage,
            sink_conveyor_direction=through_conveyors.sink_conveyor_direction,
        )

    def _plan_conveyor_path(
        self,
        km: KnownMap,
        source_building: Position,
        sinks: set[Position],
        sink_directions: dict[Position, Direction],
        blocked: set[Position],
        *,
        starts: tuple[Position, ...] | None = None,
    ) -> ConveyorPlan | None:
        """Prefer a route using no ore tiles, falling back only if required."""

        ore_tiles = {
            Position(x, y)
            for y, row in enumerate(km.environments)
            for x, environment in enumerate(row)
            if environment == Environment.ORE_TITANIUM
        }
        avoiding_ore = self._plan_conveyor_path_bfs(
            km,
            source_building,
            sinks,
            sink_directions,
            blocked | ore_tiles,
            starts=starts,
        )
        if avoiding_ore is not None:
            return avoiding_ore
        return self._plan_conveyor_path_bfs(
            km,
            source_building,
            sinks,
            sink_directions,
            blocked,
            starts=starts,
        )

    def _plan_conveyor_path_bfs(
        self,
        km: KnownMap,
        source_building: Position,
        sinks: set[Position],
        sink_directions: dict[Position, Direction],
        blocked: set[Position],
        *,
        starts: tuple[Position, ...] | None = None,
    ) -> ConveyorPlan | None:
        """Return the shortest cardinal conveyor path to an accepted sink."""

        def accepts(source: Position, sink: Position) -> bool:
            if abs(source.x - sink.x) + abs(source.y - sink.y) != 1:
                return False
            direction = sink_directions.get(sink)
            return direction is None or source != sink.add(direction)

        ordered_sinks = sorted(sinks, key=lambda position: (position.y, position.x))
        if starts is None:
            for sink in ordered_sinks:
                if accepts(source_building, sink):
                    return ConveyorPlan(
                        (),
                        sink,
                        sink_conveyor_direction=sink_directions.get(sink),
                    )

        previous: dict[Position, Position | None] = {}
        queue: deque[Position] = deque()
        candidates = (
            starts
            if starts is not None
            else tuple(
                source_building.add(direction) for direction in CARDINAL_DIRECTIONS
            )
        )
        for candidate in candidates:
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
        return ConveyorPlan(
            tuple(path),
            reached_sink,
            sink_conveyor_direction=sink_directions.get(reached_sink),
        )

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
        self,
        ct: Controller,
        km: KnownMap,
        harvester: Position,
        *,
        allow_ore: bool = False,
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
        if not allow_ore:
            blocked |= {
                Position(x, y)
                for y, row in enumerate(km.environments)
                for x, environment in enumerate(row)
                if environment == Environment.ORE_TITANIUM
            }

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
            if not allow_ore:
                return self._plan_offensive_conveyors(
                    ct, km, harvester, allow_ore=True
                )
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
        if not allow_ore:
            return self._plan_offensive_conveyors(
                ct, km, harvester, allow_ore=True
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

    def _conveyors(self) -> set[Position]:
        return {
            position
            for position, tile in self.map.items()
            if tile.building is not None
            and tile.building.entity_type == EntityType.CONVEYOR
            and tile.building.direction in CARDINAL_DIRECTIONS
        }

    def _core_connected_conveyors(
        self, core_tiles: set[Position]
    ) -> set[Position]:
        """Return conveyors whose directed output chain reaches our Core.

        An unfinished line must not become its own routing destination after a
        replan. Work backward from conveyors that output directly into the Core
        so cycles and dangling chains are excluded. Team ownership is irrelevant:
        mixed Conveyor chains transport resources normally.
        """

        conveyors = {
            position: self.map[position].building
            for position in self._conveyors()
            if self.map[position].building is not None
        }
        connected: set[Position] = set()
        changed = True
        while changed:
            changed = False
            for position, building in conveyors.items():
                if position in connected:
                    continue
                output = position.add(building.direction)
                if output in core_tiles:
                    connected.add(position)
                    changed = True
                    continue
                downstream = conveyors.get(output)
                if (
                    output in connected
                    and downstream is not None
                    and position != output.add(downstream.direction)
                ):
                    connected.add(position)
                    changed = True
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
        if self._conveyor_plan_is_broken(plan):
            self._invalidate_conveyor_plan()
            return False

        conveyor_position = plan.positions[self.conveyor_index]
        output = (
            plan.positions[self.conveyor_index + 1]
            if self.conveyor_index + 1 < len(plan.positions)
            else plan.sink
        )
        direction = conveyor_position.direction_to(output)
        if direction not in CARDINAL_DIRECTIONS:
            raise RuntimeError("Conveyor plan contains a non-cardinal segment")

        if not ct.is_in_vision(conveyor_position):
            self._move_toward(
                ct, km, adjacent_positions(km, conveyor_position)
            )
            return False

        existing_id = ct.get_tile_building_id(conveyor_position)
        if (
            conveyor_position in plan.sabotage
            and existing_id is not None
            and ct.get_entity_type(existing_id) == EntityType.CONVEYOR
        ):
            if ct.get_direction(existing_id) == direction:
                self.conveyor_index += 1
                return self.conveyor_index >= len(plan.positions)
            if ct.get_team(existing_id) == ct.get_team():
                build_positions = adjacent_positions(km, conveyor_position)
                if ct.get_position() not in build_positions:
                    self._move_toward(ct, km, build_positions)
                elif ct.can_destroy(conveyor_position):
                    ct.destroy(conveyor_position)
            elif ct.get_position() != conveyor_position:
                self._move_toward(ct, km, {conveyor_position})
            elif ct.get_action_cooldown() == 0 and ct.can_fire(conveyor_position):
                ct.fire(conveyor_position)
            return False

        current = ct.get_position()
        build_positions = adjacent_positions(km, conveyor_position)
        if current not in build_positions:
            self._move_toward(ct, km, build_positions)
            return False

        existing_id = ct.get_tile_building_id(conveyor_position)
        if existing_id is not None:
            if (
                ct.get_entity_type(existing_id) == EntityType.CONVEYOR
                and ct.get_direction(existing_id) == direction
            ):
                self.conveyor_index += 1
                return self.conveyor_index >= len(plan.positions)
            self._invalidate_conveyor_plan()
            return False

        if ct.get_action_cooldown() == 0 and ct.can_build_conveyor(
            conveyor_position, direction
        ):
            ct.build_conveyor(conveyor_position, direction)
            self.conveyor_index += 1
            return self.conveyor_index >= len(plan.positions)
        return False

    def _conveyor_plan_is_broken(self, plan: ConveyorPlan) -> bool:
        if plan.sink_conveyor_direction is not None:
            sink_tile = self.map.get(plan.sink)
            if sink_tile is not None and sink_tile.rounds_since_last_seen == 0:
                sink_building = sink_tile.building
                if not (
                    sink_building is not None
                    and sink_building.entity_type == EntityType.CONVEYOR
                    and sink_building.direction == plan.sink_conveyor_direction
                ):
                    return True

        for index in range(self.conveyor_index, len(plan.positions)):
            position = plan.positions[index]
            tile = self.map.get(position)
            if (
                tile is None
                or tile.rounds_since_last_seen != 0
                or tile.building is None
            ):
                continue
            building = tile.building
            if (
                position in plan.sabotage
                and building.entity_type == EntityType.CONVEYOR
            ):
                continue
            output = (
                plan.positions[index + 1]
                if index + 1 < len(plan.positions)
                else plan.sink
            )
            expected_direction = position.direction_to(output)
            if (
                building.entity_type == EntityType.CONVEYOR
                and building.direction == expected_direction
            ):
                continue
            return True
        return False

    def _invalidate_conveyor_plan(self) -> None:
        self.conveyor_plan = None
        self.conveyor_plan_ready = False
        self.conveyor_index = 0

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
