"""Regression tests for bots/warden_'s DEFENCE mode turret placement --
see modes/defence.py's module docstring: a turret must land on the side
of the Core actually facing the threat, not wherever the defending
Builder happened to be standing when a threat was first noticed (which
could just as easily be the opposite side, i.e. useless).
"""

from __future__ import annotations

from fcode import Direction, EntityType, Position, Team

from fake_controller import World
from warden_support import import_warden

warden = import_warden()
defence = warden.defence
BuilderState = warden.state.BuilderState
SLOT_THREAT_POS = warden.constants.SLOT_THREAT_POS


def test_guard_position_biases_toward_the_threat():
    core_pos = Position(10, 10)
    threat_pos = Position(20, 10)  # due east
    assert defence._guard_position(core_pos, threat_pos, ring_radius_sq=9) == Position(13, 10)


def test_guard_position_falls_back_to_core_with_no_known_threat():
    core_pos = Position(10, 10)
    assert defence._guard_position(core_pos, None, ring_radius_sq=9) == core_pos


def test_defender_walks_to_the_threatened_side_before_building():
    # The defender starts WEST of the Core; the only known threat (via the
    # Core's broadcast, not the defender's own vision -- it starts far out
    # of the defender's DEFENCE_RADIUS_SQ) is due EAST. A turret built at
    # the defender's starting spot would face away from the threat --
    # exactly the "turret behind the Core" bug report this guards against.
    world = World(width=40, height=40)
    core_id = world.spawn(Position(20, 20), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(14, 20), Team.A, EntityType.BUILDER_BOT)
    world.spawn(Position(30, 20), Team.B, EntityType.BUILDER_BOT)

    # Simulate the Core having already broadcast the threat's position.
    world.store[Team.A][SLOT_THREAT_POS] = warden.toolbox.pack_pos(Position(30, 20))

    state = BuilderState()
    state.core_pos = Position(20, 20)

    for _ in range(60):
        ct = world.controller_for(builder_id)
        defence.run(ct, state)
        world.advance_round()

    gunners = [e for e in world.entities.values() if e.etype == EntityType.GUNNER and e.team == Team.A]
    assert gunners, "no Gunner was ever built"
    # Not strictly "due east of the Core's centre" -- a single wandering
    # defender scatters a bit within DEFENCE_RADIUS_SQ -- but none should
    # ever land on the threat's opposite (west) side, which is the bug
    # report this guards against.
    assert all(g.pos.x >= 20 for g in gunners), (
        f"Gunner(s) built on the wrong (non-threatened) side of the Core: {[g.pos for g in gunners]}"
    )


def test_core_ring_tiles_are_the_eight_orthogonal_neighbors():
    core_pos = Position(10, 10)
    tiles = set(defence._core_ring_tiles(core_pos))
    assert tiles == {
        Position(10, 9), Position(11, 9),
        Position(10, 12), Position(11, 12),
        Position(9, 10), Position(9, 11),
        Position(12, 10), Position(12, 11),
    }


def test_find_unsealed_ring_tile_skips_tiles_that_already_have_a_building():
    # Any existing building -- here, a Conveyor -- blocks the tile just as
    # well as a fresh Barrier would, so a ring tile that already has one
    # doesn't count as a gap.
    world = World(width=30, height=30)
    core_pos = Position(10, 10)
    world.spawn(core_pos, Team.A, EntityType.CORE)
    sealed = set(defence._core_ring_tiles(core_pos)) - {Position(12, 10)}
    for p in sealed:
        world.spawn(p, Team.A, EntityType.CONVEYOR, Direction.NORTH)
    builder_id = world.spawn(Position(15, 10), Team.A, EntityType.BUILDER_BOT)
    ct = world.controller_for(builder_id)

    assert defence._find_unsealed_ring_tile(ct, core_pos) == Position(12, 10)


def test_find_unsealed_ring_tile_none_when_fully_sealed():
    world = World(width=30, height=30)
    core_pos = Position(10, 10)
    world.spawn(core_pos, Team.A, EntityType.CORE)
    for p in defence._core_ring_tiles(core_pos):
        world.spawn(p, Team.A, EntityType.CONVEYOR, Direction.NORTH)
    builder_id = world.spawn(Position(15, 10), Team.A, EntityType.BUILDER_BOT)
    ct = world.controller_for(builder_id)

    assert defence._find_unsealed_ring_tile(ct, core_pos) is None


def test_defender_seals_the_last_open_ring_gap():
    world = World(width=30, height=30)
    core_pos = Position(10, 10)
    world.spawn(core_pos, Team.A, EntityType.CORE)
    sealed = set(defence._core_ring_tiles(core_pos)) - {Position(12, 10)}
    for p in sealed:
        world.spawn(p, Team.A, EntityType.CONVEYOR, Direction.NORTH)
    # Pre-fill the turret garrison (close enough to the Core to count from
    # wherever the defender ends up patrolling) so this run isolates
    # ring-sealing from the separate turret-building priority.
    for p in (Position(10, 7), Position(7, 9), Position(13, 9)):
        world.spawn(p, Team.A, EntityType.GUNNER, Direction.NORTH)

    builder_id = world.spawn(Position(14, 10), Team.A, EntityType.BUILDER_BOT)
    state = BuilderState()
    state.core_pos = core_pos

    for _ in range(40):
        ct = world.controller_for(builder_id)
        defence.run(ct, state)
        world.advance_round()
        if world.building_at(Position(12, 10)) is not None:
            break

    sealed_gap = world.building_at(Position(12, 10))
    assert sealed_gap is not None and sealed_gap.etype == EntityType.BARRIER
