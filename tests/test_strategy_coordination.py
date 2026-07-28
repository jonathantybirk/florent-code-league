from __future__ import annotations

import sys
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "bots" / "1"))

from entities.builder import BuilderMixin, ConveyorEndpoint, ConveyorPlan
from entities.core import CoreMixin
from entities.launcher import LauncherMixin
from fcode import Direction, EntityType, Environment, Position, Team
from utils.common import (
    MAX_INFRASTRUCTURE_BUILDERS,
    SLOT_ATTACKER_0_ID,
    SLOT_ATTACKER_1_ID,
    SLOT_BUILDER_ID_START,
    known_map_or_warn,
    ordered_ores,
)
from utils.map import FixedCore, KnownMap, MapMatchState, load_known_maps


class FakeCoreController:
    def __init__(self) -> None:
        self.store: dict[int, int] = {}
        self.pending_writes: dict[int, int] = {}
        self.spawned_ids: list[int] = []
        self.current_id = 0

    def get_team(self) -> Team:
        return Team.A

    def get_global_resources(self) -> int:
        return 1_000

    def get_builder_bot_cost(self) -> int:
        return 1

    def can_spawn(self, position: Position) -> bool:
        return True

    def spawn_builder(self, position: Position) -> int:
        builder_id = 100 + len(self.spawned_ids)
        self.spawned_ids.append(builder_id)
        return builder_id

    def write_store(self, slot: int, value: int) -> None:
        self.pending_writes[slot] = value

    def read_store(self, slot: int) -> int:
        return self.store.get(slot, 0)

    def get_id(self) -> int:
        return self.current_id

    def commit_store_writes(self) -> None:
        self.store.update(self.pending_writes)
        self.pending_writes.clear()


class SpawnAssignmentTests(unittest.TestCase):
    def test_infrastructure_ore_partitions_do_not_overlap(self) -> None:
        km = load_known_maps()["twins"]
        my_core = next(
            fixed_core.anchor
            for fixed_core in set(km.cores.values())
            if fixed_core.team == Team.A
        )
        ores = ordered_ores(km, my_core)
        partitions = [
            set(ores[index::MAX_INFRASTRUCTURE_BUILDERS])
            for index in range(MAX_INFRASTRUCTURE_BUILDERS)
        ]

        self.assertEqual(set.union(*partitions), set(ores))
        for left in range(len(partitions)):
            for right in range(left + 1, len(partitions)):
                self.assertTrue(partitions[left].isdisjoint(partitions[right]))

    def test_consecutive_spawns_get_stable_id_assignments(self) -> None:
        km = load_known_maps()["twins"]
        core = CoreMixin()
        core.map_match_state = MapMatchState(
            known_maps={"twins": km},
            inferred_map_name="twins",
        )
        ct = FakeCoreController()

        builders: list[BuilderMixin] = []
        for spawn_index in range(5):
            core.run_core(ct)  # type: ignore[arg-type]
            builder_id = 100 + spawn_index
            self.assertEqual(ct.spawned_ids[-1], builder_id)
            self.assertEqual(
                ct.pending_writes[SLOT_BUILDER_ID_START + spawn_index],
                builder_id,
            )

            # The spawned Builder first executes next round, after its own ID
            # entry has committed. Later spawns use different slots.
            ct.commit_store_writes()
            ct.current_id = builder_id
            builder = BuilderMixin()
            builder._read_assignment(ct, km)  # type: ignore[arg-type]
            builders.append(builder)
            self.assertEqual(
                (builder.spawn_index, builder.is_attacker),
                (spawn_index, spawn_index < 2),
            )

        self.assertEqual(ct.store[SLOT_ATTACKER_0_ID], 100)
        self.assertEqual(ct.store[SLOT_ATTACKER_1_ID], 101)
        self.assertEqual(
            [(builder.spawn_index, builder.is_attacker) for builder in builders],
            [(0, True), (1, True), (2, False), (3, False), (4, False)],
        )

    def test_builder_reads_its_birth_assignment_only_once(self) -> None:
        km = load_known_maps()["twins"]

        class RecordingBuilder(BuilderMixin):
            def __init__(self) -> None:
                super().__init__()
                self.map_match_state = MapMatchState(
                    known_maps={"twins": km},
                    inferred_map_name="twins",
                )
                self.roles_run: list[str] = []

            def _run_attacker(self, ct, known_map) -> None:
                self.roles_run.append("attacker")

            def _run_infrastructure(self, ct, known_map) -> None:
                self.roles_run.append("infrastructure")

        ct = FakeCoreController()
        ct.current_id = 777
        ct.store[SLOT_BUILDER_ID_START] = 777
        builder = RecordingBuilder()
        builder.run_builder(ct)  # type: ignore[arg-type]

        # Even if the registry changes later, this bot retains its cached role.
        ct.store[SLOT_BUILDER_ID_START] = 888
        builder.run_builder(ct)  # type: ignore[arg-type]

        self.assertEqual((builder.spawn_index, builder.is_attacker), (0, True))
        self.assertEqual(builder.roles_run, ["attacker", "attacker"])

    def test_unknown_map_warns_once_without_raising(self) -> None:
        state = MapMatchState()
        state.last_processed_round = 80

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertIsNone(known_map_or_warn(state))
            self.assertIsNone(known_map_or_warn(state))

        self.assertEqual(len(caught), 1)
        self.assertIn("round 80", str(caught[0].message))


class FakeLauncherController:
    def __init__(self) -> None:
        self.builders: dict[Position, int] = {}
        self.store = {SLOT_ATTACKER_0_ID: 11, SLOT_ATTACKER_1_ID: 12}

    def read_store(self, slot: int) -> int:
        return self.store[slot]

    def get_map_width(self) -> int:
        return 10

    def get_map_height(self) -> int:
        return 10

    def get_tile_builder_bot_id(self, position: Position) -> int | None:
        return self.builders.get(position)


class LauncherRoleTests(unittest.TestCase):
    def test_launcher_ignores_adjacent_infrastructure_bot(self) -> None:
        ct = FakeLauncherController()
        launcher = Position(5, 5)
        ct.builders[launcher.add(Direction.NORTH)] = 99
        attacker_position = launcher.add(Direction.EAST)
        ct.builders[attacker_position] = 12

        selected = LauncherMixin()._find_adjacent_attacker(  # type: ignore[arg-type]
            ct, launcher
        )

        self.assertEqual(selected, attacker_position)


class ConveyorRoutingTests(unittest.TestCase):
    def test_friendly_route_is_kept_when_every_segment_approaches_target(self) -> None:
        plan = ConveyorPlan(
            (Position(4, 5), Position(3, 5)),
            Position(2, 5),
        )

        self.assertTrue(
            BuilderMixin._plan_moves_toward_targets(
                Position(5, 5), plan, {Position(0, 5)}
            )
        )

    def test_friendly_route_is_rejected_when_a_segment_moves_away(self) -> None:
        plan = ConveyorPlan(
            (Position(6, 5), Position(7, 5)),
            Position(8, 5),
        )

        self.assertFalse(
            BuilderMixin._plan_moves_toward_targets(
                Position(5, 5), plan, {Position(0, 5)}
            )
        )

    def test_splitter_layout_can_feed_three_core_facing_gunners(self) -> None:
        anchor = Position(6, 3)
        fixed_core = FixedCore(Team.B, anchor)
        core_tiles = {
            Position(anchor.x + dx, anchor.y + dy): fixed_core
            for dx in range(2)
            for dy in range(2)
        }
        km = KnownMap(
            name="offensive-layout-test",
            width=10,
            height=10,
            environments=tuple(
                tuple(Environment.EMPTY for _ in range(10)) for _ in range(10)
            ),
            cores=core_tiles,
        )
        splitter = Position(4, 4)
        input_position = Position(3, 4)

        gunners = BuilderMixin._offensive_gunner_layout(
            km,
            splitter,
            input_position,
            set(core_tiles),
            set(core_tiles),
        )

        self.assertEqual(len(gunners), 3)
        self.assertNotIn(input_position, {position for position, _ in gunners})

    def test_offensive_fallback_plans_supply_line_splitter_and_gunners(self) -> None:
        own_anchor = Position(0, 3)
        enemy_anchor = Position(8, 3)
        own_core = FixedCore(Team.A, own_anchor)
        enemy_core = FixedCore(Team.B, enemy_anchor)
        cores = {
            Position(anchor.x + dx, anchor.y + dy): fixed_core
            for anchor, fixed_core in (
                (own_anchor, own_core),
                (enemy_anchor, enemy_core),
            )
            for dx in range(2)
            for dy in range(2)
        }
        km = KnownMap(
            name="offensive-plan-test",
            width=12,
            height=10,
            environments=tuple(
                tuple(Environment.EMPTY for _ in range(12)) for _ in range(10)
            ),
            cores=cores,
        )

        class TeamController:
            @staticmethod
            def get_team() -> Team:
                return Team.A

        builder = BuilderMixin()
        builder.map = {}
        plan = builder._plan_offensive_conveyors(  # type: ignore[arg-type]
            TeamController(), km, Position(2, 4)
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertIsNotNone(plan.splitter_direction)
        self.assertGreaterEqual(len(plan.gunners), 1)
        self.assertEqual(plan.positions[-1].add(plan.splitter_direction), plan.sink)


class TurretSelectionTests(unittest.TestCase):
    def test_tiles_touching_enemy_core_prefer_gunners(self) -> None:
        core_anchor = Position(5, 5)

        self.assertTrue(
            BuilderMixin._is_next_to_core(Position(4, 5), core_anchor)
        )
        self.assertTrue(
            BuilderMixin._is_next_to_core(Position(7, 7), core_anchor)
        )

    def test_more_distant_tiles_keep_sentinel_behavior(self) -> None:
        self.assertFalse(
            BuilderMixin._is_next_to_core(Position(2, 5), Position(5, 5))
        )


class EnemySupplyTakeoverTests(unittest.TestCase):
    @staticmethod
    def _tile(
        team: Team, entity_type, direction: Direction | None = None
    ) -> SimpleNamespace:
        return SimpleNamespace(
            building=SimpleNamespace(
                team=team,
                entity_type=entity_type,
                direction=direction,
            )
        )

    def test_detects_complete_directed_harvester_to_core_chain(self) -> None:
        harvester = Position(2, 4)
        conveyors = (Position(3, 4), Position(4, 4), Position(5, 4))
        builder = BuilderMixin()
        builder.map = {
            harvester: self._tile(Team.B, EntityType.HARVESTER),
            **{
                position: self._tile(
                    Team.B, EntityType.CONVEYOR, Direction.EAST
                )
                for position in conveyors
            },
        }

        chains = builder._enemy_supply_chains(Team.A, {Position(6, 4)})

        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0].harvester, harvester)
        self.assertEqual(chains[0].conveyors, conveyors)

    def test_rejects_incomplete_chain_near_core(self) -> None:
        builder = BuilderMixin()
        builder.map = {
            Position(2, 4): self._tile(Team.B, EntityType.HARVESTER),
            Position(3, 4): self._tile(
                Team.B, EntityType.CONVEYOR, Direction.EAST
            ),
            Position(5, 4): self._tile(
                Team.B, EntityType.CONVEYOR, Direction.EAST
            ),
        }

        self.assertEqual(
            builder._enemy_supply_chains(Team.A, {Position(6, 4)}),
            [],
        )

    def test_enemy_conveyor_is_sabotaged_with_builder_fire(self) -> None:
        target = Position(5, 4)

        class SabotageController:
            fired_at: Position | None = None

            @staticmethod
            def get_position() -> Position:
                return target

            @staticmethod
            def get_action_cooldown() -> int:
                return 0

            @staticmethod
            def can_fire(position: Position) -> bool:
                return position == target

            def fire(self, position: Position) -> None:
                self.fired_at = position

        ct = SabotageController()
        builder = BuilderMixin()

        acted = builder._sabotage_enemy_conveyor(  # type: ignore[arg-type]
            ct, load_known_maps()["twins"], target
        )

        self.assertTrue(acted)
        self.assertEqual(ct.fired_at, target)

    def test_harvester_feed_propagates_through_directed_conveyors(self) -> None:
        builder = BuilderMixin()
        harvester = Position(2, 4)
        first = Position(3, 4)
        second = Position(4, 4)
        dangling = Position(8, 4)
        builder.map = {
            harvester: self._tile(Team.B, EntityType.HARVESTER),
            first: self._tile(Team.B, EntityType.CONVEYOR, Direction.EAST),
            second: self._tile(Team.B, EntityType.CONVEYOR, Direction.EAST),
            dangling: self._tile(
                Team.B, EntityType.CONVEYOR, Direction.EAST
            ),
        }

        self.assertEqual(
            builder._fed_enemy_conveyors(Team.A),
            {first, second},
        )

    def test_fed_gunner_endpoint_outranks_closer_dangling_endpoint(self) -> None:
        fed = ConveyorEndpoint(Position(8, 4), Position(9, 4))
        dangling = ConveyorEndpoint(Position(4, 4), Position(5, 4))
        core_tiles = {Position(10, 4)}

        fed_priority = BuilderMixin._gunner_endpoint_priority(
            fed, {fed.conveyor}, core_tiles, walking_distance=20
        )
        dangling_priority = BuilderMixin._gunner_endpoint_priority(
            dangling, {fed.conveyor}, core_tiles, walking_distance=1
        )

        self.assertLess(fed_priority, dangling_priority)

    def test_core_proximity_breaks_ties_between_fed_endpoints(self) -> None:
        near = ConveyorEndpoint(Position(8, 4), Position(9, 4))
        far = ConveyorEndpoint(Position(5, 4), Position(6, 4))
        core_tiles = {Position(10, 4)}
        fed = {near.conveyor, far.conveyor}

        self.assertLess(
            BuilderMixin._gunner_endpoint_priority(
                near, fed, core_tiles, walking_distance=20
            ),
            BuilderMixin._gunner_endpoint_priority(
                far, fed, core_tiles, walking_distance=1
            ),
        )


if __name__ == "__main__":
    unittest.main()
