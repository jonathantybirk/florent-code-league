"""Deterministic, bounded mining-expansion planning."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

from .model import (
    BlindExpansionMode,
    BuilderAssignment,
    BuilderDirective,
    BuilderSnapshot,
    BuildingKind,
    CardinalDirection,
    ConstructionStep,
    CoreMiningDirective,
    DebugEvent,
    DepositDecision,
    DepositDisposition,
    ExplorationCorridor,
    JobType,
    KnowledgeState,
    MiningAction,
    MiningActionType,
    MiningContext,
    MiningJob,
    MiningPlan,
    MiningPolicy,
    Owner,
    PlannedIncome,
    PlannedLane,
    PreemptionStatus,
    RouteEstimate,
    Terrain,
    Tile,
)
from .strategies import MiningStrategies

_LOG = logging.getLogger(__name__)
_HARVESTER_RATE = 10 / 4


class MiningPlanner:
    """Plan expansion without reading vision, pathfinding, or acting on units."""

    def __init__(
        self,
        policy: MiningPolicy | None = None,
        debug_sink: Callable[[DebugEvent], None] | None = None,
        strategies: MiningStrategies | None = None,
    ) -> None:
        self.policy = policy or MiningPolicy()
        self._debug_sink = debug_sink
        self.strategies = strategies or MiningStrategies()

    def plan(self, context: MiningContext, previous_plan: MiningPlan | None = None) -> MiningPlan:
        epoch = 1 if previous_plan is None else previous_plan.epoch + 1
        debug: list[DebugEvent] = []

        def note(level: int, event: str, message: str, **data: object) -> None:
            self._record(debug, level, event, message, data)

        available = tuple(
            sorted(
                (b for b in context.builders if b.available_for_mining),
                key=lambda b: (b.spawn_index, b.entity_id),
            )
        )
        note(
            1,
            "plan.start",
            "planning mining expansion",
            epoch=epoch,
            round=context.round,
            map_revision=context.map_revision,
            roster_revision=context.roster_revision,
            available_builders=[b.entity_id for b in available],
        )

        if not context.constraints.enabled:
            note(1, "plan.disabled", "mining disabled by global constraints")
            return self._empty_plan(context, epoch, available, debug)

        deposit_planner = self.strategies.deposits or self._score_deposits
        lane_planner = self.strategies.lanes or self._group_lanes
        job_planner = self.strategies.jobs or self._build_jobs
        blind_planner = self.strategies.blind_expansion or self._plan_corridors
        assignment_planner = self.strategies.assignments or self._assign

        decisions = deposit_planner(context, note)
        lanes, decisions = lane_planner(context, decisions, note)
        jobs = job_planner(context, lanes, decisions, note)

        corridors: tuple[ExplorationCorridor, ...] = ()
        if context.constraints.expansion_allowed and len(jobs) < len(available):
            corridors = blind_planner(context, lanes, len(available) - len(jobs), note)
            claimed = {
                step.tile
                for job in jobs
                for step in job.construction_steps
            }
            filtered_corridors = []
            for corridor in corridors:
                committed = tuple(
                    step for step in corridor.committed_steps if step.tile not in claimed
                )
                if len(committed) != len(corridor.committed_steps):
                    note(
                        1,
                        "corridor.claim_conflict",
                        "removed blind steps already owned by lane jobs",
                        corridor_id=corridor.corridor_id,
                        removed_steps=len(corridor.committed_steps) - len(committed),
                    )
                filtered_corridors.append(replace(corridor, committed_steps=committed))
                claimed.update(step.tile for step in committed)
            corridors = tuple(filtered_corridors)
            jobs += tuple(self._corridor_job(corridor) for corridor in corridors)

        assignments = assignment_planner(
            context,
            jobs,
            available,
            epoch,
            previous_plan,
            note,
        )
        planned_income = self._planned_income(context, decisions)
        preemption = self._preemption(available, jobs, assignments)
        unassigned_jobs = max(0, len(jobs) - len(assignments))
        desired = min(
            len(jobs),
            len(available) + context.constraints.maximum_additional_builders,
        )
        request_builder = (
            context.constraints.expansion_allowed
            and unassigned_jobs > 0
            and desired > len(available)
        )
        next_spend = next((amount for amount in planned_income.construction_spend_by_round if amount), 0)
        accepted_count = sum(
            decision.disposition
            in (DepositDisposition.ACCEPTED, DepositDisposition.ALREADY_HARVESTED_US)
            for decision in decisions
        )
        core_directive = CoreMiningDirective(
            desired_total_mining_builders=desired,
            request_spawn_builder=request_builder,
            next_expected_spend=next_spend,
            minimum_reserved_titanium=context.economy.minimum_reserve,
            operational_expected_flow=context.economy.operational_expected_flow,
            planned_future_flow=(
                planned_income.harvester_flow_by_round[-1]
                if planned_income.harvester_flow_by_round
                else 0.0
            ),
            active_lane_count=len(lanes),
            accepted_deposit_count=accepted_count,
            assignments=assignments,
            preemption=preemption,
        )
        note(
            1,
            "plan.complete",
            "mining plan completed",
            accepted_deposits=accepted_count,
            lanes=len(lanes),
            jobs=len(jobs),
            assignments=len(assignments),
            corridors=len(corridors),
            request_builder=request_builder,
        )
        return MiningPlan(
            epoch=epoch,
            map_revision=context.map_revision,
            roster_revision=context.roster_revision,
            deposit_decisions=decisions,
            lanes=lanes,
            corridors=corridors,
            jobs=jobs,
            assignments=assignments,
            planned_income=planned_income,
            core_directive=core_directive,
            debug_events=tuple(debug),
        )

    def next_builder_directive(
        self,
        context: MiningContext,
        plan: MiningPlan,
        builder_id: int,
    ) -> BuilderDirective:
        builder = next((b for b in context.builders if b.entity_id == builder_id), None)
        if builder is None or not builder.available_for_mining:
            return self._release(plan, builder_id, "Builder is not available to mining")
        job = plan.job_for_builder(builder_id)
        if job is None:
            self._runtime_debug(1, "directive.release", "no mining job", builder_id=builder_id)
            return self._release(plan, builder_id, "No unfinished mining job")

        if job.type is JobType.BUILD_HARVESTER:
            tile = context.world.get(job.objective)
            if (
                tile
                and tile.building
                and tile.building.kind is BuildingKind.HARVESTER
                and tile.building.owner is Owner.OURS
            ):
                action = MiningAction(MiningActionType.REPORT_COMPLETE, reason="Harvester already exists")
            elif tile and tile.building:
                action = MiningAction(
                    MiningActionType.WAIT,
                    reason="Deposit is blocked; request a map revision and replan",
                )
            elif self._adjacent(builder.position, job.objective):
                action = MiningAction(
                    MiningActionType.BUILD_HARVESTER,
                    target_tile=job.objective,
                    reason="Assigned deposit reached",
                )
            else:
                action = self._move_toward(context, builder.position, job.objective)
        elif job.type is JobType.EXTEND_LANE:
            step = next(
                (step for step in job.construction_steps if not self._step_satisfied(context, step)),
                None,
            )
            if step is None:
                action = MiningAction(MiningActionType.REPORT_COMPLETE, reason="Lane steps complete")
            elif self._blocking_building(context, step.tile):
                action = MiningAction(
                    MiningActionType.WAIT,
                    reason="Construction tile is blocked; request a map revision and replan",
                )
            elif self._adjacent(builder.position, step.tile):
                action = MiningAction(
                    MiningActionType.BUILD_CONVEYOR,
                    target_tile=step.tile,
                    direction=step.direction,
                    reason=f"Extend lane {job.lane_id}",
                )
            else:
                action = self._move_toward(context, builder.position, step.tile)
        else:
            step = next(
                (step for step in job.construction_steps if not self._step_satisfied(context, step)),
                None,
            )
            target = step.tile if step else job.objective
            if step and self._adjacent(builder.position, step.tile):
                action = MiningAction(
                    MiningActionType.BUILD_CONVEYOR,
                    target_tile=step.tile,
                    direction=step.direction,
                    reason="Commit bounded exploration corridor",
                )
            elif builder.position == job.objective:
                action = MiningAction(
                    MiningActionType.WAIT,
                    reason="Exploration objective reached; await map revision",
                )
            else:
                action = self._move_toward(context, builder.position, target)

        self._runtime_debug(
            2,
            "directive.action",
            "selected Builder mining action",
            builder_id=builder_id,
            job_id=job.job_id,
            job_type=job.type.name,
            action=action.type.name,
            target=action.target_tile,
        )
        return BuilderDirective(
            plan_epoch=plan.epoch,
            builder_id=builder_id,
            job_id=job.job_id,
            job_type=job.type,
            objective=job.objective,
            primary=action,
            fallback=MiningAction(MiningActionType.WAIT, reason="Primary action unavailable"),
        )

    def _score_deposits(self, context: MiningContext, note) -> tuple[DepositDecision, ...]:
        deposits = [
            tile
            for tile in context.world.values()
            if tile.terrain is Terrain.TITANIUM_ORE
            or (tile.building is not None and tile.building.kind is BuildingKind.HARVESTER)
        ]
        deposits.sort(
            key=lambda tile: (
                min(self._manhattan(tile.position, core) for core in context.own_core_tiles),
                tile.position,
            )
        )
        existing = [
            tile
            for tile in deposits
            if tile.building
            and tile.building.kind is BuildingKind.HARVESTER
        ]
        candidates = [tile for tile in deposits if tile not in existing]
        deposits = existing + candidates[: self.policy.candidate_deposit_limit]
        decisions: list[DepositDecision] = []
        for tile in deposits:
            building = tile.building
            if building and building.kind is BuildingKind.HARVESTER:
                if building.owner is Owner.OURS:
                    existing_lane = next(
                        (
                            lane
                            for lane in context.existing_lanes
                            if tile.position in lane.harvester_tiles
                        ),
                        None,
                    )
                    if existing_lane is None:
                        route, core_input = self._best_route(context, tile.position)
                    else:
                        core_input = existing_lane.core_input
                        route = context.path_oracle.route(core_input, tile.position)
                    decisions.append(
                        DepositDecision(
                            tile.position,
                            DepositDisposition.ALREADY_HARVESTED_US,
                            score=10_000,
                            reason="Existing friendly Harvester",
                            core_input=core_input,
                            route=route,
                            our_distance=route.total_length if route else None,
                        )
                    )
                else:
                    decisions.append(
                        DepositDecision(
                            tile.position,
                            DepositDisposition.ENEMY_CONTROLLED,
                            score=-10_000,
                            reason="Deposit occupied by enemy Harvester",
                        )
                    )
                continue

            if not context.constraints.expansion_allowed:
                decisions.append(
                    DepositDecision(
                        tile.position,
                        DepositDisposition.DEFERRED_EXPANSION_DISABLED,
                        score=-10_000,
                        reason="New mining expansion disabled by global constraints",
                    )
                )
                note(
                    2,
                    "deposit.expansion_disabled",
                    "deposit deferred by global expansion constraint",
                    deposit=tile.position,
                )
                continue

            route, core_input = self._best_route(context, tile.position)
            if route is None or core_input is None:
                decisions.append(
                    DepositDecision(
                        tile.position,
                        DepositDisposition.NO_ROUTE,
                        score=-10_000,
                        reason="Path oracle found no usable Core route",
                    )
                )
                note(2, "deposit.no_route", "deposit has no route", deposit=tile.position)
                continue

            (
                disposition,
                reason,
                score,
                construction_cost,
                our_distance,
                enemy_distance,
            ) = self._evaluate_route(context, tile.position, route)
            decision = DepositDecision(
                tile.position,
                disposition,
                score,
                reason,
                core_input,
                route,
                our_distance,
                enemy_distance,
                construction_cost,
            )
            decisions.append(decision)
            note(
                2,
                "deposit.scored",
                reason,
                deposit=tile.position,
                disposition=disposition.name,
                score=score,
                our_distance=our_distance,
                enemy_distance=enemy_distance,
                construction_cost=construction_cost,
                unrevealed_tiles=route.unrevealed_tiles,
            )
        return tuple(decisions)

    def _group_lanes(self, context: MiningContext, decisions, note):
        lane_data: dict[int, dict] = {}
        input_to_ids: dict[Tile, list[int]] = {}
        for lane in context.existing_lanes:
            lane_data[lane.lane_id] = {
                "input": lane.core_input,
                "deposits": list(lane.harvester_tiles),
                "routes": set(lane.conveyor_tiles),
                "steps": {},
                "existing": True,
            }
            input_to_ids.setdefault(lane.core_input, []).append(lane.lane_id)

        updated = list(decisions)
        accepted_indices = [
            i
            for i, decision in enumerate(updated)
            if decision.disposition
            in (DepositDisposition.ACCEPTED, DepositDisposition.ALREADY_HARVESTED_US)
            and decision.route is not None
            and decision.core_input is not None
        ]
        accepted_indices.sort(key=lambda i: (-updated[i].score, updated[i].tile))
        for index in accepted_indices:
            decision = updated[index]
            candidate_ids = input_to_ids.get(decision.core_input, [])
            current_lane = next(
                (
                    lane_id
                    for lane_id in candidate_ids
                    if decision.tile in lane_data[lane_id]["deposits"]
                ),
                None,
            )
            compatible = [
                lane_id
                for lane_id in candidate_ids
                if len(lane_data[lane_id]["deposits"]) < self.policy.lane_hard_capacity
            ]
            if current_lane is not None:
                lane_id = current_lane
            elif compatible:
                lane_id = max(
                    compatible,
                    key=lambda lane_id: (
                        len(lane_data[lane_id]["routes"].intersection(decision.route.tiles))
                        * self.policy.shared_route_bonus
                        - max(
                            0,
                            len(lane_data[lane_id]["deposits"])
                            + 1
                            - self.policy.lane_soft_capacity,
                        )
                        * self.policy.lane_overload_penalty,
                        -lane_id,
                    ),
                )
            elif not candidate_ids:
                lane_id = self._new_lane_id(context, decision.core_input, lane_data)
                lane_data[lane_id] = {
                    "input": decision.core_input,
                    "deposits": [],
                    "routes": set(),
                    "steps": {},
                    "existing": False,
                }
                input_to_ids.setdefault(decision.core_input, []).append(lane_id)
                note(2, "lane.created", "created lane at Core input", lane_id=lane_id, core_input=decision.core_input)
            else:
                allowed_inputs = tuple(
                    core_input
                    for core_input in context.core_inputs
                    if self._core_input_has_capacity(core_input, input_to_ids, lane_data)
                )
                route, core_input = self._best_route(
                    context,
                    decision.tile,
                    allowed_inputs=allowed_inputs,
                )
                if route is None or core_input is None:
                    updated[index] = replace(
                        decision,
                        disposition=DepositDisposition.DEFERRED_LANE_FULL,
                        reason="All usable Core inputs reached hard lane capacity",
                    )
                    note(
                        2,
                        "deposit.lane_full",
                        "deposit deferred after trying alternate Core inputs",
                        deposit=decision.tile,
                    )
                    continue
                if decision.disposition is DepositDisposition.ALREADY_HARVESTED_US:
                    decision = replace(decision, route=route, core_input=core_input)
                else:
                    (
                        disposition,
                        reason,
                        score,
                        construction_cost,
                        our_distance,
                        enemy_distance,
                    ) = self._evaluate_route(context, decision.tile, route)
                    decision = replace(
                        decision,
                        disposition=disposition,
                        reason=reason,
                        score=score,
                        route=route,
                        core_input=core_input,
                        construction_cost=construction_cost,
                        our_distance=our_distance,
                        enemy_distance=enemy_distance,
                    )
                    if disposition is not DepositDisposition.ACCEPTED:
                        updated[index] = decision
                        note(
                            2,
                            "deposit.reroute_rejected",
                            "alternate Core route failed deposit threshold",
                            deposit=decision.tile,
                            core_input=core_input,
                            score=score,
                        )
                        continue
                updated[index] = decision
                candidate_ids = input_to_ids.get(core_input, [])
                compatible = [
                    lane_id
                    for lane_id in candidate_ids
                    if len(lane_data[lane_id]["deposits"])
                    < self.policy.lane_hard_capacity
                ]
                if compatible:
                    lane_id = max(
                        compatible,
                        key=lambda lane_id: (
                            len(lane_data[lane_id]["routes"].intersection(route.tiles))
                            * self.policy.shared_route_bonus
                            - max(
                                0,
                                len(lane_data[lane_id]["deposits"])
                                + 1
                                - self.policy.lane_soft_capacity,
                            )
                            * self.policy.lane_overload_penalty,
                            -lane_id,
                        ),
                    )
                else:
                    lane_id = self._new_lane_id(context, core_input, lane_data)
                    lane_data[lane_id] = {
                        "input": core_input,
                        "deposits": [],
                        "routes": set(),
                        "steps": {},
                        "existing": False,
                    }
                    input_to_ids.setdefault(core_input, []).append(lane_id)
                note(
                    2,
                    "deposit.rerouted",
                    "rerouted deposit through an available Core input",
                    deposit=decision.tile,
                    core_input=core_input,
                    lane_id=lane_id,
                )

            lane = lane_data[lane_id]
            if decision.tile not in lane["deposits"]:
                lane["deposits"].append(decision.tile)
            lane["routes"].update(decision.route.tiles[:-1])
            lane["steps"][decision.tile] = self._construction_steps(context, decision.route)
            count = len(lane["deposits"])
            if count > self.policy.lane_soft_capacity:
                note(1, "lane.soft_overload", "lane exceeds configured soft capacity", lane_id=lane_id, harvesters=count)
            note(2, "deposit.grouped", "assigned deposit to lane", deposit=decision.tile, lane_id=lane_id, harvesters=count)

        lanes = tuple(
            PlannedLane(
                lane_id=lane_id,
                core_input=data["input"],
                deposits=tuple(sorted(data["deposits"])),
                route_tiles=frozenset(data["routes"]),
                steps_by_deposit=dict(data["steps"]),
                existing=data["existing"],
            )
            for lane_id, data in sorted(lane_data.items())
        )
        return lanes, tuple(updated)

    def _build_jobs(self, context: MiningContext, lanes, decisions, note):
        decisions_by_tile = {decision.tile: decision for decision in decisions}
        jobs: list[MiningJob] = []
        claimed_steps: set[Tile] = set()
        for lane in lanes:
            for deposit in lane.deposits:
                decision = decisions_by_tile.get(deposit)
                if decision is None or decision.disposition is DepositDisposition.DEFERRED_LANE_FULL:
                    continue
                tile = context.world.get(deposit)
                occupied = bool(
                    tile
                    and tile.building
                    and tile.building.kind is BuildingKind.HARVESTER
                    and tile.building.owner is Owner.OURS
                )
                if not occupied:
                    job_id = 1_000_000 + self._tile_key(context, deposit)
                    jobs.append(
                        MiningJob(
                            job_id,
                            JobType.BUILD_HARVESTER,
                            self.policy.harvester_job_bonus + decision.score,
                            deposit,
                            lane.lane_id,
                            deposit,
                            route=decision.route.tiles if decision.route else (),
                        )
                    )
                    note(2, "job.harvester", "created Harvester job", job_id=job_id, deposit=deposit, lane_id=lane.lane_id)

                steps = tuple(
                    step
                    for step in reversed(lane.steps_by_deposit.get(deposit, ()))
                    if step.tile not in claimed_steps and not self._step_satisfied(context, step)
                )
                claimed_steps.update(step.tile for step in steps)
                if steps:
                    job_id = 2_000_000 + self._tile_key(context, deposit)
                    jobs.append(
                        MiningJob(
                            job_id,
                            JobType.EXTEND_LANE,
                            self.policy.lane_job_bonus + decision.score,
                            steps[0].tile,
                            lane.lane_id,
                            deposit,
                            steps,
                            decision.route.tiles if decision.route else (),
                        )
                    )
                    note(2, "job.lane", "created lane construction job", job_id=job_id, lane_id=lane.lane_id, steps=len(steps))
        jobs.sort(key=lambda job: (-job.priority, job.job_id))
        return tuple(jobs)

    def _plan_corridors(self, context: MiningContext, lanes, count: int, note):
        if count <= 0 or not context.core_inputs:
            return ()
        used = set().union(*(lane.route_tiles for lane in lanes)) if lanes else set()
        candidates = []
        core_x = sum(x for x, _ in context.own_core_tiles) / len(context.own_core_tiles)
        core_y = sum(y for _, y in context.own_core_tiles) / len(context.own_core_tiles)
        for core_input in sorted(context.core_inputs):
            if core_input in context.constraints.forbidden_tiles:
                continue
            dx = -1 if core_input[0] < core_x else (1 if core_input[0] > core_x else 0)
            dy = -1 if core_input[1] < core_y else (1 if core_input[1] > core_y else 0)
            if dx:
                objective = (0 if dx < 0 else context.width - 1, core_input[1])
            elif dy:
                objective = (core_input[0], 0 if dy < 0 else context.height - 1)
            else:
                continue
            route = context.path_oracle.route(core_input, objective)
            if route is None or any(tile in context.constraints.forbidden_tiles for tile in route.tiles):
                continue
            unrevealed = sum(
                context.world.get(tile) is None
                or context.world[tile].knowledge is KnowledgeState.UNREVEALED
                for tile in route.tiles
            )
            overlap = len(used.intersection(route.tiles))
            score = unrevealed * 10 - overlap * 4 - route.total_length
            candidates.append((score, core_input, objective, route))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

        corridors = []
        limit = min(count, self.policy.candidate_heading_limit)
        for index, (score, core_input, objective, route) in enumerate(candidates[:limit], 1):
            committed = ()
            if self.policy.blind_mode is not BlindExpansionMode.SCOUT_THEN_BACKFILL:
                blind_limit = self.policy.blind_limit(context.width, context.height)
                prefix = route.tiles[: min(len(route.tiles) - 1, blind_limit)]
                committed = self._steps_for_prefix(context, prefix)
            corridor = ExplorationCorridor(
                corridor_id=index,
                core_input=core_input,
                objective=objective,
                optimistic_route=route.tiles,
                committed_steps=committed,
                score=score,
            )
            corridors.append(corridor)
            note(
                2,
                "corridor.created",
                "created bounded exploration corridor",
                corridor_id=index,
                core_input=core_input,
                objective=objective,
                committed_steps=len(committed),
                score=score,
                mode=self.policy.blind_mode.name,
            )
        return tuple(corridors)

    def _assign(self, context, jobs, builders, epoch, previous_plan, note):
        remaining = list(builders)
        assignments = []
        previous = {a.builder_id: a.job_id for a in previous_plan.assignments} if previous_plan else {}
        for job in jobs:
            if not remaining:
                break
            ranked = []
            for builder in remaining:
                distance = context.path_oracle.distance(builder.position, job.objective)
                if distance is None:
                    continue
                switch = 0 if previous.get(builder.entity_id) == job.job_id else self.policy.assignment_switch_penalty
                ranked.append((distance + switch, distance, builder.spawn_index, builder.entity_id, builder))
            if not ranked:
                note(2, "job.unreachable", "no available Builder can reach job", job_id=job.job_id)
                continue
            _, distance, _, _, builder = min(ranked)
            assignments.append(BuilderAssignment(builder.entity_id, job.job_id, epoch, distance))
            remaining.remove(builder)
            note(
                2,
                "builder.assigned",
                "assigned Builder to mining job",
                builder_id=builder.entity_id,
                job_id=job.job_id,
                job_type=job.type.name,
                travel_cost=distance,
            )
        return tuple(assignments)

    def _planned_income(self, context, decisions):
        rounds = self.policy.income_schedule_rounds
        flow = [0.0] * rounds
        spend = [0] * rounds
        activation = {}
        for decision in decisions:
            if decision.disposition is not DepositDisposition.ACCEPTED or decision.route is None:
                continue
            steps = len(self._needed_steps(context, decision.route)) + 1
            offset = min(rounds - 1, steps * self.policy.rounds_per_build_step)
            activation[decision.tile] = context.round + offset
            for i in range(offset, rounds):
                flow[i] += _HARVESTER_RATE
            if rounds:
                spend[min(rounds - 1, self.policy.rounds_per_build_step)] += context.economy.costs.harvester
                for i in range(len(self._needed_steps(context, decision.route))):
                    at = min(rounds - 1, (i + 1) * self.policy.rounds_per_build_step)
                    spend[at] += context.economy.costs.conveyor
        return PlannedIncome(activation, tuple(flow), tuple(spend))

    def _preemption(self, builders, jobs, assignments):
        jobs_by_id = {job.job_id: job for job in jobs}
        assignment_by_builder = {a.builder_id: a for a in assignments}
        statuses = []
        for builder in builders:
            assignment = assignment_by_builder.get(builder.entity_id)
            job = jobs_by_id.get(assignment.job_id) if assignment else None
            if job is None:
                statuses.append(PreemptionStatus(builder.entity_id, True, 0, False, None, 0))
                continue
            critical = job.type in (JobType.BUILD_HARVESTER, JobType.EXTEND_LANE)
            statuses.append(
                PreemptionStatus(
                    builder.entity_id,
                    can_release_immediately=not critical,
                    turns_to_safe_handoff=1 if critical else 0,
                    unique_critical_job=critical,
                    objective=job.objective,
                    target_value=job.priority,
                )
            )
        return tuple(statuses)

    def _best_route(
        self,
        context: MiningContext,
        deposit: Tile,
        allowed_inputs: tuple[Tile, ...] | None = None,
    ):
        best = None
        inputs = context.core_inputs if allowed_inputs is None else allowed_inputs
        used_inputs = {lane.core_input for lane in context.existing_lanes}
        existing_tiles = set().union(
            *(lane.conveyor_tiles for lane in context.existing_lanes)
        )
        for core_input in inputs:
            route = context.path_oracle.route(core_input, deposit)
            if route is None or len(route.tiles) < 2:
                continue
            if any(tile in context.constraints.forbidden_tiles for tile in route.tiles[:-1]):
                continue
            if any(self._blocking_building(context, tile) for tile in route.tiles[:-1]):
                continue
            key = (
                route.total_length * self.policy.route_tile_penalty
                + route.unrevealed_tiles * self.policy.unrevealed_tile_penalty
                + route.stale_tiles * self.policy.stale_tile_penalty
                - len(existing_tiles.intersection(route.tiles))
                * self.policy.existing_network_bonus
                - (core_input not in used_inputs) * self.policy.core_side_diversity_bonus,
                core_input,
            )
            if best is None or key < best[0]:
                best = key, route, core_input
        return (None, None) if best is None else (best[1], best[2])

    def _enemy_distance(self, context: MiningContext, target: Tile):
        distances = [context.path_oracle.distance(core, target) for core in context.enemy_core_tiles]
        finite = [distance for distance in distances if distance is not None]
        return min(finite) if finite else None

    def _evaluate_route(self, context, deposit, route):
        needed = self._needed_steps(context, route)
        construction_cost = (
            context.economy.costs.harvester
            + len(needed) * context.economy.costs.conveyor
        )
        our_distance = route.total_length
        enemy_distance = self._enemy_distance(context, deposit)
        margin = enemy_distance - our_distance if enemy_distance is not None else None
        score = int(
            self.policy.payoff_horizon
            * _HARVESTER_RATE
            * self.policy.income_value_weight
        )
        score -= construction_cost * self.policy.construction_cost_weight
        score -= our_distance * self.policy.route_tile_penalty
        score -= route.unrevealed_tiles * self.policy.unrevealed_tile_penalty
        score -= route.stale_tiles * self.policy.stale_tile_penalty
        existing = set().union(
            *(lane.conveyor_tiles for lane in context.existing_lanes)
        )
        score += (
            len(existing.intersection(route.tiles))
            * self.policy.existing_network_bonus
        )
        if margin is not None:
            if margin < 0:
                score -= -margin * self.policy.enemy_side_penalty
            if margin < self.policy.contention_margin:
                score -= (
                    self.policy.contention_margin - margin
                ) * self.policy.contention_penalty
            elif margin > self.policy.contention_margin:
                score += (
                    margin - self.policy.contention_margin
                ) * self.policy.territorial_advantage_bonus

        accepted = (
            our_distance <= self.policy.always_accept_distance
            or score >= self.policy.acceptance_threshold
        )
        if accepted:
            disposition = DepositDisposition.ACCEPTED
            reason = (
                "Within automatic distance frontier"
                if our_distance <= self.policy.always_accept_distance
                else "Score meets acceptance threshold"
            )
        elif margin is not None and margin < self.policy.contention_margin:
            disposition = DepositDisposition.DEFERRED_CONTESTED
            reason = "Territorial/contention penalty pushed score below threshold"
        else:
            disposition = DepositDisposition.DEFERRED_TOO_EXPENSIVE
            reason = "Expected payoff does not cover route and construction"
        return (
            disposition,
            reason,
            score,
            construction_cost,
            our_distance,
            enemy_distance,
        )

    def _construction_steps(self, context: MiningContext, route: RouteEstimate):
        steps = []
        for index, tile in enumerate(route.tiles[:-1]):
            if index == 0:
                core = next((core for core in context.own_core_tiles if self._adjacent(tile, core)), None)
                if core is None:
                    continue
                downstream = core
            else:
                downstream = route.tiles[index - 1]
            try:
                direction = CardinalDirection.between(tile, downstream)
            except ValueError:
                continue
            steps.append(ConstructionStep(tile, direction))
        return tuple(steps)

    def _steps_for_prefix(self, context: MiningContext, prefix: tuple[Tile, ...]):
        if not prefix:
            return ()
        steps = []
        for index, tile in enumerate(prefix):
            if index == 0:
                core = next((core for core in context.own_core_tiles if self._adjacent(tile, core)), None)
                if core is None:
                    continue
                downstream = core
            else:
                downstream = prefix[index - 1]
            steps.append(ConstructionStep(tile, CardinalDirection.between(tile, downstream)))
        return tuple(steps)

    def _needed_steps(self, context, route):
        return tuple(
            step
            for step in self._construction_steps(context, route)
            if not self._step_satisfied(context, step)
        )

    @staticmethod
    def _step_satisfied(context: MiningContext, step: ConstructionStep) -> bool:
        tile = context.world.get(step.tile)
        return bool(
            tile
            and tile.building
            and tile.building.owner is Owner.OURS
            and tile.building.kind in (BuildingKind.CONVEYOR, BuildingKind.SPLITTER)
        )

    @staticmethod
    def _blocking_building(context: MiningContext, tile: Tile) -> bool:
        known = context.world.get(tile)
        if known is None or known.building is None:
            return False
        return not (
            known.building.owner is Owner.OURS
            and known.building.kind in (BuildingKind.CONVEYOR, BuildingKind.SPLITTER)
        )

    def _move_toward(self, context: MiningContext, start: Tile, target: Tile):
        route = context.path_oracle.route(start, target)
        if route is None or len(route.tiles) < 2:
            return MiningAction(MiningActionType.WAIT, reason="Path oracle found no movement route")
        next_tile = route.tiles[1]
        try:
            direction = CardinalDirection.between(start, next_tile)
        except ValueError:
            return MiningAction(MiningActionType.WAIT, reason="Path oracle returned non-cardinal first step")
        return MiningAction(
            MiningActionType.MOVE,
            target_tile=next_tile,
            direction=direction,
            reason=f"Move toward mining objective {target}",
        )

    def _corridor_job(self, corridor: ExplorationCorridor):
        return MiningJob(
            3_000_000 + corridor.corridor_id,
            JobType.EXPLORE_CORRIDOR,
            self.policy.exploration_job_priority + corridor.score,
            corridor.objective,
            construction_steps=corridor.committed_steps,
            route=corridor.optimistic_route,
        )

    def _empty_plan(self, context, epoch, builders, debug):
        assignments: tuple[BuilderAssignment, ...] = ()
        preemption = tuple(
            PreemptionStatus(builder.entity_id, True, 0, False, None, 0)
            for builder in builders
        )
        income = PlannedIncome({}, (0.0,) * self.policy.income_schedule_rounds, (0,) * self.policy.income_schedule_rounds)
        directive = CoreMiningDirective(
            0,
            False,
            0,
            context.economy.minimum_reserve,
            context.economy.operational_expected_flow,
            0.0,
            0,
            0,
            assignments,
            preemption,
        )
        return MiningPlan(
            epoch,
            context.map_revision,
            context.roster_revision,
            (),
            (),
            (),
            (),
            assignments,
            income,
            directive,
            tuple(debug),
        )

    @staticmethod
    def _release(plan, builder_id, reason):
        return BuilderDirective(
            plan.epoch,
            builder_id,
            None,
            None,
            None,
            MiningAction(MiningActionType.RELEASE_TO_GLOBAL_ASSIGNMENT, reason=reason),
        )

    def _record(self, target, level, event, message, data):
        if self.policy.verbosity < level:
            return
        item = DebugEvent(level, event, message, dict(data))
        target.append(item)
        _LOG.debug("%s: %s | %s", event, message, data)
        if self._debug_sink:
            self._debug_sink(item)

    def _runtime_debug(self, level, event, message, **data):
        if self.policy.verbosity < level:
            return
        item = DebugEvent(level, event, message, data)
        _LOG.debug("%s: %s | %s", event, message, data)
        if self._debug_sink:
            self._debug_sink(item)

    @staticmethod
    def _adjacent(a: Tile, b: Tile) -> bool:
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1

    @staticmethod
    def _manhattan(a: Tile, b: Tile) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def _tile_key(context: MiningContext, tile: Tile) -> int:
        return tile[1] * context.width + tile[0]

    def _new_lane_id(self, context: MiningContext, core_input: Tile, lane_data) -> int:
        lane_id = self._tile_key(context, core_input) + 1
        while lane_id in lane_data:
            lane_id += context.width * context.height + 1
        return lane_id

    def _core_input_has_capacity(self, core_input, input_to_ids, lane_data):
        lane_ids = input_to_ids.get(core_input, ())
        return not lane_ids or any(
            len(lane_data[lane_id]["deposits"]) < self.policy.lane_hard_capacity
            for lane_id in lane_ids
        )
