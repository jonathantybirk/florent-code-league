"""Dependency-free inputs and outputs for economic harassment planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Mapping, Protocol

Tile = tuple[int, int]


class StructureKind(Enum):
    CORE = auto()
    HARVESTER = auto()
    CONVEYOR = auto()
    SPLITTER = auto()
    BARRIER = auto()
    GUNNER = auto()
    SENTINEL = auto()
    LAUNCHER = auto()
    BUILDER = auto()


class Owner(Enum):
    OURS = auto()
    ENEMY = auto()
    NEUTRAL = auto()


class KnowledgeState(Enum):
    UNREVEALED = auto()
    REVEALED = auto()
    VISIBLE = auto()


class ApproachKind(Enum):
    WALK = auto()
    EXISTING_LAUNCHER = auto()
    BUILD_LAUNCHER = auto()


class HarassmentActionType(Enum):
    MOVE = auto()
    ATTACK = auto()
    BUILD_BARRIER = auto()
    WAIT = auto()
    REPORT_COMPLETE = auto()
    REQUEST_REPLAN = auto()
    RELEASE_TO_GLOBAL_ASSIGNMENT = auto()


@dataclass(frozen=True)
class RouteEstimate:
    tiles: tuple[Tile, ...]
    eta: int | None = None
    approach: ApproachKind = ApproachKind.WALK

    @property
    def travel_time(self) -> int:
        return self.eta if self.eta is not None else max(0, len(self.tiles) - 1)


class PathOracle(Protocol):
    def route(self, start: Tile, goal: Tile) -> RouteEstimate | None: ...


@dataclass(frozen=True)
class EnemyEconomyNode:
    """A caller-normalised node in the enemy's directed resource graph."""

    position: Tile
    kind: StructureKind
    output_tiles: tuple[Tile, ...] = ()
    hp: int | None = None
    production_per_round: float = 0.0
    confidence: float = 1.0


@dataclass(frozen=True)
class Occupant:
    kind: StructureKind
    owner: Owner
    hp: int | None = None


@dataclass(frozen=True)
class BuilderSnapshot:
    entity_id: int
    spawn_index: int
    position: Tile
    hp: int
    available_for_harassment: bool = True
    current_job_id: int | None = None


@dataclass(frozen=True)
class HarassmentConstraints:
    enabled: bool = True
    barrier_build_allowed: bool = True
    forbidden_tiles: frozenset[Tile] = frozenset()


@dataclass(frozen=True)
class HarassmentPolicy:
    denial_horizon: int = 20
    flow_value_weight: int = 10
    replacement_cost_conveyor: int = 1
    replacement_cost_splitter: int = 3
    replacement_cost_harvester: int = 5
    replacement_cost_weight: int = 10
    score_scale: int = 100
    attack_damage: int = 10
    default_target_hp: int = 100
    attack_action_rounds: int = 1
    barrier_action_rounds: int = 1
    revealed_confidence_multiplier: float = 0.8
    inferred_confidence_multiplier: float = 0.6
    minimum_confidence: float = 0.1
    minimum_score: int = 1
    followup_radius: int = 5
    followup_candidate_limit: int = 2
    followup_discount_percent: int = 30
    candidate_limit: int = 16
    verbosity: int = 0

    def replacement_cost(self, kind: StructureKind) -> int:
        return {
            StructureKind.CONVEYOR: self.replacement_cost_conveyor,
            StructureKind.SPLITTER: self.replacement_cost_splitter,
            StructureKind.HARVESTER: self.replacement_cost_harvester,
        }.get(kind, 0)


@dataclass(frozen=True)
class HarassmentContext:
    round: int
    map_revision: int
    roster_revision: int
    width: int
    height: int
    builders: tuple[BuilderSnapshot, ...]
    enemy_economy: Mapping[Tile, EnemyEconomyNode]
    enemy_core_inputs: frozenset[Tile]
    occupants: Mapping[Tile, Occupant]
    knowledge: Mapping[Tile, KnowledgeState]
    inferred_tiles: frozenset[Tile]
    buildable_tiles: frozenset[Tile]
    path_oracle: PathOracle
    constraints: HarassmentConstraints = HarassmentConstraints()


@dataclass(frozen=True)
class TargetScore:
    builder_id: int
    target: Tile
    staging_tile: Tile
    route: RouteEstimate
    disrupted_harvesters: tuple[Tile, ...]
    disrupted_flow: float
    replacement_value: int
    confidence: float
    travel_time: int
    attack_turns: int
    completion_time: int
    immediate_value: int
    followup_target: Tile | None
    followup_value: int
    score: int


@dataclass(frozen=True)
class HarassmentJob:
    job_id: int
    target: Tile
    staging_tile: Tile
    route: tuple[Tile, ...]
    target_score: TargetScore


@dataclass(frozen=True)
class HarassmentAssignment:
    builder_id: int
    job_id: int
    assignment_epoch: int


@dataclass(frozen=True)
class HarassmentAction:
    type: HarassmentActionType
    target_tile: Tile | None = None
    reason: str = ""


@dataclass(frozen=True)
class BuilderDirective:
    plan_epoch: int
    builder_id: int
    job_id: int | None
    objective: Tile | None
    primary: HarassmentAction
    fallback: HarassmentAction | None = None


@dataclass(frozen=True)
class DebugEvent:
    level: int
    event: str
    message: str
    data: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class HarassmentPlan:
    epoch: int
    map_revision: int
    roster_revision: int
    targets: tuple[TargetScore, ...]
    jobs: tuple[HarassmentJob, ...]
    assignments: tuple[HarassmentAssignment, ...]
    debug_events: tuple[DebugEvent, ...] = ()

    def job_for_builder(self, builder_id: int) -> HarassmentJob | None:
        assignment = next((a for a in self.assignments if a.builder_id == builder_id), None)
        if assignment is None:
            return None
        return next((j for j in self.jobs if j.job_id == assignment.job_id), None)


DebugSink = Callable[[DebugEvent], None]
