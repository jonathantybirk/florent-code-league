from __future__ import annotations

import random

from bots.utils.miningstrat import (
    BuilderSnapshot,
    ConstructionCosts,
    EconomySnapshot,
    KnowledgeState,
    MiningConstraints,
    MiningContext,
    MiningPlanner,
    MiningPolicy,
    MiningStrategies,
    RouteEstimate,
    Terrain,
    WorldTile,
)


class ManhattanOracle:
    def route(self, start, goal):
        x, y = start
        tiles = [start]
        while x != goal[0]:
            x += 1 if goal[0] > x else -1
            tiles.append((x, y))
        while y != goal[1]:
            y += 1 if goal[1] > y else -1
            tiles.append((x, y))
        return RouteEstimate(tuple(tiles))

    def distance(self, start, goal):
        return abs(start[0] - goal[0]) + abs(start[1] - goal[1])


def random_context(seed: int) -> MiningContext:
    rng = random.Random(seed)
    width = rng.randint(10, 30)
    height = rng.randint(10, 30)
    core = ((1, 1), (2, 1), (1, 2), (2, 2))
    inputs = ((3, 1), (3, 2), (1, 3), (2, 3))
    unavailable = set(core + inputs)
    candidates = [
        (x, y)
        for y in range(height)
        for x in range(width)
        if (x, y) not in unavailable
    ]
    deposits = set(rng.sample(candidates, rng.randint(0, min(12, len(candidates)))))
    world = {
        position: WorldTile(
            position,
            rng.choice(tuple(KnowledgeState)),
            Terrain.TITANIUM_ORE if position in deposits else Terrain.EMPTY,
            last_observed_round=rng.randint(0, 40),
            inferred=rng.random() < 0.1,
        )
        for position in candidates
    }
    builder_count = rng.randint(0, 10)
    builders = tuple(
        BuilderSnapshot(
            entity_id=100 + index,
            spawn_index=index,
            position=rng.choice(candidates),
            hp=rng.randint(1, 100),
            available_for_mining=rng.random() >= 0.25,
        )
        for index in range(builder_count)
    )
    return MiningContext(
        round=rng.randint(0, 300),
        map_revision=rng.randint(1, 100),
        roster_revision=rng.randint(1, 100),
        width=width,
        height=height,
        own_core_tiles=core,
        core_inputs=inputs,
        world=world,
        path_oracle=ManhattanOracle(),
        builders=builders,
        economy=EconomySnapshot(
            titanium=rng.randint(0, 1_000),
            costs=ConstructionCosts(rng.randint(1, 10), rng.randint(1, 20)),
            minimum_reserve=rng.randint(0, 100),
        ),
        enemy_core_tiles=((width - 2, height - 2),),
        constraints=MiningConstraints(
            expansion_allowed=rng.random() >= 0.1,
            maximum_additional_builders=rng.randint(0, 4),
        ),
    )


def test_randomized_plans_are_deterministic_and_internally_consistent():
    for seed in range(200):
        ctx = random_context(seed)
        policy = MiningPolicy(
            candidate_deposit_limit=12,
            lane_soft_capacity=4,
            lane_hard_capacity=6,
        )
        planner = MiningPlanner(policy)
        first = planner.plan(ctx)
        second = planner.plan(ctx)

        assert first == second
        assert len({job.job_id for job in first.jobs}) == len(first.jobs)
        assert len({a.builder_id for a in first.assignments}) == len(first.assignments)
        assert len({a.job_id for a in first.assignments}) == len(first.assignments)
        assert first.core_directive.assignments == first.assignments
        assert len(first.planned_income.harvester_flow_by_round) == policy.income_schedule_rounds
        assert len(first.planned_income.construction_spend_by_round) == policy.income_schedule_rounds

        available = {b.entity_id for b in ctx.builders if b.available_for_mining}
        jobs = {job.job_id for job in first.jobs}
        assert all(a.builder_id in available and a.job_id in jobs for a in first.assignments)

        construction_tiles = [
            step.tile for job in first.jobs for step in job.construction_steps
        ]
        assert len(construction_tiles) == len(set(construction_tiles))

        accepted = {
            d.tile
            for d in first.deposit_decisions
            if d.disposition.name in {"ACCEPTED", "ALREADY_HARVESTED_US"}
        }
        planned = {deposit for lane in first.lanes for deposit in lane.deposits}
        assert accepted <= planned

        for assignment in first.assignments:
            directive = planner.next_builder_directive(ctx, first, assignment.builder_id)
            assert directive.plan_epoch == first.epoch
            assert directive.job_id == assignment.job_id


def test_every_strategy_stage_can_be_replaced_independently():
    calls = []

    def deposits(ctx, note):
        calls.append("deposits")
        return ()

    def lanes(ctx, decisions, note):
        calls.append("lanes")
        assert decisions == ()
        return (), ()

    def jobs(ctx, planned_lanes, decisions, note):
        calls.append("jobs")
        return ()

    def blind(ctx, planned_lanes, count, note):
        calls.append("blind")
        return ()

    def assignments(ctx, planned_jobs, builders, epoch, previous, note):
        calls.append("assignments")
        return ()

    planner = MiningPlanner(
        strategies=MiningStrategies(
            deposits=deposits,
            lanes=lanes,
            jobs=jobs,
            blind_expansion=blind,
            assignments=assignments,
        )
    )
    planner.plan(random_context(1))

    assert calls == ["deposits", "lanes", "jobs", "blind", "assignments"]
