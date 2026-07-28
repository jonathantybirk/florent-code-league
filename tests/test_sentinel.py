from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "bots" / "1"))

from entities.sentinel import SentinelMixin
from fcode import Position, Team


class FakeSentinelController:
    def __init__(self) -> None:
        self.position = Position(2, 2)
        self.attackable_tiles: list[Position] = []
        self.builder_bots: dict[Position, int] = {}
        self.buildings: dict[Position, int] = {}
        self.teams: dict[int, Team] = {}
        self.fired_at: Position | None = None

    def get_position(self) -> Position:
        return self.position

    def get_team(self, entity_id: int | None = None) -> Team:
        return Team.A if entity_id is None else self.teams[entity_id]

    def get_attackable_tiles(self) -> list[Position]:
        return self.attackable_tiles

    def get_tile_builder_bot_id(self, position: Position) -> int | None:
        return self.builder_bots.get(position)

    def get_tile_building_id(self, position: Position) -> int | None:
        return self.buildings.get(position)

    def can_fire(self, target: Position) -> bool:
        return True

    def fire(self, target: Position) -> None:
        self.fired_at = target


class SentinelTests(unittest.TestCase):
    def test_fires_at_closest_enemy_entity(self) -> None:
        ct = FakeSentinelController()
        closest_friendly = Position(2, 3)
        closest_enemy = Position(4, 2)
        farther_enemy = Position(5, 2)
        ct.attackable_tiles = [farther_enemy, closest_friendly, closest_enemy]
        ct.buildings = {
            closest_friendly: 1,
            closest_enemy: 2,
            farther_enemy: 3,
        }
        ct.teams = {1: Team.A, 2: Team.B, 3: Team.B}

        SentinelMixin().run_sentinel(ct)  # type: ignore[arg-type]

        self.assertEqual(ct.fired_at, closest_enemy)

    def test_does_not_shoot_friendly_bot_covering_enemy_building(self) -> None:
        ct = FakeSentinelController()
        covered_enemy = Position(3, 2)
        uncovered_enemy = Position(4, 2)
        ct.attackable_tiles = [covered_enemy, uncovered_enemy]
        ct.builder_bots = {covered_enemy: 1}
        ct.buildings = {covered_enemy: 2, uncovered_enemy: 3}
        ct.teams = {1: Team.A, 2: Team.B, 3: Team.B}

        SentinelMixin().run_sentinel(ct)  # type: ignore[arg-type]

        self.assertEqual(ct.fired_at, uncovered_enemy)


if __name__ == "__main__":
    unittest.main()
