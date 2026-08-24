from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "bots" / "1"))

from fcode import Direction, EntityType, Environment, Position, ResourceType, Team
from utils.map import (
    DiscoverySource,
    MapMatchState,
    TileObservation,
    load_known_maps,
    update_map,
)


class FakeController:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.round = 1
        self.visible: dict[Position, tuple[Environment, int | None, int | None]] = {}
        self.entities: dict[int, dict[str, object]] = {}

    def add_entity(
        self,
        entity_id: int,
        position: Position,
        entity_type: EntityType,
        *,
        team: Team = Team.A,
        hp: int = 20,
        max_hp: int = 20,
        direction: Direction | None = None,
        stored_resource: ResourceType | None = None,
        stored_resource_id: int | None = None,
    ) -> None:
        self.entities[entity_id] = {
            "position": position,
            "entity_type": entity_type,
            "team": team,
            "hp": hp,
            "max_hp": max_hp,
            "direction": direction,
            "stored_resource": stored_resource,
            "stored_resource_id": stored_resource_id,
        }

    def get_current_round(self) -> int:
        return self.round

    def get_map_width(self) -> int:
        return self.width

    def get_map_height(self) -> int:
        return self.height

    def get_nearby_tiles(self) -> list[Position]:
        return list(self.visible)

    def get_tile_env(self, position: Position) -> Environment:
        return self.visible[position][0]

    def get_tile_building_id(self, position: Position) -> int | None:
        return self.visible[position][1]

    def get_tile_builder_bot_id(self, position: Position) -> int | None:
        return self.visible[position][2]

    def get_position(self, entity_id: int) -> Position:
        return self.entities[entity_id]["position"]  # type: ignore[return-value]

    def get_entity_type(self, entity_id: int) -> EntityType:
        return self.entities[entity_id]["entity_type"]  # type: ignore[return-value]

    def get_team(self, entity_id: int) -> Team:
        return self.entities[entity_id]["team"]  # type: ignore[return-value]

    def get_hp(self, entity_id: int) -> int:
        return self.entities[entity_id]["hp"]  # type: ignore[return-value]

    def get_max_hp(self, entity_id: int) -> int:
        return self.entities[entity_id]["max_hp"]  # type: ignore[return-value]

    def get_direction(self, entity_id: int) -> Direction:
        return self.entities[entity_id]["direction"]  # type: ignore[return-value]

    def get_stored_resource(self, entity_id: int) -> ResourceType | None:
        return self.entities[entity_id]["stored_resource"]  # type: ignore[return-value]

    def get_stored_resource_id(self, entity_id: int) -> int | None:
        return self.entities[entity_id]["stored_resource_id"]  # type: ignore[return-value]


class MapAtlasTests(unittest.TestCase):
    def test_bundled_maps_match_repository_and_parse_expected_layouts(self) -> None:
        expected = {
            "atoll": (18, 18, 18, 8),
            "aurora": (26, 26, 64, 14),
            "crossfire": (16, 16, 24, 10),
            "duel": (12, 12, 2, 6),
            "fjord": (20, 20, 20, 12),
            "hive": (25, 25, 34, 12),
            "longship": (28, 20, 40, 16),
            "pinch": (14, 18, 24, 10),
            "quarry": (24, 24, 8, 22),
            "runestone": (24, 24, 16, 16),
            "skerry": (22, 22, 24, 12),
            "sprint": (10, 10, 0, 6),
            "strait": (20, 26, 64, 12),
            "twins": (21, 21, 16, 13),
            "vault": (24, 24, 26, 10),
        }
        atlas = load_known_maps()
        self.assertEqual(set(atlas), set(expected))

        for name, known_map in atlas.items():
            with self.subTest(map=name):
                source = PROJECT_ROOT / "maps" / f"{name}.map26"
                bundled = PROJECT_ROOT / "bots" / "1" / "maps" / f"{name}.map26"
                self.assertEqual(source.read_bytes(), bundled.read_bytes())
                walls = sum(
                    tile == Environment.WALL
                    for row in known_map.environments
                    for tile in row
                )
                ores = sum(
                    tile == Environment.ORE_TITANIUM
                    for row in known_map.environments
                    for tile in row
                )
                self.assertEqual(
                    (known_map.width, known_map.height, walls, ores), expected[name]
                )
                self.assertEqual(len(known_map.cores), 8)
                self.assertEqual(len(set(known_map.cores.values())), 2)

    def test_unique_dimensions_fill_unknown_ground_only(self) -> None:
        ct = FakeController(18, 18)
        tiles = {}
        match_state = MapMatchState()

        update_map(ct, tiles, match_state)

        self.assertEqual(match_state.inferred_map_name, "atoll")
        self.assertEqual(len(tiles), 18 * 18)
        self.assertTrue(
            all(tile.source == DiscoverySource.KNOWN_MAP for tile in tiles.values())
        )
        self.assertTrue(all(tile.rounds_since_last_seen is None for tile in tiles.values()))
        self.assertTrue(all(not tile.occupancy_known for tile in tiles.values()))

    def test_24_by_24_map_narrows_from_terrain(self) -> None:
        ct = FakeController(24, 24)
        ct.visible[Position(11, 5)] = (Environment.WALL, None, None)
        tiles = {}
        match_state = MapMatchState()

        update_map(ct, tiles, match_state)

        self.assertEqual(match_state.inferred_map_name, "quarry")
        self.assertEqual(tiles[Position(11, 5)].source, DiscoverySource.VISION)
        self.assertEqual(len(tiles), 24 * 24)

    def test_24_by_24_map_narrows_from_fixed_core(self) -> None:
        ct = FakeController(24, 24)
        core_anchor = Position(2, 11)
        ct.add_entity(
            4,
            core_anchor,
            EntityType.CORE,
            team=Team.A,
            hp=500,
            max_hp=500,
        )
        ct.visible[core_anchor] = (Environment.EMPTY, 4, None)
        tiles = {}
        match_state = MapMatchState()

        update_map(ct, tiles, match_state)

        self.assertEqual(match_state.inferred_map_name, "runestone")
        self.assertEqual(tiles[core_anchor].fixed_core.anchor, core_anchor)


class MapObservationTests(unittest.TestCase):
    def test_visible_entities_are_snapshotted_and_departures_are_cleared(self) -> None:
        ct = FakeController(8, 8)
        conveyor_position = Position(2, 2)
        old_position = Position(3, 2)
        ct.add_entity(
            11,
            conveyor_position,
            EntityType.CONVEYOR,
            direction=Direction.EAST,
            stored_resource=ResourceType.TITANIUM,
            stored_resource_id=91,
        )
        ct.add_entity(
            12,
            conveyor_position,
            EntityType.BUILDER_BOT,
            hp=31,
            max_hp=40,
        )
        ct.visible = {
            conveyor_position: (Environment.EMPTY, 11, 12),
            old_position: (Environment.ORE_TITANIUM, None, None),
        }
        tiles = {}
        match_state = MapMatchState()
        update_map(ct, tiles, match_state)

        observed = tiles[conveyor_position]
        self.assertEqual(observed.building.direction, Direction.EAST)
        self.assertEqual(observed.building.stored_resource, ResourceType.TITANIUM)
        self.assertEqual(observed.building.stored_resource_id, 91)
        self.assertEqual(observed.builder_bot.hp, 31)
        self.assertTrue(observed.occupancy_known)

        ct.round = 3
        ct.visible = {conveyor_position: (Environment.EMPTY, None, None)}
        update_map(ct, tiles, match_state)

        self.assertIsNone(tiles[conveyor_position].building)
        self.assertIsNone(tiles[conveyor_position].builder_bot)
        self.assertEqual(tiles[conveyor_position].rounds_since_last_seen, 0)
        self.assertEqual(tiles[old_position].rounds_since_last_seen, 2)

    def test_dynamic_building_does_not_prevent_atlas_match(self) -> None:
        ct = FakeController(18, 18)
        position = Position(0, 0)
        ct.add_entity(17, position, EntityType.BARRIER, hp=22, max_hp=30)
        ct.visible[position] = (Environment.EMPTY, 17, None)
        tiles = {}
        match_state = MapMatchState()

        update_map(ct, tiles, match_state)

        self.assertEqual(match_state.inferred_map_name, "atoll")
        self.assertEqual(tiles[position].source, DiscoverySource.VISION)
        self.assertEqual(tiles[position].building.entity_type, EntityType.BARRIER)

    def test_visual_conflict_purges_only_atlas_tiles_and_rejects_map(self) -> None:
        ct = FakeController(18, 18)
        tiles = {}
        match_state = MapMatchState()
        update_map(ct, tiles, match_state)

        ct.round = 2
        conflict = Position(0, 0)
        ct.visible[conflict] = (Environment.WALL, None, None)
        update_map(ct, tiles, match_state)

        self.assertEqual(set(tiles), {conflict})
        self.assertEqual(tiles[conflict].source, DiscoverySource.VISION)
        self.assertEqual(match_state.rejected_maps, {"atoll"})
        self.assertIsNone(match_state.inferred_map_name)

    def test_registry_conflict_can_reject_atlas_inference(self) -> None:
        ct = FakeController(18, 18)
        tiles = {}
        match_state = MapMatchState()
        update_map(ct, tiles, match_state)

        ct.round = 2
        update = TileObservation(
            position=Position(0, 0),
            environment=Environment.WALL,
            occupancy_known=False,
        )
        with patch("utils.map.decode_map_info", return_value=[update]):
            update_map(ct, tiles, match_state)

        self.assertEqual(set(tiles), {Position(0, 0)})
        self.assertEqual(tiles[Position(0, 0)].source, DiscoverySource.REGISTRY)
        self.assertEqual(tiles[Position(0, 0)].rounds_since_last_seen, 0)
        self.assertEqual(match_state.rejected_maps, {"atoll"})

    def test_current_vision_wins_over_registry_for_the_same_tile(self) -> None:
        ct = FakeController(18, 18)
        tiles = {}
        match_state = MapMatchState()
        update_map(ct, tiles, match_state)

        ct.round = 2
        position = Position(0, 0)
        ct.visible[position] = (Environment.EMPTY, None, None)
        stale_update = TileObservation(
            position=position,
            environment=Environment.WALL,
            occupancy_known=False,
        )
        with patch("utils.map.decode_map_info", return_value=[stale_update]):
            update_map(ct, tiles, match_state)

        self.assertEqual(match_state.inferred_map_name, "atoll")
        self.assertNotIn("atoll", match_state.rejected_maps)
        self.assertEqual(tiles[position].environment, Environment.EMPTY)
        self.assertEqual(tiles[position].source, DiscoverySource.VISION)


if __name__ == "__main__":
    unittest.main()
