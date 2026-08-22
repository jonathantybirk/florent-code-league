from __future__ import annotations

import unittest
from dataclasses import replace

from bots.utils.miningstrat import (
    BlindExpansionMode,
    BuildingKind,
    BuildingSnapshot,
    BuilderSnapshot,
    ConstructionCosts,
    EconomySnapshot,
    ExistingLane,
    KnowledgeState,
    MiningActionType,
    MiningConstraints,
    MiningContext,
    MiningPlanner,
    MiningPolicy,
    Owner,
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


def context(
    *,
    deposits=((6, 1),),
    builders=(BuilderSnapshot(10, 1, (5, 1), 100),),
    constraints=MiningConstraints(),
    revision=1,
):
    world = {
        (x, y): WorldTile((x, y), KnowledgeState.REVEALED, Terrain.EMPTY)
        for y in range(10)
        for x in range(10)
    }
    for tile in deposits:
        world[tile] = WorldTile(tile, KnowledgeState.VISIBLE, Terrain.TITANIUM_ORE)
    return MiningContext(
        round=5,
        map_revision=revision,
        roster_revision=revision,
        width=10,
        height=10,
        own_core_tiles=((1, 1), (2, 1), (1, 2), (2, 2)),
        core_inputs=((3, 1), (3, 2), (1, 3), (2, 3)),
        world=world,
        path_oracle=ManhattanOracle(),
        builders=builders,
        economy=EconomySnapshot(500, ConstructionCosts(conveyor=1, harvester=5)),
        enemy_core_tiles=((8, 8),),
        constraints=constraints,
    )


class MiningPlannerTests(unittest.TestCase):
    def test_accepts_near_deposit_and_returns_action(self):
        planner = MiningPlanner(MiningPolicy(verbosity=2))
        ctx = context()
        plan = planner.plan(ctx)

        accepted = [d for d in plan.deposit_decisions if d.disposition.name == "ACCEPTED"]
        self.assertEqual([d.tile for d in accepted], [(6, 1)])
        self.assertEqual(len(plan.assignments), 1)
        directive = planner.next_builder_directive(ctx, plan, 10)
        self.assertEqual(directive.primary.type, MiningActionType.BUILD_HARVESTER)
        self.assertEqual(directive.primary.target_tile, (6, 1))
        self.assertTrue(any(event.event == "deposit.scored" for event in plan.debug_events))

    def test_unavailable_builder_is_removed_and_work_is_reassigned(self):
        first = context(
            deposits=((6, 1), (1, 7)),
            builders=(
                BuilderSnapshot(10, 1, (5, 2), 100),
                BuilderSnapshot(11, 2, (1, 6), 100),
            ),
        )
        planner = MiningPlanner()
        old_plan = planner.plan(first)
        self.assertEqual({a.builder_id for a in old_plan.assignments}, {10, 11})

        second = replace(
            first,
            roster_revision=2,
            builders=(
                BuilderSnapshot(10, 1, (5, 2), 100, available_for_mining=False),
                BuilderSnapshot(11, 2, (1, 6), 100),
            ),
        )
        new_plan = planner.plan(second, old_plan)
        self.assertEqual({a.builder_id for a in new_plan.assignments}, {11})
        released = planner.next_builder_directive(second, new_plan, 10)
        self.assertEqual(released.primary.type, MiningActionType.RELEASE_TO_GLOBAL_ASSIGNMENT)
        self.assertGreater(len(new_plan.jobs), len(new_plan.assignments))

    def test_disabled_module_releases_builders_and_does_not_plan(self):
        ctx = context(constraints=MiningConstraints(enabled=False))
        plan = MiningPlanner().plan(ctx)
        self.assertEqual(plan.jobs, ())
        self.assertFalse(plan.core_directive.request_spawn_builder)
        directive = MiningPlanner().next_builder_directive(ctx, plan, 10)
        self.assertEqual(directive.primary.type, MiningActionType.RELEASE_TO_GLOBAL_ASSIGNMENT)

    def test_expansion_constraint_defers_new_deposits(self):
        ctx = context(constraints=MiningConstraints(expansion_allowed=False))
        plan = MiningPlanner().plan(ctx)
        self.assertEqual(
            plan.deposit_decisions[0].disposition.name,
            "DEFERRED_EXPANSION_DISABLED",
        )
        self.assertFalse(plan.jobs)

    def test_scout_mode_never_commits_blind_conveyors(self):
        ctx = context(deposits=())
        policy = MiningPolicy(blind_mode=BlindExpansionMode.SCOUT_THEN_BACKFILL)
        plan = MiningPlanner(policy).plan(ctx)
        self.assertTrue(plan.corridors)
        self.assertTrue(all(not corridor.committed_steps for corridor in plan.corridors))
        directive = MiningPlanner(policy).next_builder_directive(ctx, plan, 10)
        self.assertEqual(directive.primary.type, MiningActionType.MOVE)

    def test_stub_mode_bounds_blind_construction(self):
        ctx = context(deposits=())
        policy = MiningPolicy(
            blind_mode=BlindExpansionMode.BUILD_CORE_STUBS,
            blind_limit_small=2,
        )
        plan = MiningPlanner(policy).plan(ctx)
        self.assertTrue(plan.corridors)
        self.assertTrue(all(len(c.committed_steps) <= 2 for c in plan.corridors))

    def test_verbose_sink_receives_decision_events(self):
        events = []
        planner = MiningPlanner(MiningPolicy(verbosity=2), events.append)
        planner.plan(context())
        names = {event.event for event in events}
        self.assertIn("plan.start", names)
        self.assertIn("deposit.scored", names)
        self.assertIn("builder.assigned", names)
        self.assertIn("plan.complete", names)

    def test_contested_policy_is_tunable(self):
        strict = MiningPolicy(
            always_accept_distance=0,
            payoff_horizon=1,
            enemy_side_penalty=100,
            contention_penalty=100,
            acceptance_threshold=0,
        )
        ctx = context(deposits=((8, 7),))
        decision = MiningPlanner(strict).plan(ctx).deposit_decisions[0]
        self.assertIn("DEFERRED", decision.disposition.name)

    def test_existing_harvesters_are_not_lost_to_candidate_limit_or_capacity(self):
        ctx = context(deposits=((6, 1),))
        world = dict(ctx.world)
        world[(6, 1)] = replace(
            world[(6, 1)],
            building=BuildingSnapshot(BuildingKind.HARVESTER, Owner.OURS),
        )
        ctx = replace(
            ctx,
            world=world,
            existing_lanes=(ExistingLane(99, (3, 1), harvester_tiles=((6, 1),)),),
        )
        plan = MiningPlanner(
            MiningPolicy(candidate_deposit_limit=0, lane_hard_capacity=0)
        ).plan(ctx)

        decision = plan.deposit_decisions[0]
        self.assertEqual(decision.disposition.name, "ALREADY_HARVESTED_US")
        self.assertEqual(decision.core_input, (3, 1))
        self.assertIn((6, 1), plan.lanes[0].deposits)

    def test_full_lane_tries_another_core_input(self):
        ctx = context(deposits=((6, 1), (7, 1)))
        world = dict(ctx.world)
        world[(6, 1)] = replace(
            world[(6, 1)],
            building=BuildingSnapshot(BuildingKind.HARVESTER, Owner.OURS),
        )
        ctx = replace(
            ctx,
            world=world,
            existing_lanes=(ExistingLane(99, (3, 1), harvester_tiles=((6, 1),)),),
        )
        plan = MiningPlanner(MiningPolicy(lane_hard_capacity=1)).plan(ctx)

        new_deposit = next(d for d in plan.deposit_decisions if d.tile == (7, 1))
        self.assertEqual(new_deposit.disposition.name, "ACCEPTED")
        self.assertNotEqual(new_deposit.core_input, (3, 1))


if __name__ == "__main__":
    unittest.main()
