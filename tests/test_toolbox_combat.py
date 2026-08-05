"""Regression tests for common/toolbox.py's auto_fire rotate-fallback.

A Gunner's facing is fixed at build time and never moves on its own; see
auto_fire's docstring. Without the rotate fallback, a Gunner can only
ever hit whatever happens to wander onto the one ray it was built
facing -- including never once shooting a stationary enemy turret built
off to the side, since neither side ever moves. try_rotate_toward_enemy
is what turns a Gunner onto a real target instead of leaving it staring
at empty ground forever.
"""

from __future__ import annotations

from fcode import Direction, EntityType, Position, Team

from fake_controller import World
from warden_support import import_warden

warden = import_warden()
toolbox = warden.toolbox


def test_auto_fire_rotates_toward_an_enemy_turret_off_its_current_ray():
    world = World(width=20, height=20)
    world.ammo[Team.A] = 100
    # Our Gunner faces EAST (nothing there); the enemy Gunner sits south
    # of it -- off the current ray, but within rotate range.
    gunner_id = world.spawn(Position(5, 5), Team.A, EntityType.GUNNER, Direction.EAST)
    world.spawn(Position(5, 8), Team.B, EntityType.GUNNER, Direction.NORTH)

    ct = world.controller_for(gunner_id)
    assert toolbox.auto_fire(ct) is False  # nothing on the current ray yet
    assert ct.get_direction() == Direction.SOUTH  # but it turned onto the enemy


def test_auto_fire_fires_immediately_when_an_enemy_turret_is_already_on_the_ray():
    world = World(width=20, height=20)
    world.ammo[Team.A] = 100
    gunner_id = world.spawn(Position(5, 5), Team.A, EntityType.GUNNER, Direction.EAST)
    world.spawn(Position(8, 5), Team.B, EntityType.GUNNER, Direction.WEST)

    ct = world.controller_for(gunner_id)
    assert toolbox.auto_fire(ct) is True
    assert world.ammo[Team.A] == 96  # 100 - GUNNER_AMMO_COST
    assert ct.get_direction() == Direction.EAST  # no rotation needed


def test_auto_fire_never_fires_on_a_teammate_blocking_the_ray():
    # get_gunner_target() stops at the first targetable tile regardless of
    # team -- a teammate walking across the ray is the ordinary case, and
    # firing on it would be real friendly fire (wasted ammo, self-damage).
    world = World(width=20, height=20)
    world.ammo[Team.A] = 100
    gunner_id = world.spawn(Position(5, 5), Team.A, EntityType.GUNNER, Direction.EAST)
    world.spawn(Position(7, 5), Team.A, EntityType.BUILDER_BOT)

    ct = world.controller_for(gunner_id)
    assert toolbox.auto_fire(ct) is False
    assert world.ammo[Team.A] == 100
    assert ct.get_direction() == Direction.EAST


def test_auto_fire_rotates_past_a_blocking_teammate_toward_a_real_enemy():
    world = World(width=20, height=20)
    world.ammo[Team.A] = 100
    gunner_id = world.spawn(Position(5, 5), Team.A, EntityType.GUNNER, Direction.EAST)
    world.spawn(Position(7, 5), Team.A, EntityType.BUILDER_BOT)  # blocks the current ray
    world.spawn(Position(5, 8), Team.B, EntityType.GUNNER, Direction.NORTH)  # real target

    ct = world.controller_for(gunner_id)
    assert toolbox.auto_fire(ct) is False  # nothing to fire at yet (teammate doesn't count)
    assert world.ammo[Team.A] == 100
    assert ct.get_direction() == Direction.SOUTH  # turned onto the enemy instead


def test_auto_fire_does_nothing_with_no_enemy_in_range():
    world = World(width=20, height=20)
    world.ammo[Team.A] = 100
    gunner_id = world.spawn(Position(5, 5), Team.A, EntityType.GUNNER, Direction.EAST)

    ct = world.controller_for(gunner_id)
    assert toolbox.auto_fire(ct) is False
    assert ct.get_direction() == Direction.EAST
    assert world.ammo[Team.A] == 100
