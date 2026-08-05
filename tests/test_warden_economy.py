"""Regression tests for bots/warden_'s ECONOMY mode route-laying (a
harvester's conveyor chain back to the Core) -- see bots/warden_/modes/
economy.py's module docstring for the bug history this guards against:
segments whose facing was *predicted* (from arrival direction, then from
pure axis geometry) rather than recorded from a move that already
happened, which looked connected on the map but didn't actually chain --
first at turns, then again on any map with a real obstacle to detour
around.
"""

from __future__ import annotations

from fcode import Direction, EntityType, Position, Team

from fake_controller import World
from warden_support import import_warden

warden = import_warden()
economy = warden.economy
BuilderState = warden.state.BuilderState

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


def _run_until_route_done(world: World, unit_id: int, state, max_rounds: int = 300) -> int | None:
    """Call economy.run() for unit_id once per round until the route
    state machine finishes (state.route_harvester goes back to None).
    Returns the round it finished on, or None if it never did within
    max_rounds (a timeout, not a silent pass).
    """
    for i in range(max_rounds):
        ct = world.controller_for(unit_id)
        economy.run(ct, state)
        world.advance_round()
        if state.route_harvester is None:
            return i
    return None


def _chain_reaches_core(world: World, start: Position, core_id: int, max_hops: int = 200) -> bool:
    """True if a conveyor chain, followed from `start` via each segment's
    own facing, reaches a tile adjacent to the Core within max_hops.
    This is the actual property that matters -- "conveyor tiles form a
    visually connected line" is not the same claim, and was the bug.
    """
    pos = start
    for _ in range(max_hops):
        b = world.building_at(pos)
        if b is None or b.etype != EntityType.CONVEYOR:
            return False
        next_pos = pos.add(b.direction)
        nb = world.building_at(next_pos)
        if nb is not None and nb.id == core_id:
            return True
        pos = next_pos
    return False


def test_route_connects_harvester_to_core_straight_line():
    world = World(width=20, height=20, ore=frozenset({Position(10, 3)}))
    core_id = world.spawn(Position(2, 2), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(9, 3), Team.A, EntityType.BUILDER_BOT)

    state = BuilderState()
    state.core_pos = Position(2, 2)

    finished = _run_until_route_done(world, builder_id, state)
    assert finished is not None, "route never completed within the round budget"

    harvester = world.building_at(Position(10, 3))
    assert harvester is not None and harvester.etype == EntityType.HARVESTER

    neighbors = [Position(10, 3).add(d) for d in CARDINALS]
    first_segments = [p for p in neighbors if (b := world.building_at(p)) is not None and b.etype == EntityType.CONVEYOR]
    assert first_segments, "no conveyor was ever placed on a harvester-adjacent tile"

    assert any(_chain_reaches_core(world, p, core_id) for p in first_segments), (
        "harvester has an adjacent conveyor, but no chain from it actually reaches the Core"
    )


def test_route_connects_harvester_to_core_requiring_axis_turn():
    # Core and ore not aligned on either axis, so the walk must switch
    # from horizontal to vertical partway -- this is exactly the shape
    # that broke the old try_move_toward-based approach (each segment's
    # facing pointed at the ultimate Core, not the next tile, so a turn
    # left a gap in the chain).
    world = World(width=25, height=25, ore=frozenset({Position(15, 12)}))
    core_id = world.spawn(Position(2, 2), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(14, 12), Team.A, EntityType.BUILDER_BOT)

    state = BuilderState()
    state.core_pos = Position(2, 2)

    finished = _run_until_route_done(world, builder_id, state)
    assert finished is not None, "route never completed within the round budget"

    neighbors = [Position(15, 12).add(d) for d in CARDINALS]
    first_segments = [p for p in neighbors if (b := world.building_at(p)) is not None and b.etype == EntityType.CONVEYOR]
    assert first_segments, "no conveyor was ever placed on a harvester-adjacent tile"

    assert any(_chain_reaches_core(world, p, core_id) for p in first_segments), (
        "chain broke at the horizontal-to-vertical turn"
    )


def test_route_connects_harvester_to_core_around_a_single_tile_obstacle():
    # A one-tile wall directly on the straight-line path forces a detour --
    # this is exactly the shape that broke the axis-priority-*prediction*
    # approach: predicting a segment's facing from pure geometry (blind to
    # the wall forcing a real detour) built a conveyor pointing straight
    # into the wall instead of following the path actually taken. Facing
    # decided only from an already-successful move can't make that mistake.
    world = World(width=20, height=20, ore=frozenset({Position(10, 3)}), walls=frozenset({Position(5, 3)}))
    core_id = world.spawn(Position(2, 2), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(9, 3), Team.A, EntityType.BUILDER_BOT)

    state = BuilderState()
    state.core_pos = Position(2, 2)

    finished = _run_until_route_done(world, builder_id, state)
    assert finished is not None, "route never completed within the round budget"

    neighbors = [Position(10, 3).add(d) for d in CARDINALS]
    first_segments = [p for p in neighbors if (b := world.building_at(p)) is not None and b.etype == EntityType.CONVEYOR]
    assert first_segments, "no conveyor was ever placed on a harvester-adjacent tile"

    assert any(_chain_reaches_core(world, p, core_id) for p in first_segments), (
        "chain broke while detouring around the obstacle"
    )


def test_pick_axis_direction_prefers_horizontal_gap():
    world = World(width=20, height=20)
    world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)
    ct = world.controller_for(1)
    assert economy._pick_axis_direction(ct, Position(5, 5), Position(10, 8)) == Direction.EAST


def test_pick_axis_direction_falls_back_to_vertical_when_horizontal_aligned():
    world = World(width=20, height=20)
    world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)
    ct = world.controller_for(1)
    assert economy._pick_axis_direction(ct, Position(5, 5), Position(5, 9)) == Direction.SOUTH


def test_connection_facing_detects_an_adjacent_core():
    # Core footprint is (2,2)-(3,3) (2x2), so its east edge is x=3. Target
    # is irrelevant when a Core is adjacent -- the Core always counts.
    world = World(width=20, height=20)
    world.spawn(Position(2, 2), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(4, 2), Team.A, EntityType.BUILDER_BOT)
    ct = world.controller_for(builder_id)

    assert economy._connection_facing(ct, Position(4, 2), Position(99, 99)) == Direction.WEST


def test_connection_facing_none_when_nowhere_near_anything():
    world = World(width=20, height=20)
    world.spawn(Position(2, 2), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(15, 15), Team.A, EntityType.BUILDER_BOT)
    ct = world.controller_for(builder_id)

    assert economy._connection_facing(ct, Position(15, 15), Position(99, 99)) is None


def test_connection_facing_matches_only_the_specific_target_conveyor():
    # pos is adjacent to two friendly Conveyors -- only the one matching
    # target should count. The route's own just-built segments are also
    # adjacent friendly Conveyors, and treating any of them as a valid
    # connection would end the route against itself instead of the
    # intended target -- see this function's docstring.
    world = World(width=20, height=20)
    builder_id = world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)
    world.spawn(Position(6, 5), Team.A, EntityType.CONVEYOR, Direction.WEST)  # not the target
    world.spawn(Position(5, 4), Team.A, EntityType.CONVEYOR, Direction.SOUTH)  # the target
    ct = world.controller_for(builder_id)

    assert economy._connection_facing(ct, Position(5, 5), Position(5, 4)) == Direction.NORTH
    assert economy._connection_facing(ct, Position(5, 5), Position(99, 99)) is None


def test_find_nearest_friendly_conveyor_prefers_the_closer_tile():
    world = World(width=20, height=20)
    builder_id = world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)
    world.spawn(Position(5, 8), Team.A, EntityType.CONVEYOR, Direction.WEST)  # dist_sq=9
    world.spawn(Position(9, 5), Team.A, EntityType.CONVEYOR, Direction.WEST)  # dist_sq=16
    ct = world.controller_for(builder_id)

    assert economy._find_nearest_friendly_conveyor(ct) == Position(5, 8)


def test_new_harvester_joins_the_nearest_existing_conveyor_instead_of_the_core():
    world = World(width=40, height=40, ore=frozenset({Position(20, 8)}))
    core_id = world.spawn(Position(2, 2), Team.A, EntityType.CORE)

    # A pre-existing trunk from an earlier harvester, already connected to
    # the Core: a straight line at y=3 facing WEST, terminating adjacent
    # to the Core's footprint.
    trunk_positions = {Position(x, 3) for x in range(4, 21)}
    for p in trunk_positions:
        world.spawn(p, Team.A, EntityType.CONVEYOR, Direction.WEST)

    # This builder's ore is only 4 tiles from the trunk but ~25 tiles
    # from the literal Core -- it should join the trunk, not route home
    # on its own.
    builder_id = world.spawn(Position(20, 7), Team.A, EntityType.BUILDER_BOT)
    state = BuilderState()
    state.core_pos = Position(2, 2)

    finished = _run_until_route_done(world, builder_id, state)
    assert finished is not None, "route never completed within the round budget"

    new_conveyors = [
        e for e in world.entities.values()
        if e.etype == EntityType.CONVEYOR and e.pos not in trunk_positions
    ]
    assert 0 < len(new_conveyors) < 10, (
        f"expected a short join to the trunk, got {len(new_conveyors)} new segments"
    )

    harvester = world.building_at(Position(20, 8))
    assert harvester is not None and harvester.etype == EntityType.HARVESTER

    neighbors = [Position(20, 8).add(d) for d in CARDINALS]
    first_segments = [p for p in neighbors if (b := world.building_at(p)) is not None and b.etype == EntityType.CONVEYOR]
    assert first_segments, "no conveyor was ever placed on a harvester-adjacent tile"
    assert any(_chain_reaches_core(world, p, core_id) for p in first_segments), (
        "joined route never actually reaches the Core through the trunk"
    )
