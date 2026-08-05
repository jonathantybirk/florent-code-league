"""Regression tests for bots/warden_'s OFFENCE mode -- see modes/offence.py's
module docstring: reactive assignment (policy.py) pushes a Builder toward
a known enemy Core, sabotaging adjacent enemy infrastructure along the
way and seating one forward Gunner once close enough, capped small since
this is harassment, not a siege.
"""

from __future__ import annotations

from fcode import Direction, EntityType, Position, Team

from fake_controller import World
from warden_support import import_warden

warden = import_warden()
offence = warden.offence
BuilderState = warden.state.BuilderState
Mode = warden.constants.Mode
SLOT_ENEMY_CORE = warden.constants.SLOT_ENEMY_CORE


def test_offence_falls_back_to_economy_when_enemy_core_unknown():
    world = World(width=20, height=20, ore=frozenset({Position(6, 5)}))
    world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)
    state = BuilderState()
    state.mode = Mode.OFFENCE
    state.core_pos = Position(10, 10)

    ct = world.controller_for(builder_id)
    offence.run(ct, state)

    assert state.route_harvester == Position(6, 5), "should have delegated to economy.run and built a Harvester"


def test_offence_moves_toward_the_enemy_core_when_far():
    world = World(width=30, height=30)
    world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)
    state = BuilderState()
    state.mode = Mode.OFFENCE
    state.core_pos = Position(10, 10)
    world.store[Team.A][SLOT_ENEMY_CORE] = warden.toolbox.pack_pos(Position(25, 5))

    ct = world.controller_for(builder_id)
    offence.run(ct, state)

    assert world.entities[builder_id].pos.x > 5


def test_offence_sabotages_an_adjacent_enemy_building_regardless_of_range():
    world = World(width=30, height=30)
    world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)
    world.spawn(Position(6, 5), Team.B, EntityType.HARVESTER)
    state = BuilderState()
    state.mode = Mode.OFFENCE
    state.core_pos = Position(10, 10)
    world.store[Team.A][SLOT_ENEMY_CORE] = warden.toolbox.pack_pos(Position(25, 5))  # far away

    ct = world.controller_for(builder_id)
    resources_before = world.resources[Team.A]
    offence.run(ct, state)

    assert world.resources[Team.A] == resources_before - 2, "expected a sabotage fire() to have spent titanium"


def test_offence_seats_a_forward_gunner_once_in_engage_range():
    world = World(width=30, height=30)
    world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(20, 10), Team.A, EntityType.BUILDER_BOT)
    state = BuilderState()
    state.mode = Mode.OFFENCE
    state.core_pos = Position(10, 10)
    world.store[Team.A][SLOT_ENEMY_CORE] = warden.toolbox.pack_pos(Position(22, 10))

    ct = world.controller_for(builder_id)
    offence.run(ct, state)

    gunners = [e for e in world.entities.values() if e.etype == EntityType.GUNNER and e.team == Team.A]
    assert gunners, "expected a forward Gunner to be built once within OFFENCE_ENGAGE_RADIUS_SQ"


def test_offence_does_not_exceed_the_forward_turret_cap():
    world = World(width=30, height=30)
    world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    world.spawn(Position(21, 10), Team.A, EntityType.GUNNER, Direction.EAST)  # already at the cap
    builder_id = world.spawn(Position(20, 10), Team.A, EntityType.BUILDER_BOT)
    state = BuilderState()
    state.mode = Mode.OFFENCE
    state.core_pos = Position(10, 10)
    world.store[Team.A][SLOT_ENEMY_CORE] = warden.toolbox.pack_pos(Position(22, 10))

    ct = world.controller_for(builder_id)
    offence.run(ct, state)

    gunners = [e for e in world.entities.values() if e.etype == EntityType.GUNNER and e.team == Team.A]
    assert len(gunners) == 1, "should not build a second forward Gunner past MAX_OFFENCE_TURRETS_NEAR_ENEMY"
