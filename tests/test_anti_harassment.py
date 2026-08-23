"""Regression tests for bots/test/strategies/anti_harassment: harasser
detection (find_active_harassers, vision- and team-gated), escape-tile
computation (escape_tiles, reusing bots/test/strategies/defensive's
threat geometry against a live-read friendly turret), and blocker
selection (best_blocking_tile). Uses tests/fake_controller.World, same
pattern as test_econ2.py, since this module makes live ct calls (unlike
test_defensive.py's pure-Python module).
"""

from __future__ import annotations

import importlib
from pathlib import Path

from fcode import Direction, EntityType, Position, Team

from botimport import bot_on_path
from fake_controller import World

ANTI_HARASSMENT_DIR = Path(__file__).resolve().parent.parent / "bots" / "test" / "strategies" / "anti_harassment"


def _import_anti_harassment():
    with bot_on_path(ANTI_HARASSMENT_DIR):
        return importlib.import_module("main")


anti_harassment = _import_anti_harassment()

GUNNER = EntityType.GUNNER
SENTINEL = EntityType.SENTINEL
BUILDER = EntityType.BUILDER_BOT
CONVEYOR = EntityType.CONVEYOR


def infra(x, y, etype=CONVEYOR):
    return anti_harassment.FriendlyInfra(position=Position(x, y), etype=etype)


# --- find_active_harassers ---

def test_finds_enemy_builder_adjacent_to_infra():
    world = World(width=30, height=30)
    core_id = world.spawn(Position(0, 0), Team.A, EntityType.CORE)
    world.spawn(Position(4, 0), Team.A, CONVEYOR, Direction.EAST)
    enemy_id = world.spawn(Position(5, 0), Team.B, BUILDER)  # adjacent east of the conveyor

    ct = world.controller_for(core_id)
    result = anti_harassment.find_active_harassers(ct, [infra(4, 0)])
    assert result == {enemy_id: Position(5, 0)}


def test_finds_enemy_builder_standing_on_infra_itself():
    # Conveyor/Splitter tiles are Builder-Bot-passable -- a harasser can
    # be standing directly on the infra tile it's attacking sideways from.
    world = World(width=30, height=30)
    core_id = world.spawn(Position(0, 0), Team.A, EntityType.CORE)
    world.spawn(Position(4, 0), Team.A, CONVEYOR, Direction.EAST)
    enemy_id = world.spawn(Position(4, 0), Team.B, BUILDER)

    ct = world.controller_for(core_id)
    result = anti_harassment.find_active_harassers(ct, [infra(4, 0)])
    assert result == {enemy_id: Position(4, 0)}


def test_ignores_a_friendly_builder_near_infra():
    world = World(width=30, height=30)
    core_id = world.spawn(Position(0, 0), Team.A, EntityType.CORE)
    world.spawn(Position(4, 0), Team.A, CONVEYOR, Direction.EAST)
    world.spawn(Position(5, 0), Team.A, BUILDER)  # friendly, not a harasser

    ct = world.controller_for(core_id)
    assert anti_harassment.find_active_harassers(ct, [infra(4, 0)]) == {}


def test_ignores_infra_outside_this_units_vision():
    world = World(width=30, height=30)
    core_id = world.spawn(Position(0, 0), Team.A, EntityType.CORE)  # CORE_VISION_RADIUS_SQ=36
    world.spawn(Position(20, 20), Team.A, CONVEYOR, Direction.EAST)  # far outside vision
    world.spawn(Position(21, 20), Team.B, BUILDER)

    ct = world.controller_for(core_id)
    assert anti_harassment.find_active_harassers(ct, [infra(20, 20)]) == {}


def test_ignores_enemy_not_adjacent_to_any_infra():
    world = World(width=30, height=30)
    core_id = world.spawn(Position(0, 0), Team.A, EntityType.CORE)
    world.spawn(Position(4, 0), Team.A, CONVEYOR, Direction.EAST)
    world.spawn(Position(4, 3), Team.B, BUILDER)  # in vision, but not adjacent to the conveyor

    ct = world.controller_for(core_id)
    assert anti_harassment.find_active_harassers(ct, [infra(4, 0)]) == {}


# --- escape_tiles ---

def test_escape_tiles_all_four_open_with_no_covering_turret():
    world = World(width=30, height=30)
    core_id = world.spawn(Position(0, 0), Team.A, EntityType.CORE)
    ct = world.controller_for(core_id)

    escapes = anti_harassment.escape_tiles(ct, Position(10, 10), friendly_turret_ids=[])
    assert set(escapes) == {Position(10, 9), Position(11, 10), Position(10, 11), Position(9, 10)}


def test_escape_tiles_excludes_a_tile_covered_by_a_friendly_gunner():
    world = World(width=30, height=30)
    core_id = world.spawn(Position(0, 0), Team.A, EntityType.CORE)
    # Gunner just east of the harasser's own tile -- well within
    # GUNNER_RANGE_SQ=13 of the east escape tile (11,10).
    gunner_id = world.spawn(Position(13, 10), Team.A, GUNNER, Direction.WEST)

    ct = world.controller_for(core_id)
    escapes = anti_harassment.escape_tiles(ct, Position(10, 10), friendly_turret_ids=[gunner_id])
    assert Position(11, 10) not in escapes
    assert Position(9, 10) in escapes  # west is far outside the gunner's range


def test_escape_tiles_excludes_a_wall_tile():
    world = World(width=30, height=30, walls=frozenset({Position(10, 9)}))
    core_id = world.spawn(Position(0, 0), Team.A, EntityType.CORE)
    ct = world.controller_for(core_id)

    escapes = anti_harassment.escape_tiles(ct, Position(10, 10), friendly_turret_ids=[])
    assert Position(10, 9) not in escapes
    assert len(escapes) == 3


def test_escape_tiles_excludes_a_tile_occupied_by_another_builder():
    world = World(width=30, height=30)
    core_id = world.spawn(Position(0, 0), Team.A, EntityType.CORE)
    world.spawn(Position(11, 10), Team.A, BUILDER)  # occupies the east tile
    ct = world.controller_for(core_id)

    escapes = anti_harassment.escape_tiles(ct, Position(10, 10), friendly_turret_ids=[])
    assert Position(11, 10) not in escapes
    assert len(escapes) == 3


def test_escape_tiles_ignores_a_turret_that_no_longer_reads_as_a_turret():
    world = World(width=30, height=30)
    core_id = world.spawn(Position(0, 0), Team.A, EntityType.CORE)
    ct = world.controller_for(core_id)

    # An id that was never spawned as a turret at all -- _read_turret must
    # not blow up escape_tiles, just skip it (see its own None-return doc).
    escapes = anti_harassment.escape_tiles(ct, Position(10, 10), friendly_turret_ids=[9999])
    assert len(escapes) == 4


def test_escape_tiles_none_when_a_sentinel_covers_every_side():
    world = World(width=30, height=30)
    core_id = world.spawn(Position(0, 0), Team.A, EntityType.CORE)
    s1 = world.spawn(Position(16, 10), Team.A, SENTINEL, Direction.WEST)  # covers (11,10)
    s2 = world.spawn(Position(4, 10), Team.A, SENTINEL, Direction.EAST)  # covers (9,10)
    s3 = world.spawn(Position(10, 4), Team.A, SENTINEL, Direction.SOUTH)  # covers (10,9)
    s4 = world.spawn(Position(10, 16), Team.A, SENTINEL, Direction.NORTH)  # covers (10,11)

    ct = world.controller_for(core_id)
    escapes = anti_harassment.escape_tiles(ct, Position(10, 10), friendly_turret_ids=[s1, s2, s3, s4])
    assert escapes == []


# --- best_blocking_tile ---

def test_best_blocking_tile_picks_the_nearest_escape():
    escapes = [Position(11, 10), Position(10, 15)]
    assert anti_harassment.best_blocking_tile(escapes, Position(11, 9)) == Position(11, 10)


def test_best_blocking_tile_none_when_nothing_to_block():
    assert anti_harassment.best_blocking_tile([], Position(0, 0)) is None
