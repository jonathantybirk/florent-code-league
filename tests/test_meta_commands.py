"""Regression tests for bots/test/meta_commands: Trigger priority
resolution (evaluate_meta_command), the buffered Core-only broadcast
(broadcast_meta_command), and the read side's fallback for an
out-of-vocabulary raw value (read_meta_command).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fcode import EntityType, Position, Team

from botimport import bot_on_path
from fake_controller import World

META_DIR = Path(__file__).resolve().parent.parent / "bots" / "test" / "meta_commands"


def _import_meta_commands():
    with bot_on_path(META_DIR):
        return importlib.import_module("main")


meta = _import_meta_commands()

MetaCommand = meta.MetaCommand
Trigger = meta.Trigger


def _world_with_core() -> tuple[World, int]:
    world = World(width=30, height=30)
    core_id = world.spawn(Position(10, 10), Team.A, EntityType.CORE)
    return world, core_id


# --- evaluate_meta_command: priority resolution, no store side effects ------


def test_no_trigger_matches_returns_default():
    world, core_id = _world_with_core()
    ct = world.controller_for(core_id)
    result = meta.evaluate_meta_command(ct, [Trigger(MetaCommand.ATTACK, 1, lambda ct: False)])
    assert result == MetaCommand.HOLD


def test_custom_default_is_honoured():
    world, core_id = _world_with_core()
    ct = world.controller_for(core_id)
    result = meta.evaluate_meta_command(
        ct, [], default=MetaCommand.RETREAT
    )
    assert result == MetaCommand.RETREAT


def test_higher_priority_trigger_wins_regardless_of_list_order():
    world, core_id = _world_with_core()
    ct = world.controller_for(core_id)
    triggers = [
        # Listed first, but lower priority -- must still lose.
        Trigger(MetaCommand.HOLD, priority=1, condition=lambda ct: True),
        Trigger(MetaCommand.DEFEND, priority=5, condition=lambda ct: True),
    ]
    assert meta.evaluate_meta_command(ct, triggers) == MetaCommand.DEFEND


def test_non_matching_trigger_is_skipped_even_at_higher_priority():
    world, core_id = _world_with_core()
    ct = world.controller_for(core_id)
    triggers = [
        Trigger(MetaCommand.ATTACK, priority=10, condition=lambda ct: False),
        Trigger(MetaCommand.RALLY, priority=1, condition=lambda ct: True),
    ]
    assert meta.evaluate_meta_command(ct, triggers) == MetaCommand.RALLY


def test_evaluate_meta_command_does_not_write_the_store():
    world, core_id = _world_with_core()
    ct = world.controller_for(core_id)
    meta.evaluate_meta_command(ct, [Trigger(MetaCommand.ATTACK, 1, lambda ct: True)])
    assert ct.read_store(meta.SLOT_META_COMMAND) == 0


# --- broadcast_meta_command: Core-only guard + buffered write ---------------


def test_broadcast_from_non_core_raises():
    world, core_id = _world_with_core()
    builder_id = world.spawn(Position(11, 12), Team.A, EntityType.BUILDER_BOT)
    ct = world.controller_for(builder_id)
    with pytest.raises(ValueError):
        meta.broadcast_meta_command(ct, [])


def test_broadcast_returns_the_winning_command():
    world, core_id = _world_with_core()
    ct = world.controller_for(core_id)
    triggers = [Trigger(MetaCommand.EXPAND, priority=1, condition=lambda ct: True)]
    assert meta.broadcast_meta_command(ct, triggers) == MetaCommand.EXPAND


def test_broadcast_write_is_buffered_one_round():
    world, core_id = _world_with_core()
    core_ct = world.controller_for(core_id)
    builder_id = world.spawn(Position(11, 12), Team.A, EntityType.BUILDER_BOT)
    builder_ct = world.controller_for(builder_id)

    triggers = [Trigger(MetaCommand.DEFEND, priority=1, condition=lambda ct: True)]
    meta.broadcast_meta_command(core_ct, triggers)

    # Same round: still reads the pre-write value (0 == HOLD).
    assert meta.read_meta_command(builder_ct) == MetaCommand.HOLD

    world.advance_round()

    # Next round: the write has committed.
    assert meta.read_meta_command(builder_ct) == MetaCommand.DEFEND


def test_broadcast_uses_a_custom_slot():
    world, core_id = _world_with_core()
    ct = world.controller_for(core_id)
    triggers = [Trigger(MetaCommand.RALLY, priority=1, condition=lambda ct: True)]

    meta.broadcast_meta_command(ct, triggers, slot=3)
    world.advance_round()

    assert ct.read_store(3) == int(MetaCommand.RALLY)
    assert ct.read_store(meta.SLOT_META_COMMAND) == 0


# --- read_meta_command: fallback on an out-of-vocabulary raw value ----------


def test_read_meta_command_falls_back_on_unknown_raw_value():
    world, core_id = _world_with_core()
    ct = world.controller_for(core_id)
    ct.write_store(meta.SLOT_META_COMMAND, 99)
    world.advance_round()

    assert meta.read_meta_command(ct) == MetaCommand.HOLD
    assert meta.read_meta_command(ct, default=MetaCommand.RETREAT) == MetaCommand.RETREAT
