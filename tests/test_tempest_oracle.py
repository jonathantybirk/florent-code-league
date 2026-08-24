"""Validation tests for the published-map oracle."""

from importlib import util
from pathlib import Path
import sys

from fcode import Environment, Position


BOT_DIR = Path(__file__).parents[1] / "bots" / "luc" / "tempest_reinforcements"
sys.path.insert(0, str(BOT_DIR))
try:
    spec = util.spec_from_file_location("luc_tempest_atlas", BOT_DIR / "atlas.py")
    atlas = util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(atlas)
finally:
    sys.path.remove(str(BOT_DIR))


class VisibleMap:
    def __init__(self, environment: Environment) -> None:
        self.environment = environment

    def get_map_width(self) -> int:
        return 12

    def get_map_height(self) -> int:
        return 12

    def get_nearby_tiles(self) -> list[Position]:
        return [Position(0, 0)]

    def get_tile_env(self, position: Position) -> Environment:
        return self.environment


def test_identifies_known_map_after_visible_terrain_agrees() -> None:
    known = atlas.identify_visible(VisibleMap(Environment.EMPTY), (1, 8))

    assert known is not None
    assert known.name == "duel"
    assert known.enemy_core == (9, 2)


def test_rejects_known_dimensions_when_visible_terrain_disagrees() -> None:
    known = atlas.identify_visible(VisibleMap(Environment.WALL), (1, 8))

    assert known is None
