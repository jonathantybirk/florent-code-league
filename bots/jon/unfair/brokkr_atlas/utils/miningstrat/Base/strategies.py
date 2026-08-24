"""Replaceable planning stages for mining strategy variants.

Every field is optional. ``MiningPlanner`` uses its existing deterministic
implementation for fields left as ``None``. A variant can therefore replace
one strategic choice without copying the rest of the planner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .model import (
    BuilderAssignment,
    BuilderSnapshot,
    DepositDecision,
    ExplorationCorridor,
    MiningContext,
    MiningJob,
    MiningPlan,
    PlannedLane,
)

DecisionNote = Callable[..., None]

DepositPlanner = Callable[
    [MiningContext, DecisionNote], tuple[DepositDecision, ...]
]
LanePlanner = Callable[
    [MiningContext, tuple[DepositDecision, ...], DecisionNote],
    tuple[tuple[PlannedLane, ...], tuple[DepositDecision, ...]],
]
JobPlanner = Callable[
    [MiningContext, tuple[PlannedLane, ...], tuple[DepositDecision, ...], DecisionNote],
    tuple[MiningJob, ...],
]
BlindExpansionPlanner = Callable[
    [MiningContext, tuple[PlannedLane, ...], int, DecisionNote],
    tuple[ExplorationCorridor, ...],
]
AssignmentPlanner = Callable[
    [
        MiningContext,
        tuple[MiningJob, ...],
        tuple[BuilderSnapshot, ...],
        int,
        MiningPlan | None,
        DecisionNote,
    ],
    tuple[BuilderAssignment, ...],
]


@dataclass(frozen=True)
class MiningStrategies:
    """Optional overrides for the strategic stages of ``MiningPlanner``.

    Hooks consume and return the same immutable domain objects as the default
    planner. Directive execution, pre-emption reporting, income projection,
    epochs, and debug collection remain shared.
    """

    deposits: DepositPlanner | None = None
    lanes: LanePlanner | None = None
    jobs: JobPlanner | None = None
    blind_expansion: BlindExpansionPlanner | None = None
    assignments: AssignmentPlanner | None = None
