"""Regression tests for bots/test/strategies/defensive's turret threat
geometry: threatens/is_safe (the safety half), gunner_coverage/
best_sentinel_facing/best_cluster_placement (the offense half), and
safe_heal_tile. Pure functions on fcode.Position/Direction -- no
Controller or fake_controller.World needed, since this module never calls
ct.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from fcode import Direction, EntityType, Position

from botimport import bot_on_path

DEFENSIVE_DIR = Path(__file__).resolve().parent.parent / "bots" / "test" / "strategies" / "defensive"


def _import_defensive():
    with bot_on_path(DEFENSIVE_DIR):
        return importlib.import_module("main")


defensive = _import_defensive()

GUNNER = EntityType.GUNNER
SENTINEL = EntityType.SENTINEL
LAUNCHER = EntityType.LAUNCHER


def turret(x, y, etype, direction=None):
    return defensive.EnemyTurret(position=Position(x, y), etype=etype, direction=direction)


# --- threatens() / is_safe() -- Gunner ---

def test_gunner_threatens_within_range_circle():
    g = turret(10, 10, GUNNER)
    # distance_squared((10,10),(13,10)) == 9 <= 13
    assert defensive.threatens(g, Position(13, 10)) is True


def test_gunner_does_not_threaten_outside_range_circle():
    g = turret(10, 10, GUNNER)
    # distance_squared((10,10),(14,10)) == 16 > 13
    assert defensive.threatens(g, Position(14, 10)) is False


def test_gunner_threat_ignores_cached_facing_since_it_can_rotate():
    # Facing WEST, but a tile to the EAST is still in range -- rotation
    # means the cached facing is not trustworthy for safety purposes.
    g = turret(10, 10, GUNNER, direction=Direction.WEST)
    assert defensive.threatens(g, Position(12, 10)) is True


def test_gunner_range_boundary_is_inclusive():
    g = turret(0, 0, GUNNER)
    on_boundary = next(
        p for p in (Position(x, y) for x in range(-4, 5) for y in range(-4, 5))
        if p.distance_squared(Position(0, 0)) == defensive.GUNNER_RANGE_SQ
    )
    assert defensive.threatens(g, on_boundary) is True


# --- threatens() -- Sentinel ---

def test_sentinel_with_known_facing_only_threatens_its_own_ray():
    s = turret(10, 10, SENTINEL, direction=Direction.EAST)
    assert defensive.threatens(s, Position(15, 10)) is True  # on the ray, in range
    assert defensive.threatens(s, Position(10, 15)) is False  # off the ray entirely
    assert defensive.threatens(s, Position(5, 10)) is False  # behind it, not forward


def test_sentinel_with_known_facing_is_safe_off_axis_even_close():
    # The user's "place a gunner outside its direction" idea: adjacent but
    # off the fixed facing is safe regardless of distance.
    s = turret(10, 10, SENTINEL, direction=Direction.EAST)
    assert defensive.threatens(s, Position(10, 11)) is False


def test_sentinel_range_is_farther_than_gunners():
    s = turret(0, 0, SENTINEL, direction=Direction.EAST)
    far = Position(5, 0)  # distance_squared 25: > GUNNER_RANGE_SQ, <= SENTINEL_RANGE_SQ
    assert far.distance_squared(Position(0, 0)) > defensive.GUNNER_RANGE_SQ
    assert defensive.threatens(s, far) is True


def test_sentinel_with_unknown_facing_is_conservative_on_every_axis():
    s = turret(10, 10, SENTINEL, direction=None)
    # East and northeast axes, both unconfirmed -- must be treated as live.
    assert defensive.threatens(s, Position(15, 10)) is True
    assert defensive.threatens(s, Position(14, 14)) is True  # NE axis, distance_sq 32 == boundary
    # Off every one of the 8 axes entirely -- safe even unknown.
    assert defensive.threatens(s, Position(12, 11)) is False


def test_sentinel_diagonal_ray_requires_exact_diagonal_alignment():
    s = turret(10, 10, SENTINEL, direction=Direction.SOUTHEAST)
    assert defensive.threatens(s, Position(13, 13)) is True
    assert defensive.threatens(s, Position(13, 12)) is False


# --- threatens() -- Launcher never threatens a building ---

def test_launcher_never_threatens_a_turret():
    l = turret(10, 10, LAUNCHER)
    assert defensive.threatens(l, Position(10, 11)) is False
    assert defensive.threatens(l, Position(10, 10)) is False


# --- is_safe() ---

def test_is_safe_false_if_any_enemy_threatens():
    enemies = [turret(0, 0, GUNNER), turret(20, 20, SENTINEL, direction=Direction.WEST)]
    assert defensive.is_safe(Position(2, 0), enemies) is False  # in gunner range


def test_is_safe_true_if_no_enemy_threatens():
    enemies = [turret(0, 0, GUNNER), turret(20, 20, SENTINEL, direction=Direction.WEST)]
    assert defensive.is_safe(Position(9, 9), enemies) is True


# --- gunner_coverage() ---

def test_gunner_coverage_counts_every_enemy_in_range_regardless_of_axis():
    enemies = [turret(3, 0, GUNNER), turret(0, 3, SENTINEL), turret(100, 100, GUNNER)]
    assert defensive.gunner_coverage(Position(0, 0), enemies) == 2


def test_gunner_coverage_excludes_a_same_tile_entry():
    enemies = [turret(5, 5, GUNNER)]
    assert defensive.gunner_coverage(Position(5, 5), enemies) == 0


# --- best_sentinel_facing() ---

def test_best_sentinel_facing_picks_the_axis_with_more_enemies():
    # Two enemies due east, one due south -- east should win.
    enemies = [turret(3, 0, GUNNER), turret(5, 0, GUNNER), turret(0, 3, GUNNER)]
    facing, count = defensive.best_sentinel_facing(Position(0, 0), enemies)
    assert facing == Direction.EAST
    assert count == 2


def test_best_sentinel_facing_none_when_nothing_aligns():
    enemies = [turret(3, 1, GUNNER)]  # off every one of the 8 axes
    facing, count = defensive.best_sentinel_facing(Position(0, 0), enemies)
    assert facing is None
    assert count == 0


# --- best_cluster_placement() ---

def test_best_cluster_placement_prefers_safe_high_coverage_candidate():
    # A tight cluster of 2 adjacent gunners; a sentinel built just out of
    # their range, aligned on the row, threatens both while staying safe
    # -- GUNNER_RANGE_SQ=13 and SENTINEL_RANGE_SQ=32 only leave a distance
    # of 4-5 tiles that is simultaneously safe and in range, so only a
    # tightly-packed cluster is coverable by one Sentinel this way.
    enemies = [turret(20, 10, GUNNER), turret(21, 10, GUNNER)]
    candidates = [Position(x, 10) for x in (14, 15, 16, 30)]
    placement = defensive.best_cluster_placement(candidates, enemies)
    assert placement is not None
    assert placement.position == Position(16, 10)
    assert placement.turret_type == SENTINEL
    assert placement.facing == Direction.EAST
    assert placement.coverage == 2
    assert defensive.is_safe(placement.position, enemies) is True


def test_best_cluster_placement_rejects_unsafe_candidates():
    enemies = [turret(10, 10, GUNNER)]
    # Every candidate sits inside the gunner's own range circle.
    candidates = [Position(11, 10), Position(10, 11), Position(9, 10)]
    assert defensive.best_cluster_placement(candidates, enemies) is None


def test_best_cluster_placement_none_when_nothing_covers_anything():
    enemies = [turret(100, 100, GUNNER)]
    candidates = [Position(0, 0), Position(1, 1)]
    assert defensive.best_cluster_placement(candidates, enemies) is None


def test_best_cluster_placement_can_be_restricted_to_one_turret_type():
    # An enemy Sentinel facing NORTH threatens nothing to its east, so a
    # Gunner at distance_sq 9 (<= GUNNER_RANGE_SQ) is both safe and able
    # to cover it -- restricting to GUNNER should return this, not fall
    # through to no placement.
    enemies = [turret(10, 10, SENTINEL, direction=Direction.NORTH)]
    candidates = [Position(13, 10)]
    placement = defensive.best_cluster_placement(candidates, enemies, turret_types=(GUNNER,))
    assert placement is not None
    assert placement.turret_type == GUNNER
    assert placement.facing is None
    assert placement.coverage == 1


# --- safe_heal_tile() ---

def test_safe_heal_tile_finds_the_untargeted_side():
    # A gunner east of the friendly turret threatens the east-adjacent
    # tile but not the other three.
    enemies = [turret(13, 10, GUNNER)]
    tile = defensive.safe_heal_tile(Position(10, 10), enemies)
    assert tile is not None
    assert defensive.is_safe(tile, enemies) is True
    assert tile != Position(11, 10)


def test_safe_heal_tile_none_when_every_adjacent_tile_is_threatened():
    # One sentinel per side, each facing in toward the friendly turret at
    # (10, 10) -- covers all 4 orthogonal neighbours, none of them safe.
    enemies = [
        turret(16, 10, SENTINEL, direction=Direction.WEST),  # covers (11, 10)
        turret(4, 10, SENTINEL, direction=Direction.EAST),  # covers (9, 10)
        turret(10, 4, SENTINEL, direction=Direction.SOUTH),  # covers (10, 9)
        turret(10, 16, SENTINEL, direction=Direction.NORTH),  # covers (10, 11)
    ]
    assert defensive.safe_heal_tile(Position(10, 10), enemies) is None
