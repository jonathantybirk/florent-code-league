"""Regression tests for bots/test/econ's expected_titanium_schedule and
expected_titanium_flow -- see bots/test/econ/README.md for the design this
guards against regressing: dynamic per-Splitter weighting (1 / live
outputs, not a hardcoded 1/3), vision-gated traversal, same-team-only
feeders, and the round-by-round schedule bucketing a stack by exactly how
many tiles -- rounds -- it has left to travel, not "sometime within N".
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fcode import Direction, EntityType, Position, ResourceType, Team

from botimport import bot_on_path
from fake_controller import World

ECON_DIR = Path(__file__).resolve().parent.parent / "bots" / "test" / "econ"


def _import_econ():
    with bot_on_path(ECON_DIR):
        return importlib.import_module("main")


econ = _import_econ()

TI = ResourceType.TITANIUM
CORE_POS = Position(10, 10)
# The Core's 2x2 footprint anchored at CORE_POS: (10,10),(11,10),(10,11),(11,11).
# Everything below approaches it from the west, through (9, 10).


def _world_with_core(width: int = 40, height: int = 40) -> tuple[World, int]:
    world = World(width=width, height=height)
    core_id = world.spawn(CORE_POS, Team.A, EntityType.CORE)
    return world, core_id


def _core_ct(world: World, core_id: int):
    return world.controller_for(core_id)


# --- expected_titanium_schedule: plain Conveyor chains -----------------------


def test_straight_chain_buckets_each_stack_by_its_own_distance():
    world, core_id = _world_with_core()
    # dist 1, 2, 3 west of the Core, all facing EAST (toward it), all holding.
    for dist in (1, 2, 3):
        cid = world.spawn(Position(10 - dist, 10), Team.A, EntityType.CONVEYOR, Direction.EAST)
        world.set_stored_resource(cid, TI)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 3)
    assert schedule == [10.0, 10.0, 10.0]


def test_empty_conveyor_contributes_nothing():
    world, core_id = _world_with_core()
    cid = world.spawn(Position(9, 10), Team.A, EntityType.CONVEYOR, Direction.EAST)
    world.set_stored_resource(cid, None)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 1)
    assert schedule == [0.0]


def test_conveyor_facing_away_from_core_is_not_a_feeder():
    world, core_id = _world_with_core()
    # Adjacent to the Core, holding titanium, but facing WEST (away) --
    # geometry alone (adjacency) must not be enough to count it.
    cid = world.spawn(Position(9, 10), Team.A, EntityType.CONVEYOR, Direction.WEST)
    world.set_stored_resource(cid, TI)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 1)
    assert schedule == [0.0]


def test_conveyor_beyond_the_requested_window_is_excluded():
    world, core_id = _world_with_core()
    for dist in (1, 2, 3):
        cid = world.spawn(Position(10 - dist, 10), Team.A, EntityType.CONVEYOR, Direction.EAST)
        world.set_stored_resource(cid, TI)

    # Only asking for 2 rounds: the dist-3 tile must never even be reached,
    # let alone counted -- it's one hop past where _accumulate stops.
    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 2)
    assert schedule == [10.0, 10.0]


def test_fan_in_sums_multiple_feeders_of_the_same_tile():
    world, core_id = _world_with_core()
    # A plain Conveyor accepts from any of its 3 non-output sides. Feed
    # (9, 10) -- which faces EAST into the Core -- from its other three
    # sides at once: three independent stacks, all one hop further out,
    # all landing in the Core within 2 rounds.
    hub = world.spawn(Position(9, 10), Team.A, EntityType.CONVEYOR, Direction.EAST)
    world.set_stored_resource(hub, TI)
    north = world.spawn(Position(9, 9), Team.A, EntityType.CONVEYOR, Direction.SOUTH)
    world.set_stored_resource(north, TI)
    south = world.spawn(Position(9, 11), Team.A, EntityType.CONVEYOR, Direction.NORTH)
    world.set_stored_resource(south, TI)
    west = world.spawn(Position(8, 10), Team.A, EntityType.CONVEYOR, Direction.EAST)
    world.set_stored_resource(west, TI)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 2)
    # hop 1: hub only (10). hop 2: north + south + west, all feeding hub (30).
    assert schedule == [10.0, 30.0]


# --- Splitter weight: 1 / live outputs ----------------------------------------


def test_splitter_with_one_live_output_has_weight_one():
    world, core_id = _world_with_core()
    splitter = world.spawn(Position(9, 10), Team.A, EntityType.SPLITTER, Direction.EAST)
    world.set_stored_resource(splitter, TI)
    # NORTH (9,9) and SOUTH (9,11) of the splitter are left empty -- only
    # its EAST side (into the Core) is actually built.

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 1)
    assert schedule == [10.0]


def test_splitter_with_two_live_outputs_has_weight_one_half():
    world, core_id = _world_with_core()
    splitter = world.spawn(Position(9, 10), Team.A, EntityType.SPLITTER, Direction.EAST)
    world.set_stored_resource(splitter, TI)
    # A second Conveyor on the splitter's NORTH side -- a genuinely live
    # second output, verified against the real engine to change the
    # rotation (see bots/test/splitter_probe): the splitter's own weight
    # toward the Core is now 1/2, not 1.
    world.spawn(Position(9, 9), Team.A, EntityType.CONVEYOR, Direction.NORTH)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 1)
    assert schedule == [5.0]


def test_splitter_with_three_live_outputs_has_weight_one_third():
    world, core_id = _world_with_core()
    splitter = world.spawn(Position(9, 10), Team.A, EntityType.SPLITTER, Direction.EAST)
    world.set_stored_resource(splitter, TI)
    world.spawn(Position(9, 9), Team.A, EntityType.CONVEYOR, Direction.NORTH)
    world.spawn(Position(9, 11), Team.A, EntityType.CONVEYOR, Direction.SOUTH)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 1)
    assert schedule[0] == pytest.approx(10.0 / 3.0)


def test_splitters_back_is_input_only_not_counted_as_a_live_output():
    world, core_id = _world_with_core()
    splitter = world.spawn(Position(9, 10), Team.A, EntityType.SPLITTER, Direction.EAST)
    world.set_stored_resource(splitter, TI)
    # A Conveyor on the splitter's WEST side (its back / input side) feeds
    # it -- and is a perfectly good Conveyor/Splitter/Core receiver by
    # _is_receiver's own rules -- but must not count toward the splitter's
    # *output* rotation. If it did, this would read weight 1/2, not 1.
    feeder = world.spawn(Position(8, 10), Team.A, EntityType.CONVEYOR, Direction.EAST)
    world.set_stored_resource(feeder, TI)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 2)
    assert schedule == [10.0, 10.0]


def test_barrier_on_a_splitter_side_does_not_count_as_a_receiver():
    world, core_id = _world_with_core()
    splitter = world.spawn(Position(9, 10), Team.A, EntityType.SPLITTER, Direction.EAST)
    world.set_stored_resource(splitter, TI)
    # A building sits on the splitter's NORTH side, but it's a Barrier --
    # nowhere to put titanium -- so it must not raise the live-output count
    # the way a second Conveyor would (see the two-live-outputs test above).
    world.spawn(Position(9, 9), Team.A, EntityType.BARRIER)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 1)
    assert schedule == [10.0]


def test_chained_splitters_compound_their_weights():
    world, core_id = _world_with_core()
    # Splitter A (hop 1, two live outputs -> weight 1/2) is fed by
    # Splitter B (hop 2, also two live outputs -> weight 1/2 of A's
    # weight). Cumulative weight at B is 1/2 * 1/2 = 1/4.
    a = world.spawn(Position(9, 10), Team.A, EntityType.SPLITTER, Direction.EAST)
    world.set_stored_resource(a, TI)
    world.spawn(Position(9, 9), Team.A, EntityType.CONVEYOR, Direction.SOUTH)  # A's 2nd output

    b = world.spawn(Position(8, 10), Team.A, EntityType.SPLITTER, Direction.EAST)
    world.set_stored_resource(b, TI)
    world.spawn(Position(8, 9), Team.A, EntityType.CONVEYOR, Direction.SOUTH)  # B's 2nd output

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 2)
    assert schedule[0] == pytest.approx(5.0)   # A: 10 * 1/2
    assert schedule[1] == pytest.approx(2.5)   # B: 10 * 1/2 * 1/2


# --- Team ownership and vision ------------------------------------------------


def test_enemy_conveyor_is_never_counted_even_if_perfectly_positioned():
    world, core_id = _world_with_core()
    cid = world.spawn(Position(9, 10), Team.B, EntityType.CONVEYOR, Direction.EAST)
    world.set_stored_resource(cid, TI)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 1)
    assert schedule == [0.0]


def test_enemy_receiver_does_not_inflate_a_splitters_live_output_count():
    world, core_id = _world_with_core()
    splitter = world.spawn(Position(9, 10), Team.A, EntityType.SPLITTER, Direction.EAST)
    world.set_stored_resource(splitter, TI)
    # An enemy Conveyor sits on the splitter's NORTH side -- a receiver by
    # type, but not by team. Must not count toward live outputs.
    world.spawn(Position(9, 9), Team.B, EntityType.CONVEYOR, Direction.SOUTH)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 1)
    assert schedule == [10.0]


def test_harvester_adjacent_to_core_does_not_crash_and_is_not_counted():
    # Harvesters aren't Conveyors or Splitters -- _feeder_at must reject
    # them by type before ever touching get_stored_resource, which would
    # raise GameError on a Harvester (see fake_controller.get_stored_resource).
    world, core_id = _world_with_core()
    world.spawn(Position(9, 10), Team.A, EntityType.HARVESTER)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 1)
    assert schedule == [0.0]


def test_conveyor_outside_vision_is_excluded():
    world, core_id = _world_with_core()
    # CORE_VISION_RADIUS_SQ is 36 (see fake_controller.VISION_RADIUS_SQ),
    # i.e. a straight-line reach of exactly 6 tiles from the Core's own
    # anchor tile. Lay a chain out to dist 7: dist 1..6 are in vision
    # (distance_sq 1..36), dist 7 is not (distance_sq 49).
    for dist in range(1, 8):
        cid = world.spawn(Position(10 - dist, 10), Team.A, EntityType.CONVEYOR, Direction.EAST)
        world.set_stored_resource(cid, TI)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 8)
    # dist 1..6 count; dist 7 (and the never-built dist 8) don't. Rounds 4
    # and 8 (index 3 and index 7) also pick up the passive tick.
    assert schedule == [10.0, 10.0, 10.0, 20.0, 10.0, 10.0, 0.0, 10.0]


def test_out_of_vision_side_does_not_inflate_a_splitters_live_output_count():
    world, core_id = _world_with_core()
    splitter = world.spawn(Position(9, 10), Team.A, EntityType.SPLITTER, Direction.EAST)
    world.set_stored_resource(splitter, TI)
    # A second Conveyor exists on the splitter's NORTH side, same team,
    # correct type -- but placed far enough that it's outside the Core's
    # vision. _is_receiver must treat it as unconfirmed, not live.
    far_north = Position(9, 9 - 100)
    world.spawn(far_north, Team.A, EntityType.CONVEYOR, Direction.SOUTH)

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 1)
    assert schedule == [10.0]


# --- The passive trickle, and its round-based (not index-based) placement ----


def test_passive_income_lands_on_the_correct_future_round():
    world, core_id = _world_with_core()
    assert world.round == 0
    # From round 0, the next four rounds are 1, 2, 3, 4 -- only round 4 is
    # a multiple of PASSIVE_TITANIUM_INTERVAL.
    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 4)
    assert schedule == [0.0, 0.0, 0.0, 10.0]


def test_passive_income_phase_follows_current_round_not_the_index():
    world, core_id = _world_with_core()
    for _ in range(2):
        world.advance_round()
    assert world.round == 2
    # From round 2: future rounds 3, 4, 5, 6, 7, 8 -- multiples of 4 are 4
    # and 8, landing at index 1 and index 5, not index 3 as it would from
    # round 0.
    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 6)
    assert schedule == [0.0, 10.0, 0.0, 0.0, 0.0, 10.0]


def test_pipeline_and_passive_income_add_within_the_same_round():
    world, core_id = _world_with_core()
    # The walk has to reach dist 4 by hopping through dist 1..3 -- an
    # isolated Conveyor 4 tiles out with nothing connecting it to the Core
    # is invisible to _feeder_at no matter what it holds, so the
    # intermediate segments must exist too (holding nothing themselves).
    for dist in (1, 2, 3):
        world.spawn(Position(10 - dist, 10), Team.A, EntityType.CONVEYOR, Direction.EAST)
    cid = world.spawn(Position(6, 10), Team.A, EntityType.CONVEYOR, Direction.EAST)
    world.set_stored_resource(cid, TI)  # dist 4 -> schedule[3], same slot as the passive tick

    schedule = econ.expected_titanium_schedule(_core_ct(world, core_id), 4)
    assert schedule == [0.0, 0.0, 0.0, 20.0]


# --- expected_titanium_flow: the 4-round average -----------------------------


def test_flow_is_the_average_of_the_first_four_schedule_entries():
    world, core_id = _world_with_core()
    a = world.spawn(Position(9, 10), Team.A, EntityType.CONVEYOR, Direction.EAST)
    world.set_stored_resource(a, TI)
    b = world.spawn(Position(6, 10), Team.A, EntityType.CONVEYOR, Direction.EAST)
    world.set_stored_resource(b, TI)

    ct = _core_ct(world, core_id)
    schedule = econ.expected_titanium_schedule(ct, 4)
    assert econ.expected_titanium_flow(ct) == pytest.approx(sum(schedule) / 4)


# --- Misuse guards -------------------------------------------------------------


def test_schedule_from_a_non_core_unit_raises():
    world, core_id = _world_with_core()
    builder_id = world.spawn(Position(9, 10), Team.A, EntityType.BUILDER_BOT)
    with pytest.raises(ValueError):
        econ.expected_titanium_schedule(world.controller_for(builder_id), 4)


def test_flow_from_a_non_core_unit_raises():
    world, core_id = _world_with_core()
    builder_id = world.spawn(Position(9, 10), Team.A, EntityType.BUILDER_BOT)
    with pytest.raises(ValueError):
        econ.expected_titanium_flow(world.controller_for(builder_id))


def test_schedule_rejects_fewer_than_one_round():
    world, core_id = _world_with_core()
    with pytest.raises(ValueError):
        econ.expected_titanium_schedule(_core_ct(world, core_id), 0)


# --- _core_footprint --------------------------------------------------------


def test_core_footprint_is_exactly_the_four_footprint_tiles():
    world, core_id = _world_with_core()
    footprint = set(econ._core_footprint(_core_ct(world, core_id)))
    assert footprint == {Position(10, 10), Position(11, 10), Position(10, 11), Position(11, 11)}
