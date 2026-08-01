"""Tests for the stuck-Builder launcher fallback."""

from importlib import util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

from fcode import Position, Team


BOT_DIR = Path(__file__).parents[1] / "bots" / "luc" / "tempest_reinforcements"


def load_bot_modules():
    saved_modules = {name: sys.modules.pop(name) for name in ("constants", "utils")
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
        for name in ("constants", "utils"):
            sys.modules.pop(name, None)
        sys.modules.update(saved_modules)
    return loaded["builder"], loaded["launcher"]


builder, launcher = load_bot_modules()


class StuckBuilderController:
    def __init__(self, titanium: int = 80, can_move: bool = False) -> None:
        self.position = Position(1, 5)
        self.titanium = titanium
        self.round = 10
        self.built: list[Position] = []
        self.moved = False
        self.movement_allowed = can_move
        self.store: dict[int, int] = {}

    def get_position(self) -> Position:
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

    def get_launcher_cost(self) -> int:
        return 20

    def can_build_launcher(self, position: Position) -> bool:
        return True

    def build_launcher(self, position: Position) -> int:
        self.built.append(position)
        return 90

    def get_id(self) -> int:
        return 42

    def write_store(self, slot: int, value: int) -> None:
        self.store[slot] = value


def stuck_player():
    return SimpleNamespace(
        w=10,
        h=10,
        walls={(2, y) for y in range(10)},
        foot=set(),
        solids=set(),
        bot_occupied=set(),
        ores=set(),
        seen={(x, y) for x in range(10) for y in range(10)},
        path_failures=0,
        awaiting_launch=0,
        launch_origin=None,
        next_launcher_round=0,
    )


class LauncherFallbackTests(unittest.TestCase):
    def test_builds_launcher_after_three_failed_paths(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController()
        target = Position(8, 5)

        self.assertFalse(builder._step(player, ct, target, False))
        self.assertFalse(builder._step(player, ct, target, False))
        self.assertTrue(builder._step(player, ct, target, False))

        self.assertEqual(len(ct.built), 1)
        self.assertEqual(ct.store[builder.SLOT_LAUNCH_ID], 42)
        self.assertEqual(
            builder.unpack_pos(ct.store[builder.SLOT_LAUNCH_TARGET]),
            tuple(target),
        )
        self.assertEqual(player.awaiting_launch, builder.LAUNCH_REQUEST_ROUNDS)

    def test_preserves_titanium_when_launcher_is_not_affordable(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController(titanium=79)

        for _ in range(builder.PATH_FAILURES_BEFORE_LAUNCHER):
            builder._step(player, ct, Position(8, 5), False)

        self.assertEqual(ct.built, [])

    def test_moves_locally_when_launcher_is_not_affordable(self) -> None:
        player = stuck_player()
        ct = StuckBuilderController(titanium=0, can_move=True)

        self.assertTrue(builder._step(player, ct, Position(8, 5), False))

        self.assertTrue(ct.moved)
        self.assertEqual(ct.built, [])


class LauncherController:
    def __init__(self) -> None:
        self.store = {
            launcher.SLOT_LAUNCH_ID: 42,
            launcher.SLOT_LAUNCH_TARGET: builder.pack_pos((8, 5)),
        }
        self.launched: tuple[Position, Position] | None = None

    def read_store(self, slot: int) -> int:
        return self.store.get(slot, 0)

    def write_store(self, slot: int, value: int) -> None:
        self.store[slot] = value

    def get_nearby_units(self, dist_sq: int) -> list[int]:
        return [42]

    def get_team(self, entity_id: int | None = None) -> Team:
        return Team.A

    def get_position(self, entity_id: int) -> Position:
        return Position(1, 5)

    def get_nearby_tiles(self, dist_sq: int) -> list[Position]:
        return [Position(2, 5), Position(5, 5), Position(1, 1)]

    def can_launch(self, origin: Position, target: Position) -> bool:
        return True

    def launch(self, origin: Position, target: Position) -> None:
        self.launched = origin, target


class LauncherBehaviorTests(unittest.TestCase):
    def test_launches_requested_builder_toward_its_target(self) -> None:
        ct = LauncherController()

        launcher._run(SimpleNamespace(), ct)

        self.assertEqual(ct.launched, (Position(1, 5), Position(5, 5)))
        self.assertEqual(ct.store[launcher.SLOT_LAUNCH_ID], 0)
        self.assertEqual(ct.store[launcher.SLOT_LAUNCH_TARGET], 0)


if __name__ == "__main__":
    unittest.main()
