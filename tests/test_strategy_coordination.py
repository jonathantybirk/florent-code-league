from __future__ import annotations

import sys
import unittest
import warnings
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "bots" / "1"))

from entities.builder import BuilderMixin
from entities.launcher import LauncherMixin
from fcode import Direction, Position, Team
from utils.common import (
    ATTACKER_ROLE_BIT,
    MAX_INFRASTRUCTURE_BUILDERS,
    SLOT_ATTACKER_0_ID,
    SLOT_ATTACKER_1_ID,
    decode_spawn_assignment,
    encode_spawn_assignment,
    known_map_or_warn,
    ordered_ores,
)
from utils.map import MapMatchState, load_known_maps


class SpawnAssignmentTests(unittest.TestCase):
    def test_low_bit_carries_role_and_upper_bits_carry_spawn_order(self) -> None:
        for spawn_index in range(8):
            for attacker in (False, True):
                encoded = encode_spawn_assignment(spawn_index, attacker=attacker)
                self.assertEqual(encoded & ATTACKER_ROLE_BIT, int(attacker))
                self.assertEqual(
                    decode_spawn_assignment(encoded), (spawn_index, attacker)
                )

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
    def test_existing_friendly_conveyors_replace_core_as_sinks(self) -> None:
        core_tiles = {Position(1, 1), Position(2, 1)}
        friendly_conveyors = {Position(7, 5), Position(8, 5)}

        sinks = BuilderMixin._preferred_connection_sinks(
            core_tiles, friendly_conveyors
        )

        self.assertEqual(sinks, friendly_conveyors)
        self.assertTrue(sinks.isdisjoint(core_tiles))

    def test_core_is_used_when_no_friendly_conveyor_exists(self) -> None:
        core_tiles = {Position(1, 1), Position(2, 1)}

        sinks = BuilderMixin._preferred_connection_sinks(core_tiles, set())

        self.assertEqual(sinks, core_tiles)


if __name__ == "__main__":
    unittest.main()
