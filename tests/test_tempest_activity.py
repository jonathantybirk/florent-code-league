"""Tests for the stuck-Builder launcher fallback."""

from importlib import util
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

from fcode import EntityType, Position, Team


BOT_DIR = Path(__file__).parents[1] / "bots" / "luc" / "tempest_reinforcements"


def load_bot_modules():
    saved_modules = {name: sys.modules.pop(name)
                     for name in ("atlas", "atlas_data", "constants", "utils")
                     if name in sys.modules}
    sys.path.insert(0, str(BOT_DIR))
    loaded = {}
    try:
        for name in ("builder", "launcher"):
            spec = util.spec_from_file_location(
                f"luc_tempest_activity_{name}", BOT_DIR / f"{name}.py"
            )
            module = util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            loaded[name] = module
    finally:
        sys.path.remove(str(BOT_DIR))
        for name in ("atlas", "atlas_data", "constants", "utils"):
            sys.modules.pop(name, None)
        sys.modules.update(saved_modules)
    return loaded["builder"], loaded["launcher"]


builder, launcher = load_bot_modules()


class StuckBuilderController:
    def __init__(self, titanium: int = 80, can_move: bool = False) -> None:
        self.position = Position(1, 5)
        self.titanium = titanium
        self.ammo = 100
        self.round = 10
        self.built: list[Position] = []
        self.moved = False
        self.movement_allowed = can_move
        self.store: dict[int, int] = {}
        self.launchers: dict[int, Position] = {}
        self.enemy_positions: dict[int, Position] = {}
        self.gunners: list[tuple[Position, object]] = []
        self.harvesters: list[Position] = []

    def get_position(self, entity_id: int | None = None) -> Position:
        if entity_id is not None:
            if entity_id in self.launchers:
                return self.launchers[entity_id]
            return self.enemy_positions[entity_id]
        return self.position

    def can_move(self, direction) -> bool:
        return self.movement_allowed

    def move(self, direction) -> None:
        self.position = self.position.add(direction)
        self.moved = True

    def get_current_round(self) -> int:
        return self.round

    def get_global_resources(self) -> int:
        return self.titanium

    def get_global_ammo(self) -> int:
        return self.ammo

    def get_launcher_cost(self) -> int:
        return 20

    def get_harvester_cost(self) -> int:
        return 20

    def get_conveyor_cost(self) -> int:
        return 5

    def get_gunner_cost(self) -> int:
        return 20

    def get_action_cooldown(self) -> int:
        return 0

    def get_move_cooldown(self) -> int:
        return 0

    def can_build_launcher(self, position: Position) -> bool:
        return True

    def build_launcher(self, position: Position) -> int:
        self.built.append(position)
        self.launchers[90 + len(self.built)] = position
        return 90

    def can_build_harvester(self, position: Position) -> bool:
        return False

    def build_harvester(self, position: Position) -> int:
        self.harvesters.append(position)
        return 300 + len(self.harvesters)

    def get_tile_building_id(self, position: Position) -> int | None:
        return next((entity_id for entity_id, launcher_position
                     in self.launchers.items() if launcher_position == position), None)

    def get_nearby_buildings(self) -> list[int]:
        return [entity_id for entity_id, position in self.launchers.items()
                if self.position.distance_squared(position) <= 20]

    def get_team(self, entity_id: int | None = None) -> Team:
        return Team.B if entity_id in self.enemy_positions else Team.A

    def get_entity_type(self, entity_id: int) -> EntityType:
        return (EntityType.LAUNCHER if entity_id in self.launchers
                else EntityType.BUILDER_BOT)

    def get_nearby_entities(self) -> list[int]:
        return list(self.enemy_positions)

    def can_build_gunner(self, position: Position, facing) -> bool:
        return True

    def can_fire_from(self, position: Position, facing, entity_type,
                      target: Position) -> bool:
        return True

    def build_gunner(self, position: Position, facing) -> int:
        self.gunners.append((position, facing))
        return 200 + len(self.gunners)

    def get_id(self) -> int:
        return 42

    def write_store(self, slot: int, value: int) -> None:
        self.store[slot] = value

    def read_store(self, slot: int) -> int:
        return self.store.get(slot, 0)


class FireLaneController(StuckBuilderController):
    def __init__(self) -> None:
        super().__init__()
        self.friendly_gunners = {70: Position(1, 1)}
        self.enemy_positions[99] = Position(1, 4)

    def get_nearby_buildings(self) -> list[int]:
        return super().get_nearby_buildings() + list(self.friendly_gunners)

    def get_position(self, entity_id: int | None = None) -> Position:
        if entity_id in self.friendly_gunners:
            return self.friendly_gunners[entity_id]
        return super().get_position(entity_id)

    def get_entity_type(self, entity_id: int) -> EntityType:
        if entity_id in self.friendly_gunners:
            return EntityType.GUNNER
        return super().get_entity_type(entity_id)

    def get_direction(self, entity_id: int):
        return builder.FACING[(0, 1)]


def stuck_player(width: int = 20):
    return SimpleNamespace(
        w=width,
        h=10,
        walls={(2, y) for y in range(10)},
        foot=set(),
        solids=set(),
        conveyors={},
        bot_occupied=set(),
        enemy_launchers=set(),
        enemy_launcher_danger=set(),
        ores=set(),
        seen={(x, y) for x in range(10) for y in range(10)},
        path_failures=0,
        awaiting_launch=0,
        launch_origin=None,
        launch_blocked=False,
        launch_blocking_launchers=set(),
        launcher_breakers=set(),
        attack_gunners_built=0,
        current_route_tiles=set(),
        network_tiles=set(),
        network_load=0,
        economy_lines_completed=0,
        task=None,
        route=[],
        route_i=0,
        phase="scout",
        lock_required=False,
        build_wait_key=None,
        build_wait_rounds=0,
        pending_build=None,
        rejected_build_sites=set(),
        deferred_ores={},
        last_progress_round=10,
        last_progress="spawned",
        stall_reported=False,
        next_blocker_gunner_round=0,
        atlas=object(),
        builder_index=builder.ECONOMY_BUILDERS,
        core=(1, 5),
    )


def launch_request(player, ct):
    slot = builder.LAUNCH_REQUEST_SLOTS[
        player.builder_index % len(builder.LAUNCH_REQUEST_SLOTS)
    ]
    value = ct.store[slot]
    passenger = value >> builder.LAUNCH_DIRECTION_BITS
    direction_index = value & launcher.LAUNCH_DIRECTION_MASK
    return slot, passenger, builder.D8[direction_index - 1]


class LauncherFallbackTests(unittest.TestCase):
    def test_lead_attacker_starts_a_proactive_oracle_relay(self) -> None:
        player = stuck_player()
        player.walls.clear()
        ct = StuckBuilderController(titanium=20)

        self.assertTrue(builder._opening_ferry(player, ct, (12, 5)))

        self.assertEqual(len(ct.built), 1)
        _, passenger, direction = launch_request(player, ct)
        self.assertEqual(passenger, 42)
        self.assertEqual(direction.delta(), (1, 0))

    def test_reuses_an_adjacent_visible_launcher_instead_of_building(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController()
        ct.launchers[77] = Position(1, 4)

        self.assertTrue(builder._opening_ferry(player, ct, (12, 5)))

        self.assertEqual(ct.built, [])
        _, passenger, direction = launch_request(player, ct)
        self.assertEqual(passenger, 42)
        self.assertEqual(direction.delta(), (1, 1))

    def test_all_opening_attackers_have_distinct_launcher_requests(self) -> None:
        slots = set()
        for builder_index in range(builder.ECONOMY_BUILDERS,
                                   builder.LAUNCHER_BUILDER_INDEX):
            player = stuck_player()
            player.builder_index = builder_index
            ct = StuckBuilderController()
            ct.launchers[77] = Position(1, 4)

            self.assertTrue(builder._opening_ferry(player, ct, (12, 5)))
            slot, passenger, _ = launch_request(player, ct)
            slots.add(slot)
            self.assertEqual(passenger, 42)

        self.assertEqual(
            len(slots), builder.LAUNCHER_BUILDER_INDEX - builder.ECONOMY_BUILDERS
        )

    def test_does_not_build_while_a_nonadjacent_launcher_is_visible(self) -> None:
        player = stuck_player()
        player.walls.clear()
        ct = StuckBuilderController(can_move=True)
        ct.launchers[77] = Position(4, 5)

        self.assertTrue(builder._opening_ferry(player, ct, (12, 5)))

        self.assertEqual(ct.built, [])
        self.assertTrue(ct.moved)

    def test_builds_another_relay_after_the_previous_one_leaves_vision(self) -> None:
        player = stuck_player(width=30)
        player.walls.clear()
        ct = StuckBuilderController()
        ct.position = Position(8, 5)
        ct.launchers[77] = Position(2, 5)

        self.assertTrue(builder._opening_ferry(player, ct, (24, 5)))

        self.assertEqual(len(ct.built), 1)

    def test_skips_relay_when_enemy_core_is_within_seven_tiles(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController()

        self.assertFalse(builder._opening_ferry(player, ct, (8, 5)))

        self.assertEqual(ct.built, [])

    def test_builds_launcher_immediately_when_no_path_exists(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController()
        target = Position(8, 5)

        self.assertTrue(builder._step(player, ct, target, False))

        self.assertEqual(len(ct.built), 1)
        _, passenger, direction = launch_request(player, ct)
        self.assertEqual(passenger, 42)
        self.assertEqual(direction.delta(), (1, 1))
        self.assertEqual(player.awaiting_launch, builder.LAUNCH_REQUEST_ROUNDS)
        self.assertEqual(ct.gunners, [])

    def test_preserves_titanium_when_launcher_is_not_affordable(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController(titanium=19)

        for _ in range(builder.PATH_FAILURES_BEFORE_LAUNCHER):
            builder._step(player, ct, Position(8, 5), False)

        self.assertEqual(ct.built, [])

    def test_builds_aligned_gunner_when_launcher_is_not_possible(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController(titanium=0)
        ct.enemy_positions[99] = Position(1, 2)

        self.assertTrue(builder._step(player, ct, Position(8, 5), False))

        self.assertEqual(len(ct.gunners), 1)
        position, facing = ct.gunners[0]
        self.assertEqual(position, Position(1, 4))
        self.assertEqual(facing.delta(), (0, -1))

    def test_does_not_build_gunner_below_ammo_reserve(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController(titanium=0, can_move=True)
        ct.ammo = builder.MIN_AMMO_FOR_GUNNER - 1
        ct.enemy_positions[99] = Position(1, 2)

        self.assertTrue(builder._step(player, ct, Position(8, 5), False))

        self.assertEqual(ct.gunners, [])
        self.assertTrue(ct.moved)

    def test_does_not_build_gunner_through_obstacle(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController(titanium=0, can_move=True)
        ct.enemy_positions[99] = Position(1, 2)
        ct.can_fire_from = lambda *args: False

        self.assertTrue(builder._step(player, ct, Position(8, 5), False))

        self.assertEqual(ct.gunners, [])
        self.assertTrue(ct.moved)

    def test_moves_locally_when_launcher_is_not_affordable(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController(titanium=0, can_move=True)

        self.assertTrue(builder._step(player, ct, Position(8, 5), False))

        self.assertTrue(ct.moved)
        self.assertEqual(ct.built, [])

    def test_diagonal_harvester_target_moves_to_cardinal_build_range(self) -> None:
        player = stuck_player(width=16)
        player.h = 16
        player.walls.clear()
        player.task = (1, 14)
        ct = StuckBuilderController(can_move=True)
        ct.position = Position(0, 13)

        builder._goto(player, ct)

        self.assertTrue(ct.moved)
        self.assertEqual(
            builder._cardinal_distance(tuple(ct.position), player.task), 1
        )

    def test_harvester_waits_for_bot_then_releases_blocked_ore(self) -> None:
        player = stuck_player(width=16)
        player.h = 16
        player.walls.clear()
        player.task = (5, 13)
        player.phase = "goto"
        player.bot_occupied = {(5, 13)}
        ct = StuckBuilderController()
        ct.position = Position(4, 13)

        for round_number in range(10, 14):
            ct.round = round_number
            builder._goto(player, ct)

        self.assertIsNone(player.task)
        self.assertEqual(player.phase, "scout")
        self.assertGreater(player.deferred_ores[(5, 13)], ct.round)

    def test_waiting_wall_builder_vacates_ore(self) -> None:
        player = stuck_player(width=16)
        player.h = 16
        player.walls.clear()
        player.core = (2, 11)
        player.ores = {(5, 13)}
        player.launcher_wall_targets = [Position(6, 13)]
        player.launcher_wall_done = set()
        ct = StuckBuilderController(titanium=0, can_move=True)
        ct.position = Position(5, 13)
        ct.store[builder.SLOT_ENEMY_CORE] = builder.pack_pos((12, 3))
        ct.is_in_vision = lambda position: True

        for round_number in range(10, 14):
            ct.round = round_number
            self.assertFalse(builder._run_launcher_wall(player, ct))

        self.assertTrue(ct.moved)
        self.assertEqual(ct.position, Position(6, 12))

    def test_more_than_five_idle_rounds_emit_diagnostic_reason(self) -> None:
        player = stuck_player()
        player.phase = "goto"
        player.task = (5, 13)
        player.pending_build = (
            "harvester", (5, 13), "builder bot occupying target", 4
        )
        player.last_progress_round = 10
        ct = StuckBuilderController()
        ct.round = 16
        output = StringIO()

        with redirect_stdout(output):
            message = builder._report_stall(player, ct)

        self.assertIsNotNone(message)
        self.assertIn("BUILDER_STALL id=42 rounds=6", output.getvalue())
        self.assertIn("builder bot occupying target", output.getvalue())

    def test_unaffordable_build_is_exempt_from_duplicate_stall_alarm(self) -> None:
        player = stuck_player()
        player.pending_build = (
            "harvester", (5, 13), "needs 51 titanium", 6
        )
        player.last_progress_round = 10
        ct = StuckBuilderController(titanium=20)
        ct.round = 16
        output = StringIO()

        with redirect_stdout(output):
            message = builder._report_stall(player, ct)

        self.assertIsNone(message)
        self.assertEqual(output.getvalue(), "")

    def test_failed_build_prints_exact_resource_reason(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController(titanium=20)
        output = StringIO()

        with redirect_stdout(output):
            abandoned = builder._build_failure(
                player, ct, Position(5, 5), "harvester", 51,
                allow_ore=True,
            )

        self.assertFalse(abandoned)
        self.assertIn("PLAN_FAILED id=42 round=10", output.getvalue())
        self.assertIn("action=build harvester target=(5, 5)", output.getvalue())
        self.assertIn("needs 51 titanium; available=20 cost=51", output.getvalue())

    def test_turret_site_cannot_interrupt_a_friendly_firing_lane(self) -> None:
        ct = FireLaneController()
        output = StringIO()

        with redirect_stdout(output):
            preserves_lane = builder._preserves_friendly_turret_lanes(
                ct, Position(1, 2)
            )

        self.assertFalse(preserves_lane)
        self.assertIn(
            "reason=would block friendly turret=70 firing_at=(1, 4)",
            output.getvalue(),
        )
        self.assertTrue(
            builder._preserves_friendly_turret_lanes(ct, Position(2, 2))
        )

    def test_distance_map_matches_shortest_distance_queries(self) -> None:
        player = stuck_player(width=10)
        player.walls = {(3, y) for y in range(1, 9) if y != 4}
        source = (1, 5)
        goals = {(7, 3), (8, 6)}

        distances = builder._distance_map(player, source)

        self.assertEqual(
            min(distances[goal] for goal in goals if goal in distances),
            builder._distance(player, source, goals),
        )

    def test_launch_request_at_launcher_target_reports_failure(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController()
        launcher_position = Position(2, 5)
        output = StringIO()

        with redirect_stdout(output):
            announced = builder._announce_launch(
                player, ct, launcher_position, launcher_position,
            )

        self.assertFalse(announced)
        self.assertIn(
            "reason=launcher at (2, 5) is already the target",
            output.getvalue(),
        )

    def test_routes_around_enemy_launcher_pickup_tiles(self) -> None:
        player = stuck_player()
        player.walls.clear()
        player.enemy_launcher_danger = {(2, 5)}

        step = builder._bfs_step(player, (1, 5), (8, 5), False)

        self.assertIsNotNone(step)
        self.assertNotEqual(step, (2, 5))

    def test_builds_safe_ferry_when_enemy_launcher_blocks_corridor(self) -> None:
        player = stuck_player(width=10)
        player.h = 3
        player.walls = ({(x, 0) for x in range(10)}
                        | {(x, 2) for x in range(10)})
        player.solids = {(3, 1)}
        player.enemy_launcher_danger = {(2, 1), (4, 1)}
        ct = StuckBuilderController()
        ct.position = Position(1, 1)

        self.assertTrue(builder._step(player, ct, Position(8, 1), False))

        self.assertEqual(ct.built, [Position(0, 1)])
        _, passenger, direction = launch_request(player, ct)
        self.assertEqual(passenger, 42)
        self.assertEqual(direction.delta(), (1, 0))

    def test_rejected_launch_switches_attacker_to_gunners(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController()
        slot = builder.LAUNCH_REQUEST_SLOTS[
            player.builder_index % len(builder.LAUNCH_REQUEST_SLOTS)
        ]
        ct.store[slot] = (
            builder.LAUNCH_REJECTION_FLAG
            | (ct.get_id() << builder.LAUNCH_REJECTION_POSITION_BITS)
            | builder.pack_pos((3, 5))
        )

        self.assertFalse(builder._opening_ferry(player, ct, (12, 5)))

        self.assertTrue(player.launch_blocked)
        self.assertEqual(player.enemy_launchers, {(3, 5)})
        self.assertEqual(player.launch_blocking_launchers, {(3, 5)})
        self.assertEqual(ct.store[slot], 0)

    def test_unreachable_core_falls_back_to_enemy_launcher_gunner(self) -> None:
        player = stuck_player()
        player.solids = {(1, 2)}
        player.enemy_launchers = {(1, 2)}
        player.enemy_launcher_danger = {
            (x, y) for x in range(0, 3) for y in range(1, 4)
            if (x, y) != (1, 2)
        }
        ct = StuckBuilderController()

        self.assertTrue(builder._build_basic_gunner(player, ct, (12, 5)))

        self.assertEqual(len(ct.gunners), 1)
        position, facing = ct.gunners[0]
        self.assertEqual(position, Position(1, 4))
        self.assertEqual(facing.delta(), (0, -1))
        self.assertEqual(player.launcher_breakers, {(1, 2)})


class LauncherController:
    def __init__(self, direction_delta: tuple[int, int] = (1, 0)) -> None:
        direction_index = next(
            index for index, direction in enumerate(launcher.D8, start=1)
            if direction.delta() == direction_delta
        )
        self.request_slot = launcher.LAUNCH_REQUEST_SLOTS[1]
        request = (42 << launcher.LAUNCH_DIRECTION_BITS) | direction_index
        self.store = {
            self.request_slot: request,
            launcher.SLOT_OWN_CORE: builder.pack_pos((0, 5)),
        }
        self.launched: tuple[Position, Position] | None = None
        self.enemy_launchers: dict[int, Position] = {}

    def read_store(self, slot: int) -> int:
        return self.store.get(slot, 0)

    def write_store(self, slot: int, value: int) -> None:
        self.store[slot] = value

    def get_id(self) -> int:
        return 77

    def get_current_round(self) -> int:
        return 10

    def get_nearby_units(self, dist_sq: int) -> list[int]:
        return [42]

    def get_team(self, entity_id: int | None = None) -> Team:
        return Team.B if entity_id in self.enemy_launchers else Team.A

    def get_position(self, entity_id: int | None = None) -> Position:
        if entity_id in self.enemy_launchers:
            return self.enemy_launchers[entity_id]
        return Position(1, 5) if entity_id is not None else Position(0, 5)

    def get_nearby_buildings(self) -> list[int]:
        return list(self.enemy_launchers)

    def get_entity_type(self, entity_id: int) -> EntityType:
        return EntityType.LAUNCHER

    def get_nearby_tiles(self, dist_sq: int) -> list[Position]:
        return [Position(2, 5), Position(5, 5), Position(1, 1)]

    def can_launch(self, origin: Position, target: Position) -> bool:
        return True

    def launch(self, origin: Position, target: Position) -> None:
        self.launched = origin, target


class LauncherBehaviorTests(unittest.TestCase):
    def test_launches_requested_builder_maximally_in_announced_direction(self) -> None:
        ct = LauncherController()

        launcher._run(SimpleNamespace(), ct)

        self.assertEqual(ct.launched, (Position(1, 5), Position(5, 5)))
        self.assertEqual(ct.store[ct.request_slot], 0)

    def test_directional_launch_uses_farthest_forward_projection(self) -> None:
        ct = LauncherController((1, -1))
        ct.get_nearby_tiles = lambda dist_sq: [
            Position(3, 2),  # projection 6
            Position(4, 1),  # projection 8, at maximum radius
            Position(5, 5),  # projection 5 but no northward progress
        ]

        launcher._run(SimpleNamespace(), ct)

        self.assertEqual(ct.launched, (Position(1, 5), Position(4, 1)))

    def test_no_legal_forward_landing_keeps_request_without_crashing(self) -> None:
        ct = LauncherController()
        ct.can_launch = lambda origin, target: False

        launcher._run(SimpleNamespace(), ct)

        self.assertIsNone(ct.launched)
        self.assertNotEqual(ct.store[ct.request_slot], 0)

    def test_uses_shorter_safe_landing_outside_enemy_launcher_range(self) -> None:
        ct = LauncherController()
        ct.enemy_launchers[88] = Position(4, 5)
        ct.get_nearby_tiles = lambda dist_sq: [Position(2, 5), Position(5, 5)]

        launcher._run(SimpleNamespace(), ct)

        self.assertEqual(ct.launched, (Position(1, 5), Position(2, 5)))

    def test_rejects_request_when_every_forward_landing_is_unsafe(self) -> None:
        ct = LauncherController()
        ct.enemy_launchers = {88: Position(3, 5), 89: Position(4, 5)}
        ct.get_nearby_tiles = lambda dist_sq: [Position(2, 5), Position(5, 5)]

        launcher._run(SimpleNamespace(), ct)

        self.assertIsNone(ct.launched)
        self.assertEqual(
            ct.store[ct.request_slot],
            (launcher.LAUNCH_REJECTION_FLAG
             | (42 << launcher.LAUNCH_REJECTION_POSITION_BITS)
             | builder.pack_pos((3, 5))),
        )

    def test_launcher_throws_enemy_maximally_away_from_home_first(self) -> None:
        ct = LauncherController()
        ct.get_nearby_units = lambda dist_sq: [42, 99]
        original_team = ct.get_team
        ct.get_team = lambda entity_id=None: (
            Team.B if entity_id == 99 else original_team(entity_id)
        )
        original_position = ct.get_position
        ct.get_position = lambda entity_id=None: (
            Position(1, 4) if entity_id == 99 else original_position(entity_id)
        )
        ct.get_nearby_tiles = lambda dist_sq: [Position(1, 1), Position(5, 5)]

        launcher._run(SimpleNamespace(), ct)

        self.assertEqual(ct.launched, (Position(1, 4), Position(5, 5)))
        self.assertNotEqual(ct.store[ct.request_slot], 0)


class LauncherWallTests(unittest.TestCase):
    def test_wall_sites_have_two_tiles_between_launchers(self) -> None:
        player = SimpleNamespace(
            core=(2, 9), w=20, h=20, walls=set(), ores=set(), foot=set()
        )

        targets = builder._launcher_wall_targets(player, (17, 9))

        self.assertTrue(targets)
        self.assertEqual({target.x for target in targets}, {6})
        ordered_y = sorted(target.y for target in targets)
        self.assertTrue(all(b - a == 3 for a, b in zip(ordered_y, ordered_y[1:])))

    def test_completed_wall_releases_builder_for_economy_work(self) -> None:
        target = Position(6, 7)
        player = SimpleNamespace(
            launcher_wall_targets=[target],
            launcher_wall_done={tuple(target)},
        )
        ct = SimpleNamespace(
            read_store=lambda slot: builder.pack_pos((17, 9)),
        )

        self.assertTrue(builder._run_launcher_wall(player, ct))


if __name__ == "__main__":
    unittest.main()
