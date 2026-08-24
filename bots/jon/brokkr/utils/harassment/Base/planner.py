"""Bounded planning and execution for Bean-like economic harassment."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable

from .model import (
    BuilderDirective,
    BuilderSnapshot,
    DebugEvent,
    HarassmentAction,
    HarassmentActionType,
    HarassmentAssignment,
    HarassmentContext,
    HarassmentJob,
    HarassmentPlan,
    HarassmentPolicy,
    KnowledgeState,
    Owner,
    RouteEstimate,
    StructureKind,
    TargetScore,
    Tile,
)

_LOG = logging.getLogger(__name__)
_ECONOMY = {StructureKind.CONVEYOR, StructureKind.SPLITTER, StructureKind.HARVESTER}
_DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))


class HarassmentPlanner:
    """Select and coordinate destroy-and-block jobs without issuing engine calls."""

    def __init__(
        self,
        policy: HarassmentPolicy | None = None,
        debug_sink: Callable[[DebugEvent], None] | None = None,
    ) -> None:
        self.policy = policy or HarassmentPolicy()
        self._debug_sink = debug_sink

    def plan(
        self,
        context: HarassmentContext,
        previous_plan: HarassmentPlan | None = None,
    ) -> HarassmentPlan:
        epoch = 1 if previous_plan is None else previous_plan.epoch + 1
        debug: list[DebugEvent] = []

        def note(level: int, event: str, message: str, **data: object) -> None:
            self._record(debug, level, event, message, data)

        builders = tuple(sorted(
            (b for b in context.builders if b.available_for_harassment),
            key=lambda b: (b.spawn_index, b.entity_id),
        ))
        note(1, "plan.start", "planning economic harassment", epoch=epoch,
             builders=[b.entity_id for b in builders], targets=len(context.enemy_economy))
        if not context.constraints.enabled or not builders:
            note(1, "plan.inactive", "harassment disabled or no assigned builders")
            return HarassmentPlan(epoch, context.map_revision, context.roster_revision, (), (), (), tuple(debug))

        remaining = list(builders)
        removed: set[Tile] = set()
        jobs: list[HarassmentJob] = []
        assignments: list[HarassmentAssignment] = []
        considered: dict[tuple[int, Tile], TargetScore] = {}
        disruption_cache: dict[
            tuple[frozenset[Tile], Tile], tuple[tuple[Tile, ...], float]
        ] = {}
        candidate_order = self._rank_candidates(context)

        while remaining:
            candidate_tiles = tuple(
                tile for tile in candidate_order if tile not in removed
            )[: self.policy.candidate_limit]
            target_values = {
                target: self._target_value(
                    context, target, removed, disruption_cache
                )
                for target in candidate_tiles
            }
            followups = {
                target: self._best_followup(
                    context, target, removed | {target}, disruption_cache,
                    candidate_order,
                )
                for target in candidate_tiles
            }
            choices: list[tuple[TargetScore, BuilderSnapshot]] = []
            for builder in remaining:
                for target in candidate_tiles:
                    scored = self._score(
                        context, builder, target,
                        target_values[target], followups[target],
                    )
                    if scored is None:
                        continue
                    considered[(builder.entity_id, target)] = scored
                    note(2, "target.scored", "scored destroy-and-block target",
                         builder_id=builder.entity_id, target=target, score=scored.score,
                         disrupted_flow=scored.disrupted_flow,
                         disrupted_harvesters=scored.disrupted_harvesters,
                         completion_time=scored.completion_time,
                         followup_target=scored.followup_target,
                         followup_value=scored.followup_value)
                    if scored.score >= self.policy.minimum_score:
                        choices.append((scored, builder))
            if not choices:
                break
            scored, builder = max(
                choices,
                key=lambda pair: (
                    pair[0].score,
                    pair[0].immediate_value,
                    -pair[0].completion_time,
                    -pair[1].spawn_index,
                    -pair[1].entity_id,
                    -pair[0].target[1],
                    -pair[0].target[0],
                ),
            )
            job_id = self._job_id(scored.target)
            jobs.append(HarassmentJob(job_id, scored.target, scored.staging_tile,
                                      scored.route.tiles, scored))
            assignments.append(HarassmentAssignment(builder.entity_id, job_id, epoch))
            note(1, "builder.assigned", "assigned destroy-and-block job",
                 builder_id=builder.entity_id, job_id=job_id, target=scored.target,
                 score=scored.score)
            remaining.remove(builder)
            removed.add(scored.target)

        targets = tuple(sorted(considered.values(), key=lambda s: (-s.score, s.target, s.staging_tile)))
        note(1, "plan.complete", "harassment plan complete", jobs=len(jobs),
             unassigned_builders=len(remaining))
        return HarassmentPlan(
            epoch, context.map_revision, context.roster_revision, targets,
            tuple(jobs), tuple(assignments), tuple(debug),
        )

    def next_builder_directive(
        self,
        context: HarassmentContext,
        plan: HarassmentPlan,
        builder_id: int,
    ) -> BuilderDirective:
        builder = next((b for b in context.builders if b.entity_id == builder_id), None)
        job = plan.job_for_builder(builder_id)
        if builder is None or not builder.available_for_harassment or job is None:
            return self._directive(plan, builder_id, None, HarassmentActionType.RELEASE_TO_GLOBAL_ASSIGNMENT,
                                   None, "no active harassment assignment")

        target_occupant = context.occupants.get(job.target)
        target_is_enemy_economy = (
            target_occupant is not None
            and target_occupant.owner is Owner.ENEMY
            and target_occupant.kind in _ECONOMY
        )
        adjacent = self._manhattan(builder.position, job.target) == 1

        if target_is_enemy_economy:
            if adjacent:
                if context.knowledge.get(job.target) is not KnowledgeState.VISIBLE:
                    return self._directive(
                        plan, builder_id, job, HarassmentActionType.REQUEST_REPLAN,
                        job.target, "adjacent target is not currently verified",
                    )
                return self._directive(plan, builder_id, job, HarassmentActionType.ATTACK,
                                       job.target, "destroy assigned economic target")
            route = context.path_oracle.route(builder.position, job.staging_tile)
            if route is None or len(route.tiles) < 2:
                return self._directive(plan, builder_id, job, HarassmentActionType.REQUEST_REPLAN,
                                       job.target, "staging tile no longer reachable")
            return self._directive(plan, builder_id, job, HarassmentActionType.MOVE,
                                   route.tiles[1], "approach assigned target")

        if target_occupant is not None and target_occupant.owner is Owner.OURS \
                and target_occupant.kind is StructureKind.BARRIER:
            return self._directive(plan, builder_id, job, HarassmentActionType.REPORT_COMPLETE,
                                   job.target, "target destroyed and blocked")

        if target_occupant is not None:
            return self._directive(plan, builder_id, job, HarassmentActionType.REQUEST_REPLAN,
                                   job.target, "target tile now contains a different structure")

        if context.knowledge.get(job.target) is not KnowledgeState.VISIBLE:
            return self._directive(plan, builder_id, job, HarassmentActionType.REQUEST_REPLAN,
                                   job.target, "target absence is not currently visible")
        if not adjacent:
            route = context.path_oracle.route(builder.position, job.staging_tile)
            if route is None or len(route.tiles) < 2:
                return self._directive(plan, builder_id, job, HarassmentActionType.REQUEST_REPLAN,
                                       job.target, "cannot reach barrier staging tile")
            return self._directive(plan, builder_id, job, HarassmentActionType.MOVE,
                                   route.tiles[1], "approach destroyed target to block it")
        if not context.constraints.barrier_build_allowed:
            return self._directive(plan, builder_id, job, HarassmentActionType.WAIT,
                                   job.target, "barrier spending currently disallowed")
        if job.target not in context.buildable_tiles or job.target in context.constraints.forbidden_tiles:
            return self._directive(plan, builder_id, job, HarassmentActionType.REQUEST_REPLAN,
                                   job.target, "destroyed target tile is not buildable")
        return self._directive(plan, builder_id, job, HarassmentActionType.BUILD_BARRIER,
                               job.target, "deny immediate economic repair")

    def _score(
        self,
        context: HarassmentContext,
        builder: BuilderSnapshot,
        target: Tile,
        target_value: tuple[tuple[Tile, ...], float, int, float, int],
        followup: tuple[Tile | None, int],
    ) -> TargetScore | None:
        node = context.enemy_economy[target]
        route_choice = self._best_staging_route(context, builder.position, target)
        if route_choice is None:
            return None
        staging, route = route_choice
        disrupted, flow, replacement, confidence, immediate = target_value
        attack_turns = math.ceil((node.hp or self.policy.default_target_hp) / self.policy.attack_damage)
        attack_turns *= self.policy.attack_action_rounds
        completion = route.travel_time + attack_turns + self.policy.barrier_action_rounds
        followup_target, followup_value = followup
        score = (immediate + followup_value) * self.policy.score_scale // max(1, completion)
        return TargetScore(
            builder.entity_id, target, staging, route, disrupted, flow, replacement, confidence,
            route.travel_time, attack_turns, completion, immediate,
            followup_target, followup_value, score,
        )

    def _best_followup(
        self,
        context: HarassmentContext,
        first: Tile,
        removed: set[Tile],
        cache: dict[tuple[frozenset[Tile], Tile], tuple[tuple[Tile, ...], float]],
        candidate_order: tuple[Tile, ...],
    ) -> tuple[Tile | None, int]:
        best: tuple[int, Tile] | None = None
        nearby = sorted(
            (
                tile for tile in candidate_order
                if tile not in removed
                and self._manhattan(first, tile) <= self.policy.followup_radius
            ),
            key=lambda tile: (self._manhattan(first, tile), tile),
        )[: self.policy.followup_candidate_limit]
        for tile in nearby:
            *_, raw = self._target_value(context, tile, removed, cache)
            value = raw * self.policy.followup_discount_percent // 100
            candidate = value, tile
            if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and tile < best[1]):
                best = candidate
        return (None, 0) if best is None else (best[1], best[0])

    def _target_value(
        self,
        context: HarassmentContext,
        target: Tile,
        removed: set[Tile],
        cache: dict[tuple[frozenset[Tile], Tile], tuple[tuple[Tile, ...], float]],
    ) -> tuple[tuple[Tile, ...], float, int, float, int]:
        node = context.enemy_economy[target]
        key = frozenset(removed), target
        disrupted, flow = cache.get(key, ((), -1.0))
        if flow < 0:
            disrupted, flow = self._disruption(context, target, removed)
            cache[key] = disrupted, flow
        confidence = max(self.policy.minimum_confidence, min(1.0, node.confidence))
        knowledge = context.knowledge.get(target, KnowledgeState.UNREVEALED)
        if knowledge is KnowledgeState.REVEALED:
            confidence *= self.policy.revealed_confidence_multiplier
        if target in context.inferred_tiles:
            confidence *= self.policy.inferred_confidence_multiplier
        replacement = self.policy.replacement_cost(node.kind)
        immediate = round(confidence * (
            flow * self.policy.denial_horizon * self.policy.flow_value_weight
            + replacement * self.policy.replacement_cost_weight
        ))
        return disrupted, flow, replacement, confidence, immediate

    def _disruption(
        self, context: HarassmentContext, target: Tile, already_removed: set[Tile]
    ) -> tuple[tuple[Tile, ...], float]:
        before_removed = already_removed
        after_removed = already_removed | {target}
        disrupted: list[Tile] = []
        flow = 0.0
        for tile, node in context.enemy_economy.items():
            if node.kind is not StructureKind.HARVESTER or tile in before_removed:
                continue
            if not self._reaches_core(context, tile, before_removed):
                continue
            if self._reaches_core(context, tile, after_removed):
                continue
            disrupted.append(tile)
            flow += node.production_per_round
        return tuple(sorted(disrupted)), flow

    def _reaches_core(self, context: HarassmentContext, start: Tile, removed: set[Tile]) -> bool:
        stack = [start]
        visited: set[Tile] = set()
        while stack:
            tile = stack.pop()
            if tile in visited or tile in removed:
                continue
            if tile in context.enemy_core_inputs:
                return True
            visited.add(tile)
            node = context.enemy_economy.get(tile)
            if node is not None:
                stack.extend(node.output_tiles)
        return False

    def _rank_candidates(self, context: HarassmentContext) -> tuple[Tile, ...]:
        """Cheap static shortlist: estimated upstream flow, then replacement value."""
        upstream_flow = {tile: 0.0 for tile in context.enemy_economy}
        for source, node in context.enemy_economy.items():
            if node.kind is not StructureKind.HARVESTER:
                continue
            stack = [source]
            visited: set[Tile] = set()
            while stack:
                tile = stack.pop()
                if tile in visited:
                    continue
                visited.add(tile)
                if tile in upstream_flow:
                    upstream_flow[tile] += node.production_per_round
                downstream = context.enemy_economy.get(tile)
                if downstream is not None:
                    stack.extend(downstream.output_tiles)
        candidates = [
            tile for tile, node in context.enemy_economy.items()
            if node.kind in _ECONOMY
            and tile not in context.constraints.forbidden_tiles
        ]
        candidates.sort(key=lambda tile: (
            -upstream_flow[tile],
            -self.policy.replacement_cost(context.enemy_economy[tile].kind),
            tile,
        ))
        return tuple(candidates)

    def _best_staging_route(
        self, context: HarassmentContext, start: Tile, target: Tile
    ) -> tuple[Tile, RouteEstimate] | None:
        choices = []
        for dx, dy in _DIRECTIONS:
            staging = target[0] + dx, target[1] + dy
            if not (0 <= staging[0] < context.width and 0 <= staging[1] < context.height):
                continue
            occupant = context.occupants.get(staging)
            if occupant is not None and staging != start:
                continue
            route = context.path_oracle.route(start, staging)
            if route is not None:
                choices.append((route.travel_time, staging, route))
        if not choices:
            return None
        _, staging, route = min(choices, key=lambda item: (item[0], item[1]))
        return staging, route

    def _directive(
        self,
        plan: HarassmentPlan,
        builder_id: int,
        job: HarassmentJob | None,
        action: HarassmentActionType,
        target: Tile | None,
        reason: str,
    ) -> BuilderDirective:
        event = DebugEvent(2, "builder.directive", reason, {
            "builder_id": builder_id, "job_id": job.job_id if job else None,
            "action": action.name, "target": target,
        })
        self._emit(event)
        return BuilderDirective(
            plan.epoch, builder_id, job.job_id if job else None,
            job.target if job else None, HarassmentAction(action, target, reason),
        )

    def _record(
        self, events: list[DebugEvent], level: int, event: str,
        message: str, data: dict[str, object],
    ) -> None:
        if self.policy.verbosity < level:
            return
        item = DebugEvent(level, event, message, data)
        events.append(item)
        self._emit(item)

    def _emit(self, event: DebugEvent) -> None:
        if self.policy.verbosity < event.level:
            return
        if self._debug_sink is not None:
            self._debug_sink(event)
        _LOG.debug("%s: %s %s", event.event, event.message, dict(event.data))

    @staticmethod
    def _job_id(tile: Tile) -> int:
        return 20_000_000 + tile[1] * 1_000 + tile[0]

    @staticmethod
    def _manhattan(a: Tile, b: Tile) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
