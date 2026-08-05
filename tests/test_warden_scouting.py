"""Regression test for bots/warden_'s SCOUTING mode also sharing ore it
passes -- see modes/scouting.py's module docstring: Economy builders
only ever search their own vision and fall back to SLOT_ORE_SHARE, so
ore outside where an Economy builder actually walks would otherwise
never be discovered at all. A Scout covers exactly that ground.
"""

from __future__ import annotations

from fcode import EntityType, Position, Team

from fake_controller import World
from warden_support import import_warden

warden = import_warden()
scouting = warden.scouting
BuilderState = warden.state.BuilderState
SLOT_ORE_SHARE = warden.constants.SLOT_ORE_SHARE


def test_scouting_shares_ore_it_passes():
    world = World(width=30, height=30, ore=frozenset({Position(5, 5)}))
    scout_id = world.spawn(Position(6, 6), Team.A, EntityType.BUILDER_BOT)
    state = BuilderState()
    state.core_pos = Position(2, 2)

    ct = world.controller_for(scout_id)
    scouting.run(ct, state)
    world.advance_round()

    assert warden.toolbox.unpack_pos(world.store[Team.A][SLOT_ORE_SHARE]) == Position(5, 5)


def test_scouting_reports_an_enemy_core_sighting_to_its_own_slot():
    world = World(width=30, height=30)
    scout_id = world.spawn(Position(10, 10), Team.A, EntityType.BUILDER_BOT)
    world.spawn(Position(11, 10), Team.B, EntityType.CORE)
    state = BuilderState()
    state.core_pos = Position(2, 2)

    ct = world.controller_for(scout_id)
    scouting.run(ct, state)
    world.advance_round()

    SLOT_ENEMY_CORE = warden.constants.SLOT_ENEMY_CORE
    SLOT_ENEMY_SIGHTING = warden.constants.SLOT_ENEMY_SIGHTING
    assert warden.toolbox.unpack_pos(world.store[Team.A][SLOT_ENEMY_CORE]) == Position(11, 10)
    assert world.store[Team.A][SLOT_ENEMY_SIGHTING] == 0, "the Core sighting shouldn't also spend the generic slot"


def test_scouting_prefers_reporting_the_enemy_core_over_another_enemy():
    world = World(width=30, height=30)
    scout_id = world.spawn(Position(10, 10), Team.A, EntityType.BUILDER_BOT)
    world.spawn(Position(9, 10), Team.B, EntityType.BUILDER_BOT)  # closer, but less valuable
    world.spawn(Position(11, 10), Team.B, EntityType.CORE)
    state = BuilderState()
    state.core_pos = Position(2, 2)

    ct = world.controller_for(scout_id)
    scouting.run(ct, state)
    world.advance_round()

    SLOT_ENEMY_CORE = warden.constants.SLOT_ENEMY_CORE
    assert warden.toolbox.unpack_pos(world.store[Team.A][SLOT_ENEMY_CORE]) == Position(11, 10)
