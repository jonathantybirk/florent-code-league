"""Regression tests for bots/test/econ2's Path/Harvester reachability model:
_build_paths (the single reverse BFS from every Core tile), _find_entry,
_update_harvesters (per-harvester connectivity + per-tile flow aggregation),
and _observe_flow (the actual-flow EMA, vision-gated and stack-id-delta
based). Unlike bots/test/econ, this bot keeps its own cached self.map of
entity objects rather than querying the live Controller each time, so these
tests populate both the fake World (for the Controller calls _observe_flow
makes) and player.map (for the reachability graph) in lockstep -- see
place() below.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fcode import Direction, EntityType, Position, ResourceType, Team

from botimport import bot_on_path
from fake_controller import World

ECON2_DIR = Path(__file__).resolve().parent.parent / "bots" / "test" / "econ2"


def _import_econ2():
    with bot_on_path(ECON2_DIR):
        return importlib.import_module("main")


econ2 = _import_econ2()

TI = ResourceType.TITANIUM
CORE_POS = Position(10, 10)
# The Core's 2x2 footprint anchored at CORE_POS: (10,10),(11,10),(10,11),(11,11).


class MockEntity:
    """A minimal stand-in for whatever populates econ2's self.map -- just
    the .type/.direction attributes _accepts_from/_out_dirs read."""

    __slots__ = ("type", "direction")

    def __init__(self, type_, direction=None):
        self.type = type_
        self.direction = direction


def place(player, world, pos, etype, direction=None, team=Team.A):
    """Spawn in the fake World AND mirror into player.map, keeping the two
    representations (live Controller state vs. econ2's cached map) in sync,
    the way builder reports would in the real bot."""
    building_id = world.spawn(pos, team, etype, direction)
    player.map[pos.y][pos.x] = MockEntity(etype, direction)
    return building_id


def _world_with_core(width: int = 30, height: int = 30) -> tuple[World, int, "econ2.Player"]:
    world = World(width=width, height=height)
    core_id = world.spawn(CORE_POS, Team.A, EntityType.CORE)
    ct = world.controller_for(core_id)
    player = econ2.Player(ct)
    for dx in (0, 1):
        for dy in (0, 1):
            p = Position(CORE_POS.x + dx, CORE_POS.y + dy)
            player.map[p.y][p.x] = MockEntity(EntityType.CORE)
    return world, core_id, player


def _core_ct(world: World, core_id: int):
    return world.controller_for(core_id)


def _build_merge_scenario():
    """Straight conveyor chain (6,10)-harvester -> (7,10)->(8,10)->(9,10)->Core,
    plus a Splitter at (9,9) merging a second harvester in at (9,10) (the
    tile right before the Core), plus a fully disconnected third harvester.
    """
    world, core_id, player = _world_with_core()
    ct = _core_ct(world, core_id)

    place(player, world, Position(9, 10), EntityType.CONVEYOR, Direction.EAST)
    place(player, world, Position(8, 10), EntityType.CONVEYOR, Direction.EAST)
    place(player, world, Position(7, 10), EntityType.CONVEYOR, Direction.EAST)
    harvester_a = (6, 10)

    place(player, world, Position(9, 9), EntityType.SPLITTER, Direction.SOUTH)
    harvester_b = (9, 8)

    harvester_c = (25, 25)  # disconnected

    player.harvester_positions = [harvester_a, harvester_b, harvester_c]
    return world, ct, player, harvester_a, harvester_b, harvester_c


# --- _update_harvesters: connectivity, per-harvester paths, flow aggregation --


def test_straight_chain_is_connected_with_the_expected_path():
    world, ct, player, ha, hb, hc = _build_merge_scenario()
    player._update_harvesters(ct)

    by_pos = {h.position: h for h in player.harvesters}
    assert by_pos[ha].connected is True
    # (9,10) faces EAST straight into the Core -- a single hop, not a longer
    # chain -- so ha's route is (7,10)->(8,10)->(9,10)->Core.
    assert by_pos[ha].path == [(7, 10), (8, 10), (9, 10)]


def test_splitter_branch_merges_at_the_shared_tile_not_upstream():
    world, ct, player, ha, hb, hc = _build_merge_scenario()
    player._update_harvesters(ct)

    by_pos = {h.position: h for h in player.harvesters}
    # Splitter (9,9) feeds (9,10) directly, which then goes straight to the
    # Core -- hb never touches (8,10)/(7,10); those are only on ha's route.
    assert by_pos[hb].connected is True
    assert by_pos[hb].path == [(9, 9), (9, 10)]


def test_disconnected_harvester_has_no_path():
    world, ct, player, ha, hb, hc = _build_merge_scenario()
    player._update_harvesters(ct)

    by_pos = {h.position: h for h in player.harvesters}
    assert by_pos[hc].connected is False
    assert by_pos[hc].path is None


def test_shared_merge_tile_lists_every_upstream_harvester():
    world, ct, player, ha, hb, hc = _build_merge_scenario()
    player._update_harvesters(ct)

    # (9,10) is the genuine merge point: both ha (straight chain) and hb
    # (via the splitter) pass through it right before the Core.
    trunk = player.paths[(9, 10)]
    assert {h.position for h in trunk.harvesters} == {ha, hb}
    assert trunk.expected_flow == pytest.approx(2 * 10 / 4)  # 2 harvesters * 10 Ti / 4 rounds


def test_tile_upstream_of_the_merge_only_lists_its_own_branch():
    world, ct, player, ha, hb, hc = _build_merge_scenario()
    player._update_harvesters(ct)

    tip = player.paths[(7, 10)]
    assert {h.position for h in tip.harvesters} == {ha}


def test_harvester_directly_adjacent_to_core_has_an_empty_path():
    world, core_id, player = _world_with_core()
    ct = _core_ct(world, core_id)
    player.harvester_positions = [(9, 10)]  # directly west of the Core, zero conveyors

    player._update_harvesters(ct)

    h = player.harvesters[0]
    assert h.connected is True
    assert h.path == []


# --- _observe_flow: vision gating, id-delta arrival detection, EMA -----------


def test_observe_flow_from_a_non_core_unit_raises():
    world, ct, player, ha, hb, hc = _build_merge_scenario()
    player._update_harvesters(ct)
    builder_id = world.spawn(Position(20, 20), Team.A, EntityType.BUILDER_BOT)

    with pytest.raises(ValueError):
        player._observe_flow(world.controller_for(builder_id))


def test_observe_flow_treats_a_changed_stack_id_as_one_arrival():
    world, ct, player, ha, hb, hc = _build_merge_scenario()
    player._update_harvesters(ct)
    tip_id = world.building_at(Position(7, 10)).id
    assert player.paths[(7, 10)].actual_flow == 0.0

    world.set_stored_resource(tip_id, TI)
    player._observe_flow(ct)

    assert player.paths[(7, 10)].actual_flow == pytest.approx(econ2._FLOW_EMA_ALPHA * 10.0)


def test_observe_flow_treats_an_unchanged_stack_id_as_no_new_arrival():
    world, ct, player, ha, hb, hc = _build_merge_scenario()
    player._update_harvesters(ct)
    tip_id = world.building_at(Position(7, 10)).id
    world.set_stored_resource(tip_id, TI)
    player._observe_flow(ct)
    flow_after_arrival = player.paths[(7, 10)].actual_flow

    # Same stack still sitting there next round (backpressure) -- id unchanged.
    player._observe_flow(ct)

    assert player.paths[(7, 10)].actual_flow == pytest.approx(
        (1 - econ2._FLOW_EMA_ALPHA) * flow_after_arrival
    )


def test_observe_flow_detects_a_second_genuinely_new_stack():
    world, ct, player, ha, hb, hc = _build_merge_scenario()
    player._update_harvesters(ct)
    tip_id = world.building_at(Position(7, 10)).id
    world.set_stored_resource(tip_id, TI)
    player._observe_flow(ct)
    player._observe_flow(ct)  # stalled round, id unchanged
    flow_before = player.paths[(7, 10)].actual_flow

    world.set_stored_resource(tip_id, TI)  # fresh id: a new stack arrived
    player._observe_flow(ct)

    expected = econ2._FLOW_EMA_ALPHA * 10.0 + (1 - econ2._FLOW_EMA_ALPHA) * flow_before
    assert player.paths[(7, 10)].actual_flow == pytest.approx(expected)


def test_observe_flow_skips_tiles_outside_the_cores_vision():
    # CORE_VISION_RADIUS_SQ is 36 (fake_controller.VISION_RADIUS_SQ[CORE]).
    world, core_id, player = _world_with_core(width=70, height=30)
    ct = _core_ct(world, core_id)
    far = Position(CORE_POS.x + 50, CORE_POS.y)
    place(player, world, far, EntityType.CONVEYOR, Direction.WEST)
    player.paths = {(far.x, far.y): econ2.Path(position=(far.x, far.y))}

    player._observe_flow(ct)  # must not raise even though far is unseen

    assert player.paths[(far.x, far.y)].actual_flow == 0.0


# --- _build_paths: flow state survives a rebuild -----------------------------


def test_rebuilding_the_network_does_not_reset_actual_flow():
    world, ct, player, ha, hb, hc = _build_merge_scenario()
    player._update_harvesters(ct)
    tip_id = world.building_at(Position(7, 10)).id
    world.set_stored_resource(tip_id, TI)
    player._observe_flow(ct)
    flow_before = player.paths[(7, 10)].actual_flow
    assert flow_before > 0.0

    player._update_harvesters(ct)  # as if called again next round

    assert player.paths[(7, 10)].actual_flow == pytest.approx(flow_before)
