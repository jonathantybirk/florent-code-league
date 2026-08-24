from __future__ import annotations

import unittest

from bots.utils.pathfinding import (
    Terrain, distance, distance_map, first_step, keeps_route_open, path,
    safe_path,
)


def wall_column(x, h, gap=None):
    return {(x, y) for y in range(h) if y != gap}


class PathTests(unittest.TestCase):
    def test_straight_line(self):
        t = Terrain(5, 5)
        self.assertEqual(path(t, (0, 0), (3, 0)), [(0, 0), (1, 0), (2, 0), (3, 0)])

    def test_already_there(self):
        t = Terrain(5, 5)
        self.assertEqual(path(t, (2, 2), (2, 2)), [(2, 2)])
        self.assertEqual(path(t, (2, 2), (3, 3), exact=False), [(2, 2)])

    def test_walls_force_detour(self):
        t = Terrain(5, 5, blocked=wall_column(2, 5, gap=4))
        route = path(t, (0, 0), (4, 0))
        self.assertIsNotNone(route)
        self.assertIn((2, 4), route)
        self.assertEqual(len(route) - 1, 12)

    def test_no_route(self):
        t = Terrain(5, 5, blocked=wall_column(2, 5))
        self.assertIsNone(path(t, (0, 0), (4, 0)))
        self.assertIsNone(first_step(t, (0, 0), (4, 0)))
        self.assertIsNone(distance(t, (0, 0), {(4, 0)}))

    def test_adjacent_goal_when_target_is_solid(self):
        t = Terrain(5, 5, blocked={(3, 0)})
        route = path(t, (0, 0), (3, 0), exact=False)
        self.assertEqual(route[-1], (2, 0))
        self.assertIsNone(path(t, (0, 0), (3, 0), exact=True))

    def test_source_exempt_from_no_go(self):
        t = Terrain(5, 1, threat={(0, 0)})
        self.assertEqual(first_step(t, (0, 0), (4, 0)), (1, 0))

    def test_threat_forbidden_unless_allow_fire(self):
        t = Terrain(5, 1, threat={(2, 0)})
        self.assertIsNone(path(t, (0, 0), (4, 0)))
        self.assertIsNotNone(path(t, (0, 0), (4, 0), allow_fire=True))

    def test_launcher_hazards_never_admitted(self):
        t = Terrain(5, 1, launcher_hazards={(2, 0)})
        self.assertIsNone(path(t, (0, 0), (4, 0), allow_fire=True))


class HopTests(unittest.TestCase):
    def setUp(self):
        # Wall across x=5 with no gap; a launcher at (4,2) can throw over it.
        self.t = Terrain(10, 5, blocked=wall_column(5, 5),
                         friendly_launchers=[(4, 2)])

    def test_hop_crosses_wall(self):
        route = path(self.t, (0, 2), (9, 2))
        self.assertIsNotNone(route)
        jumps = [(a, b) for a, b in zip(route, route[1:])
                 if abs(a[0] - b[0]) + abs(a[1] - b[1]) != 1]
        self.assertEqual(len(jumps), 1)
        self.assertIn(jumps[0][0], self.t.pickup_ring((4, 2)))

    def test_hops_off_means_walking_only(self):
        self.assertIsNone(path(self.t, (0, 2), (9, 2), hops=False))

    def test_distance_agrees_with_path(self):
        route = path(self.t, (0, 2), (9, 2))
        self.assertEqual(distance(self.t, (0, 2), {(9, 2)}), len(route) - 1)
        self.assertEqual(distance_map(self.t, (0, 2))[(9, 2)], len(route) - 1)

    def test_landing_never_in_threat(self):
        self.t.threat = {(x, y) for x in range(6, 10) for y in range(5)}
        self.assertIsNone(path(self.t, (0, 2), (9, 2)))


class SafePathTests(unittest.TestCase):
    def test_clean_route_preferred(self):
        t = Terrain(5, 2, threat={(2, 0)})
        route, blocked = safe_path(t, (0, 0), (4, 0), survives=lambda r: True)
        self.assertFalse(blocked)
        self.assertNotIn((2, 0), route)

    def test_survivable_fire_taken(self):
        t = Terrain(5, 1, threat={(2, 0)})
        route, blocked = safe_path(t, (0, 0), (4, 0), survives=lambda r: True)
        self.assertIsNotNone(route)
        self.assertFalse(blocked)

    def test_lethal_fire_refused(self):
        t = Terrain(5, 1, threat={(2, 0)})
        route, blocked = safe_path(t, (0, 0), (4, 0), survives=lambda r: False)
        self.assertIsNone(route)
        self.assertTrue(blocked)

    def test_no_route_at_all_is_not_fire(self):
        t = Terrain(5, 1, blocked={(2, 0)})
        self.assertEqual(safe_path(t, (0, 0), (4, 0)), (None, False))


class KeepsRouteOpenTests(unittest.TestCase):
    def test_corridor_site_refused(self):
        t = Terrain(5, 3, blocked=wall_column(2, 3, gap=1))
        self.assertFalse(keeps_route_open(t, (2, 1), (0, 1), (4, 1)))

    def test_off_route_site_allowed(self):
        t = Terrain(5, 3)
        self.assertTrue(keeps_route_open(t, (2, 2), (0, 1), (4, 1)))

    def test_baseline_reused(self):
        t = Terrain(5, 3, blocked=wall_column(2, 3, gap=1))
        baseline = set(path(t, (0, 1), (4, 1)))
        self.assertFalse(keeps_route_open(t, (2, 1), (0, 1), (4, 1), baseline=baseline))
        self.assertTrue(keeps_route_open(t, (0, 0), (0, 1), (4, 1), baseline=baseline))

    def test_goal_and_source_exempt(self):
        t = Terrain(3, 1)
        self.assertTrue(keeps_route_open(t, (2, 0), (0, 0), (2, 0)))
        self.assertTrue(keeps_route_open(t, (0, 0), (0, 0), (2, 0)))


if __name__ == "__main__":
    unittest.main()
