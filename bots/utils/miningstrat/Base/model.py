"""Plain input/output objects for mining expansion.

There is deliberately no ``fcode`` or Controller dependency here. The caller
adapts shared-memory and engine values into these immutable snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Mapping, Protocol

Tile = tuple[int, int]


class KnowledgeState(Enum):
    UNREVEALED = auto()
    REVEALED = auto()
    VISIBLE = auto()


class Terrain(Enum):
    UNKNOWN = auto()
    EMPTY = auto()
    WALL = auto()
    TITANIUM_ORE = auto()


class Owner(Enum):
    OURS = auto()
    ENEMY = auto()
    NEUTRAL = auto()


class BuildingKind(Enum):
    CORE = auto()
    HARVESTER = auto()
    CONVEYOR = auto()
    SPLITTER = auto()
    BARRIER = auto()
    GUNNER = auto()
    SENTINEL = auto()
    LAUNCHER = auto()


class CardinalDirection(Enum):
    NORTH = (0, -1)
    EAST = (1, 0)
    SOUTH = (0, 1)
    WEST = (-1, 0)

    @property
    def delta(self) -> Tile:
        return self.value

    @classmethod
    def between(cls, source: Tile, target: Tile) -> CardinalDirection:
        delta = target[0] - source[0], target[1] - source[1]
        for direction in cls:
            if direction.value == delta:
                return direction
        raise ValueError(f"tiles are not cardinal neighbours: {source} -> {target}")


class BlindExpansionMode(Enum):
    SCOUT_THEN_BACKFILL = auto()
    BUILD_CORE_STUBS = auto()
    BUILD_CONFIDENT_CORRIDORS = auto()


class DepositDisposition(Enum):
    ACCEPTED = auto()
    DEFERRED_EXPANSION_DISABLED = auto()
    DEFERRED_TOO_EXPENSIVE = auto()
    DEFERRED_CONTESTED = auto()
    DEFERRED_LANE_FULL = auto()
    NO_ROUTE = auto()
    ALREADY_HARVESTED_US = auto()
    ENEMY_CONTROLLED = auto()


class JobType(Enum):
    BUILD_HARVESTER = auto()
    EXTEND_LANE = auto()
    EXPLORE_CORRIDOR = auto()


class MiningActionType(Enum):
    MOVE = auto()
    BUILD_CONVEYOR = auto()
    BUILD_HARVESTER = auto()
    WAIT = auto()
    REPORT_COMPLETE = auto()
    RELEASE_TO_GLOBAL_ASSIGNMENT = auto()


@dataclass(frozen=True)
class BuildingSnapshot:
    kind: BuildingKind
    owner: Owner
    direction: CardinalDirection | None = None
    entity_id: int | None = None
    hp: int | None = None


@dataclass(frozen=True)
class WorldTile:
    position: Tile
    knowledge: KnowledgeState
    terrain: Terrain = Terrain.UNKNOWN
    building: BuildingSnapshot | None = None
    last_observed_round: int | None = None
    inferred: bool = False


@dataclass(frozen=True)
class RouteEstimate:
    """A route supplied by pathfinding, including both endpoints."""

    tiles: tuple[Tile, ...]
    unrevealed_tiles: int = 0
    stale_tiles: int = 0

    @property
    def total_length(self) -> int:
        return max(0, len(self.tiles) - 1)


class PathOracle(Protocol):
    def route(self, start: Tile, goal: Tile) -> RouteEstimate | None: ...

    def distance(self, start: Tile, goal: Tile) -> int | None: ...


@dataclass(frozen=True)
class BuilderSnapshot:
    entity_id: int
    spawn_index: int
    position: Tile
    hp: int
    available_for_mining: bool = True
    current_assignment: int | None = None


@dataclass(frozen=True)
class ExistingLane:
    lane_id: int
    core_input: Tile
    conveyor_tiles: tuple[Tile, ...] = ()
    harvester_tiles: tuple[Tile, ...] = ()
    operational_expected_flow: float = 0.0
    actual_observed_flow: float | None = None


@dataclass(frozen=True)
class ConstructionCosts:
    conveyor: int
    harvester: int
    builder: int = 0


@dataclass(frozen=True)
class EconomySnapshot:
    titanium: int
    costs: ConstructionCosts
    minimum_reserve: int = 0
    passive_income_schedule: tuple[int, ...] = ()
    operational_expected_flow: float = 0.0
    actual_observed_flow: float | None = None


@dataclass(frozen=True)
class MiningConstraints:
    enabled: bool = True
    expansion_allowed: bool = True
    forbidden_tiles: frozenset[Tile] = frozenset()
    maximum_additional_builders: int = 0


@dataclass(frozen=True)
class MiningPolicy:
    """All uncertain strategy choices live here for replay-driven tuning."""

    blind_mode: BlindExpansionMode = BlindExpansionMode.BUILD_CORE_STUBS
    blind_limit_small: int = 2
    blind_limit_medium: int = 3
    blind_limit_large: int = 4
    candidate_heading_limit: int = 4
    candidate_deposit_limit: int = 12

    payoff_horizon: int = 80
    income_value_weight: int = 1
    construction_cost_weight: int = 1
    route_tile_penalty: int = 2
    unrevealed_tile_penalty: int = 2
    stale_tile_penalty: int = 1
    enemy_side_penalty: int = 18
    contention_margin: int = 3
    contention_penalty: int = 5
    territorial_advantage_bonus: int = 1
    existing_network_bonus: int = 4
    shared_route_bonus: int = 3
    acceptance_threshold: int = 0
    always_accept_distance: int = 8

    lane_soft_capacity: int = 4
    lane_hard_capacity: int = 6
    lane_overload_penalty: int = 18
    core_side_diversity_bonus: int = 3

    assignment_switch_penalty: int = 6
    harvester_job_bonus: int = 1_000
    lane_job_bonus: int = 500
    exploration_job_priority: int = 0
    income_schedule_rounds: int = 64
    rounds_per_build_step: int = 2
    verbosity: int = 0

    def blind_limit(self, width: int, height: int) -> int:
        area = width * height
        if area <= 18 * 18:
            return self.blind_limit_small
        if area <= 24 * 24:
            return self.blind_limit_medium
        return self.blind_limit_large


@dataclass(frozen=True)
class MiningContext:
    round: int
    map_revision: int
    roster_revision: int
    width: int
    height: int
    own_core_tiles: tuple[Tile, ...]
    core_inputs: tuple[Tile, ...]
    world: Mapping[Tile, WorldTile]
    path_oracle: PathOracle
    builders: tuple[BuilderSnapshot, ...]
    economy: EconomySnapshot
    existing_lanes: tuple[ExistingLane, ...] = ()
    enemy_core_tiles: tuple[Tile, ...] = ()
    constraints: MiningConstraints = MiningConstraints()


@dataclass(frozen=True)
class DepositDecision:
    tile: Tile
    disposition: DepositDisposition
    score: int
    reason: str
    core_input: Tile | None = None
    route: RouteEstimate | None = None
    our_distance: int | None = None
    enemy_distance: int | None = None
    construction_cost: int = 0


@dataclass(frozen=True)
class ConstructionStep:
    tile: Tile
    direction: CardinalDirection


@dataclass(frozen=True)
class PlannedLane:
    lane_id: int
    core_input: Tile
    deposits: tuple[Tile, ...]
    route_tiles: frozenset[Tile]
    steps_by_deposit: Mapping[Tile, tuple[ConstructionStep, ...]]
    existing: bool = False


@dataclass(frozen=True)
class ExplorationCorridor:
    corridor_id: int
    core_input: Tile
    objective: Tile
    optimistic_route: tuple[Tile, ...]
    committed_steps: tuple[ConstructionStep, ...]
    score: int


@dataclass(frozen=True)
class MiningJob:
    job_id: int
    type: JobType
    priority: int
    objective: Tile
    lane_id: int | None = None
    deposit: Tile | None = None
    construction_steps: tuple[ConstructionStep, ...] = ()
    route: tuple[Tile, ...] = ()


@dataclass(frozen=True)
class BuilderAssignment:
    builder_id: int
    job_id: int
    assignment_epoch: int
    travel_cost: int


@dataclass(frozen=True)
class PreemptionStatus:
    builder_id: int
    can_release_immediately: bool
    turns_to_safe_handoff: int
    unique_critical_job: bool
    objective: Tile | None
    target_value: int


@dataclass(frozen=True)
class PlannedIncome:
    activation_round_by_deposit: Mapping[Tile, int]
    harvester_flow_by_round: tuple[float, ...]
    construction_spend_by_round: tuple[int, ...]


@dataclass(frozen=True)
class CoreMiningDirective:
    desired_total_mining_builders: int
    request_spawn_builder: bool
    next_expected_spend: int
    minimum_reserved_titanium: int
    operational_expected_flow: float
    planned_future_flow: float
    active_lane_count: int
    accepted_deposit_count: int
    assignments: tuple[BuilderAssignment, ...]
    preemption: tuple[PreemptionStatus, ...]


@dataclass(frozen=True)
class MiningAction:
    type: MiningActionType
    target_tile: Tile | None = None
    direction: CardinalDirection | None = None
    reason: str = ""


@dataclass(frozen=True)
class BuilderDirective:
    plan_epoch: int
    builder_id: int
    job_id: int | None
    job_type: JobType | None
    objective: Tile | None
    primary: MiningAction
    fallback: MiningAction | None = None


@dataclass(frozen=True)
class DebugEvent:
    level: int
    event: str
    message: str
    data: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MiningPlan:
    epoch: int
    map_revision: int
    roster_revision: int
    deposit_decisions: tuple[DepositDecision, ...]
    lanes: tuple[PlannedLane, ...]
    corridors: tuple[ExplorationCorridor, ...]
    jobs: tuple[MiningJob, ...]
    assignments: tuple[BuilderAssignment, ...]
    planned_income: PlannedIncome
    core_directive: CoreMiningDirective
    debug_events: tuple[DebugEvent, ...] = ()

    def job_for_builder(self, builder_id: int) -> MiningJob | None:
        assignment = next((a for a in self.assignments if a.builder_id == builder_id), None)
        if assignment is None:
            return None
        return next((job for job in self.jobs if job.job_id == assignment.job_id), None)
