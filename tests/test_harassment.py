from __future__ import annotations

from dataclasses import replace

from bots.utils.harassment import (
    BuilderSnapshot,
    EnemyEconomyNode,
    HarassmentActionType,
    HarassmentConstraints,
    HarassmentContext,
    HarassmentPlanner,
    HarassmentPolicy,
    KnowledgeState,
    Occupant,
    Owner,
    RouteEstimate,
    StructureKind,
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


def context(*, builders=None):
    # h1 -- c1 -- trunk -- core
    # h2 -- c2 ----/
    nodes = {
        (7, 4): EnemyEconomyNode((7, 4), StructureKind.HARVESTER, ((6, 4),), 20, 2.5),
        (6, 4): EnemyEconomyNode((6, 4), StructureKind.CONVEYOR, ((5, 4),), 10),
        (7, 6): EnemyEconomyNode((7, 6), StructureKind.HARVESTER, ((6, 6),), 20, 2.5),
        (6, 6): EnemyEconomyNode((6, 6), StructureKind.CONVEYOR, ((5, 6),), 10),
        (5, 4): EnemyEconomyNode((5, 4), StructureKind.CONVEYOR, ((5, 5),), 10),
        (5, 6): EnemyEconomyNode((5, 6), StructureKind.CONVEYOR, ((5, 5),), 10),
        (5, 5): EnemyEconomyNode((5, 5), StructureKind.CONVEYOR, ((4, 5),), 10),
    }
    all_tiles = {(x, y) for y in range(10) for x in range(10)}
    occupants = {tile: Occupant(node.kind, Owner.ENEMY, node.hp) for tile, node in nodes.items()}
    return HarassmentContext(
        round=20,
        map_revision=1,
        roster_revision=1,
        width=10,
        height=10,
        builders=builders or (BuilderSnapshot(10, 1, (3, 5), 100),),
        enemy_economy=nodes,
        enemy_core_inputs=frozenset({(4, 5)}),
        occupants=occupants,
        knowledge={tile: KnowledgeState.VISIBLE for tile in all_tiles},
        inferred_tiles=frozenset(),
        buildable_tiles=frozenset(all_tiles),
        path_oracle=ManhattanOracle(),
    )


def test_shared_trunk_disrupts_both_harvesters_and_is_selected():
    plan = HarassmentPlanner(HarassmentPolicy(verbosity=2)).plan(context())
    job = plan.jobs[0]
    assert job.target == (5, 5)
    assert job.target_score.disrupted_flow == 5.0
    assert job.target_score.disrupted_harvesters == ((7, 4), (7, 6))
    assert any(event.event == "target.scored" for event in plan.debug_events)


def test_alternate_route_prevents_false_disconnection_value():
    ctx = context()
    nodes = dict(ctx.enemy_economy)
    # The first harvester can reach either branch, so removing one branch alone
    # must not claim its production as disrupted.
    nodes[(7, 4)] = replace(nodes[(7, 4)], output_tiles=((6, 4), (6, 6)))
    ctx = replace(ctx, enemy_economy=nodes)
    planner = HarassmentPlanner()
    disrupted, flow = planner._disruption(ctx, (6, 4), set())
    assert (7, 4) not in disrupted
    assert flow == 0


def test_candidate_bound_keeps_high_flow_trunk_not_just_costly_harvesters():
    ctx = context()
    policy = HarassmentPolicy(candidate_limit=1)
    plan = HarassmentPlanner(policy).plan(ctx)
    assert plan.jobs[0].target == (5, 5)


def test_directive_moves_attacks_blocks_then_completes():
    planner = HarassmentPlanner()
    ctx = context()
    plan = planner.plan(ctx)
    job = plan.jobs[0]
    directive = planner.next_builder_directive(ctx, plan, 10)
    assert directive.primary.type is HarassmentActionType.MOVE

    adjacent = replace(ctx, builders=(replace(ctx.builders[0], position=job.staging_tile),))
    directive = planner.next_builder_directive(adjacent, plan, 10)
    assert directive.primary.type is HarassmentActionType.ATTACK

    gone = replace(adjacent, occupants={k: v for k, v in ctx.occupants.items() if k != job.target})
    directive = planner.next_builder_directive(gone, plan, 10)
    assert directive.primary.type is HarassmentActionType.BUILD_BARRIER

    blocked = replace(gone, occupants={**gone.occupants, job.target: Occupant(StructureKind.BARRIER, Owner.OURS)})
    directive = planner.next_builder_directive(blocked, plan, 10)
    assert directive.primary.type is HarassmentActionType.REPORT_COMPLETE


def test_two_builders_receive_distinct_marginal_targets():
    ctx = context(builders=(
        BuilderSnapshot(10, 1, (3, 5), 100),
        BuilderSnapshot(11, 2, (8, 5), 100),
    ))
    plan = HarassmentPlanner().plan(ctx)
    assert len(plan.assignments) == 2
    assert len({job.target for job in plan.jobs}) == 2
    # Once the trunk is reserved, a second cut cannot claim the same flow.
    assert plan.jobs[1].target_score.disrupted_flow == 0


def test_stale_target_requests_replan_instead_of_blocking_unknown_tile():
    planner = HarassmentPlanner()
    ctx = context()
    plan = planner.plan(ctx)
    job = plan.jobs[0]
    adjacent = replace(ctx, builders=(replace(ctx.builders[0], position=job.staging_tile),))
    occupants = {k: v for k, v in ctx.occupants.items() if k != job.target}
    stale = replace(adjacent, occupants=occupants,
                    knowledge={**ctx.knowledge, job.target: KnowledgeState.REVEALED})
    directive = planner.next_builder_directive(stale, plan, 10)
    assert directive.primary.type is HarassmentActionType.REQUEST_REPLAN


def test_global_allocator_can_remove_one_builder_without_losing_other_work():
    ctx = context(builders=(
        BuilderSnapshot(10, 1, (3, 5), 100),
        BuilderSnapshot(11, 2, (8, 5), 100),
    ))
    planner = HarassmentPlanner()
    first = planner.plan(ctx)
    second_ctx = replace(ctx, roster_revision=2, builders=(
        replace(ctx.builders[0], available_for_harassment=False),
        ctx.builders[1],
    ))
    second = planner.plan(second_ctx, first)
    assert {a.builder_id for a in second.assignments} == {11}
    released = planner.next_builder_directive(second_ctx, second, 10)
    assert released.primary.type is HarassmentActionType.RELEASE_TO_GLOBAL_ASSIGNMENT


def test_barrier_budget_waits_without_stealing_global_spending_policy():
    planner = HarassmentPlanner()
    ctx = context()
    plan = planner.plan(ctx)
    job = plan.jobs[0]
    adjacent = replace(ctx, builders=(replace(ctx.builders[0], position=job.staging_tile),))
    gone = replace(
        adjacent,
        occupants={k: v for k, v in ctx.occupants.items() if k != job.target},
        constraints=HarassmentConstraints(barrier_build_allowed=False),
    )
    directive = planner.next_builder_directive(gone, plan, 10)
    assert directive.primary.type is HarassmentActionType.WAIT
