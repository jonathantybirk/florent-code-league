"""Tests for the synthetic competition-map generator."""

from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_maps as maps
import generate_profiles as profiles


class GeneratorTests(unittest.TestCase):
    def test_exact_editor_symmetry_transforms(self):
        width = height = 12
        first = (1, 1)
        probe = (4, 5)
        for symmetry in maps.Symmetry:
            with self.subTest(symmetry=symmetry):
                second = maps.transform_core_anchor(
                    first, width, height, symmetry
                )
                rows = [[maps.EMPTY for _ in range(width)] for _ in range(height)]
                paired = maps.transform(probe, width, height, symmetry)
                rows[probe[1]][probe[0]] = maps.ORE
                rows[paired[1]][paired[0]] = maps.ORE
                game_map = maps.GameMap(
                    width,
                    height,
                    rows,
                    [
                        maps.Core(1, 0, *first),
                        maps.Core(2, 1, *second),
                    ],
                    symmetry,
                )
                self.assertEqual(
                    [], maps.validate(game_map, require_playable=False)
                )
                self.assertEqual(
                    maps.footprint(second),
                    {
                        maps.transform(tile, width, height, symmetry)
                        for tile in maps.footprint(first)
                    },
                )

    def test_many_generated_maps_are_valid_and_round_trip(self):
        rng = random.Random(80421)
        seen_symmetries = set()
        for index in range(60):
            game_map = maps.generate_one(rng, index)
            self.assertEqual([], maps.validate(game_map))
            decoded = maps.decode(maps.encode(game_map))
            self.assertEqual([], maps.validate(decoded))
            self.assertEqual(game_map, decoded)
            seen_symmetries.add(game_map.symmetry)
        self.assertEqual(set(maps.Symmetry), seen_symmetries)

    def test_symmetry_violation_is_rejected(self):
        game_map = maps.generate_one(random.Random(91), 0)
        protected = set().union(
            *(
                maps.core_margin(core.anchor, game_map.width, game_map.height)
                for core in game_map.cores
            )
        )
        tile = next(
            (x, y)
            for y in range(game_map.height)
            for x in range(game_map.width)
            if (x, y) not in protected
            and maps.transform(
                (x, y), game_map.width, game_map.height, game_map.symmetry
            )
            != (x, y)
        )
        x, y = tile
        game_map.rows[y][x] = (
            maps.WALL if game_map.rows[y][x] != maps.WALL else maps.EMPTY
        )
        self.assertTrue(
            any("symmetry" in error for error in maps.validate(game_map))
        )

    def test_invalid_dimensions_are_rejected(self):
        game_map = maps.generate_one(random.Random(7), 0)
        game_map.width = 31
        self.assertTrue(
            any("dimensions" in error for error in maps.validate(game_map))
        )

    def test_rules_only_separates_playability_policy(self):
        rows = [[maps.EMPTY for _ in range(8)] for _ in range(8)]
        game_map = maps.GameMap(
            8,
            8,
            rows,
            [maps.Core(1, 0, 1, 1), maps.Core(2, 1, 5, 5)],
            maps.Symmetry.ROTATIONAL,
        )
        self.assertEqual([], maps.validate(game_map, require_playable=False))
        self.assertTrue(
            any("reachable ore" in error for error in maps.validate(game_map))
        )

    def test_official_pool_features_and_symmetry_mix(self):
        official = sorted(profiles.OFFICIAL.glob("*.map26"))
        extracted = [profiles.features(path) for path in official]
        self.assertEqual(15, len(extracted))
        symmetry_counts = {
            symmetry: sum(
                item.symmetries == (symmetry,) for item in extracted
            )
            for symmetry in maps.Symmetry
        }
        self.assertEqual(10, symmetry_counts[maps.Symmetry.ROTATIONAL])
        self.assertEqual(1, symmetry_counts[maps.Symmetry.HORIZONTAL])
        self.assertEqual(3, symmetry_counts[maps.Symmetry.VERTICAL])
        self.assertEqual(
            1, sum(len(item.symmetries) > 1 for item in extracted)
        )

    def test_adversarial_anchor_ambiguity_is_real(self):
        game_map = profiles.generate_adversarial_ambiguity(
            random.Random(117), 0
        )
        self.assertEqual(
            [maps.Symmetry.HORIZONTAL],
            maps.matching_symmetries(game_map),
        )
        for team in (0, 1):
            survivors = profiles.surviving_round_one(game_map, team)
            self.assertIn(maps.Symmetry.ROTATIONAL, survivors)
            self.assertIn(maps.Symmetry.HORIZONTAL, survivors)
            core = next(core for core in game_map.cores if core.team == team)
            self.assertEqual(
                maps.transform_core_anchor(
                    core.anchor,
                    game_map.width,
                    game_map.height,
                    maps.Symmetry.ROTATIONAL,
                ),
                maps.transform_core_anchor(
                    core.anchor,
                    game_map.width,
                    game_map.height,
                    maps.Symmetry.HORIZONTAL,
                ),
            )


if __name__ == "__main__":
    unittest.main()
