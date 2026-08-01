"""Tests for Luc's persistent-spawning Tempest variant."""

from importlib import util
from pathlib import Path
import sys
import unittest

from fcode import Environment, Position


BOT_DIR = Path(__file__).parents[1] / "bots" / "luc" / "tempest_reinforcements"
saved_modules = {name: sys.modules.pop(name) for name in ("constants", "utils")
                 if name in sys.modules}
sys.path.insert(0, str(BOT_DIR))
try:
    SPEC = util.spec_from_file_location(
        "luc_tempest_reinforcement_core", BOT_DIR / "core.py"
    )
    core = util.module_from_spec(SPEC)
    assert SPEC.loader is not None
    SPEC.loader.exec_module(core)
finally:
    sys.path.remove(str(BOT_DIR))
    for name in ("constants", "utils"):
        sys.modules.pop(name, None)
    sys.modules.update(saved_modules)


class FakeController:
    def __init__(self, titanium: int) -> None:
        self.titanium = titanium
        self.spawned: list[Position] = []
        self.round = 100
        self.store: dict[int, int] = {core.SLOT_BUILDER_HEARTBEAT: self.round}

    def get_global_ammo(self) -> int:
        return 120

    def get_id(self) -> int:
        return 1

    def get_hp(self, entity_id: int) -> int:
        return 500

    def get_max_hp(self, entity_id: int) -> int:
        return 500

    def get_position(self) -> Position:
        return Position(4, 4)

    def write_store(self, slot: int, value: int) -> None:
        self.store[slot] = value

    def read_store(self, slot: int) -> int:
        return self.store.get(slot, 0)

    def get_current_round(self) -> int:
        return self.round

    def get_nearby_tiles(self, dist_sq: int | None = None) -> list[Position]:
        if dist_sq is None:
            return []
        return [Position(3, 3)]

    def get_tile_env(self, tile: Position) -> Environment:
        return Environment.EMPTY

    def get_tile_building_id(self, tile: Position) -> None:
        return None

    def get_global_resources(self) -> int:
        return self.titanium

    def get_builder_bot_cost(self) -> int:
        return 30

    def get_map_width(self) -> int:
        return 20

    def get_map_height(self) -> int:
        return 20

    def can_spawn(self, tile: Position) -> bool:
        return True

    def spawn_builder(self, tile: Position) -> int:
        self.spawned.append(tile)
        self.titanium -= self.get_builder_bot_cost()
        return 100 + len(self.spawned)


class PersistentSpawningTests(unittest.TestCase):
    def test_does_not_reinforce_at_threshold(self) -> None:
        player = object_with_builders_spawned(core.MAX_OPENING_BUILDERS)
        ct = FakeController(core.REINFORCEMENT_TITANIUM_THRESHOLD)

        core.run(player, ct)

        self.assertEqual(ct.spawned, [])

    def test_reinforces_above_threshold_after_opening(self) -> None:
        player = object_with_builders_spawned(core.MAX_OPENING_BUILDERS)
        ct = FakeController(core.REINFORCEMENT_TITANIUM_THRESHOLD + 1)

        core.run(player, ct)

        self.assertEqual(len(ct.spawned), 1)
        self.assertEqual(player.builders_spawned, core.MAX_OPENING_BUILDERS + 1)

    def test_old_opening_cap_no_longer_stops_later_reinforcements(self) -> None:
        player = object_with_builders_spawned(20)
        ct = FakeController(core.REINFORCEMENT_TITANIUM_THRESHOLD + 1)

        core.run(player, ct)

        self.assertEqual(len(ct.spawned), 1)
        self.assertEqual(player.builders_spawned, 21)

    def test_replaces_last_builder_even_below_surplus_threshold(self) -> None:
        player = object_with_builders_spawned(core.MAX_OPENING_BUILDERS)
        ct = FakeController(30)
        ct.store[core.SLOT_BUILDER_HEARTBEAT] = ct.round - 1

        core.run(player, ct)

        self.assertEqual(len(ct.spawned), 1)


def object_with_builders_spawned(count: int):
    class Player:
        pass

    player = Player()
    player.builders_spawned = count
    player.repair_alert = False
    return player


if __name__ == "__main__":
    unittest.main()
