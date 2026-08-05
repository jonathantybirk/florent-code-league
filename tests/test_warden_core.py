"""Regression test for bots/warden_'s Core spawn pacing -- see core.py's
module docstring: affordability alone let the Core burst out several
Builders in the first few rounds, all racing for whatever ore tiles
happen to be nearest the spawn, leaving most of that burst idle.
"""

from __future__ import annotations

from fcode import EntityType, Position, Team

from fake_controller import World
from warden_support import import_warden

warden = import_warden()
core = warden.core
BuilderState = warden.state.BuilderState
BUILDER_SPAWN_COOLDOWN_ROUNDS = warden.constants.BUILDER_SPAWN_COOLDOWN_ROUNDS


def test_core_paces_spawns_by_cooldown_not_just_affordability():
    world = World(width=20, height=20)
    core_id = world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    state = BuilderState()

    spawned_rounds = []
    for _ in range(24):
        ct = world.controller_for(core_id)
        before = set(world.entities)
        core.run(ct, state)
        spawned = set(world.entities) - before
        if any(world.entities[i].etype == EntityType.BUILDER_BOT for i in spawned):
            spawned_rounds.append(world.round)
        world.advance_round()

    assert len(spawned_rounds) >= 2, "expected at least two spawns within the round budget"
    gaps = [b - a for a, b in zip(spawned_rounds, spawned_rounds[1:])]
    assert all(gap >= BUILDER_SPAWN_COOLDOWN_ROUNDS for gap in gaps), (
        f"spawns weren't paced by the cooldown: rounds={spawned_rounds}"
    )
