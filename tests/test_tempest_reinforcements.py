"""Tests for Luc's persistent-spawning Tempest variant."""

from importlib import util
from pathlib import Path
import sys
import unittest

from fcode import Environment, Position


BOT_DIR = Path(__file__).parents[1] / "bots" / "luc" / "tempest_reinforcements"
saved_modules = {name: sys.modules.pop(name)
                 for name in ("atlas", "atlas_data", "constants", "utils")
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
    for name in ("atlas", "atlas_data", "constants", "utils"):
        sys.modules.pop(name, None)
    sys.modules.update(saved_modules)


class FakeController:
    def __init__(self, titanium: int) -> None:
        self.titanium = titanium
        self.ammo = 120
        self.spawned: list[Position] = []
        self.round = 100
        self.store: dict[int, int] = {core.SLOT_BUILDER_HEARTBEAT: self.round}

    def get_global_ammo(self) -> int:
        return self.ammo

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

    def get_harvester_cost(self) -> int:
        return 68

    def get_launcher_cost(self) -> int:
        return 70

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

    def can_convert_ammo(self, amount: int) -> bool:
        return amount > 0

    def convert_ammo(self, amount: int) -> None:
        self.titanium -= amount
        self.ammo += amount


class PersistentSpawningTests(unittest.TestCase):
    def test_ammo_conversion_arms_the_team_before_reserving_build_budget(self) -> None:
        """An unarmed team converts past the construction reserve.

        With no ammunition no turret can fire and no Builder may start one,
        so holding titanium back for a scaled Harvester is strictly worse
        than being able to shoot.
        """
        ct = FakeController(80)
        ct.ammo = 0

        core._keep_ammunition(ct)

        self.assertEqual(ct.titanium, core.EMERGENCY_RESERVE)
        self.assertEqual(ct.ammo, 80 - core.EMERGENCY_RESERVE)

    def test_ammo_conversion_preserves_scaled_construction_cost(self) -> None:
        """Above the combat floor the scaled construction reserve applies."""
        ct = FakeController(80)
        ct.ammo = core.COMBAT_AMMO_FLOOR

        core._keep_ammunition(ct)

        # get_launcher_cost() of 70 outranks MIN_TITANIUM_RESERVE.
        self.assertEqual(ct.titanium, 70)
        self.assertEqual(ct.ammo, core.COMBAT_AMMO_FLOOR + 10)

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

    def test_known_map_publishes_oracle_enemy_core(self) -> None:
        player = object_with_builders_spawned(core.MAX_OPENING_BUILDERS)
        del player.builders_spawned
        ct = DuelAtlasController(core.REINFORCEMENT_TITANIUM_THRESHOLD)

        core.run(player, ct)

        self.assertEqual(ct.store[core.SLOT_ENEMY_CORE], 1 + 9 * 32 + 2)


class DuelAtlasController(FakeController):
    def get_position(self) -> Position:
        return Position(1, 8)

    def get_map_width(self) -> int:
        return 12

    def get_map_height(self) -> int:
        return 12


def object_with_builders_spawned(count: int):
    class Player:
        pass

    player = Player()
    player.builders_spawned = count
    player.repair_alert = False
    return player


if __name__ == "__main__":
    unittest.main()
