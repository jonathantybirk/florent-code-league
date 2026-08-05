"""Regression test for bots/warden_'s policy.maybe_reassign() idle-
Economy-to-Scouting trigger -- see its docstring: a Builder that can
find no ore at all (map run dry locally, or lost the race to nearby
teammates) previously sat in Economy mode calling explore_randomly
forever with nothing to show for it.
"""

from __future__ import annotations

from fcode import EntityType, Position, Team

from fake_controller import World
from warden_support import import_warden

warden = import_warden()
policy = warden.policy
economy = warden.economy
BuilderState = warden.state.BuilderState
Mode = warden.constants.Mode
ECON_IDLE_ROUNDS_BEFORE_SCOUT = warden.constants.ECON_IDLE_ROUNDS_BEFORE_SCOUT


def test_idle_economy_builder_reassigns_to_scouting():
    world = World(width=20, height=20)  # no ore anywhere -- genuinely nothing to find
    world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)

    state = BuilderState()
    state.ticket = 0  # ECONOMY by default (QUOTA_CYCLE[0])
    state.core_pos = Position(10, 10)

    for _ in range(4 * ECON_IDLE_ROUNDS_BEFORE_SCOUT):
        ct = world.controller_for(builder_id)
        policy.maybe_reassign(ct, state)
        if state.mode == Mode.ECONOMY:
            economy.run(ct, state)
        world.advance_round()
        if state.mode != Mode.ECONOMY:
            break

    assert state.mode == Mode.SCOUTING


def test_economy_builder_does_not_reassign_while_actively_routing():
    # Ore starts adjacent, so the Harvester goes down round 0 and the
    # route to the Core (~10 tiles away) takes far longer than
    # ECON_IDLE_ROUNDS_BEFORE_SCOUT rounds to finish -- reassigning mid
    # route would abandon real, in-progress work.
    world = World(width=20, height=20, ore=frozenset({Position(6, 5)}))
    world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)

    state = BuilderState()
    state.ticket = 0
    state.core_pos = Position(10, 10)

    for _ in range(ECON_IDLE_ROUNDS_BEFORE_SCOUT):
        ct = world.controller_for(builder_id)
        policy.maybe_reassign(ct, state)
        economy.run(ct, state)
        world.advance_round()

    assert state.mode == Mode.ECONOMY
    assert state.route_harvester is not None, "should still be mid-route, not finished or abandoned"
    assert state.econ_idle_rounds == 0


SLOT_ENEMY_CORE = warden.constants.SLOT_ENEMY_CORE
SLOT_OFFENCE_COUNT = warden.constants.SLOT_OFFENCE_COUNT
SLOT_THREAT_LEVEL = warden.constants.SLOT_THREAT_LEVEL
MAX_OFFENCE_UNITS = warden.constants.MAX_OFFENCE_UNITS


def test_economy_builder_between_tasks_joins_offence_when_enemy_core_known():
    world = World(width=20, height=20)
    world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)
    state = BuilderState()
    state.ticket = 0  # ECONOMY, and ore_target is None (between tasks) by default
    state.core_pos = Position(10, 10)
    world.store[Team.A][SLOT_ENEMY_CORE] = warden.toolbox.pack_pos(Position(18, 18))

    ct = world.controller_for(builder_id)
    policy.maybe_reassign(ct, state)

    assert state.mode == Mode.OFFENCE


def test_scouting_builder_joins_offence_when_enemy_core_known():
    world = World(width=20, height=20)
    world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)
    state = BuilderState()
    state.ticket = 4
    state.mode = Mode.SCOUTING
    state.core_pos = Position(10, 10)
    world.store[Team.A][SLOT_ENEMY_CORE] = warden.toolbox.pack_pos(Position(18, 18))

    ct = world.controller_for(builder_id)
    policy.maybe_reassign(ct, state)

    assert state.mode == Mode.OFFENCE


def test_offence_join_respects_the_unit_cap():
    world = World(width=20, height=20)
    world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)
    state = BuilderState()
    state.ticket = 0
    state.core_pos = Position(10, 10)
    world.store[Team.A][SLOT_ENEMY_CORE] = warden.toolbox.pack_pos(Position(18, 18))
    world.store[Team.A][SLOT_OFFENCE_COUNT] = MAX_OFFENCE_UNITS  # already full

    ct = world.controller_for(builder_id)
    policy.maybe_reassign(ct, state)

    assert state.mode == Mode.ECONOMY


def test_threat_promotion_outranks_joining_offence():
    # Defend home first: a Builder eligible for both this round should
    # go to DEFENCE, not OFFENCE.
    world = World(width=20, height=20)
    world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)
    state = BuilderState()
    state.ticket = 0
    state.core_pos = Position(10, 10)
    world.store[Team.A][SLOT_ENEMY_CORE] = warden.toolbox.pack_pos(Position(18, 18))
    world.store[Team.A][SLOT_THREAT_LEVEL] = 10

    ct = world.controller_for(builder_id)
    policy.maybe_reassign(ct, state)

    assert state.mode == Mode.DEFENCE


def test_offence_join_is_one_way():
    # Once in OFFENCE, later maybe_reassign calls (even with the enemy
    # Core slot cleared, or under threat) must never move it back out.
    world = World(width=20, height=20)
    world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    builder_id = world.spawn(Position(5, 5), Team.A, EntityType.BUILDER_BOT)
    state = BuilderState()
    state.ticket = 0
    state.core_pos = Position(10, 10)
    state.mode = Mode.OFFENCE

    ct = world.controller_for(builder_id)
    world.store[Team.A][SLOT_THREAT_LEVEL] = 10
    policy.maybe_reassign(ct, state)

    assert state.mode == Mode.OFFENCE
