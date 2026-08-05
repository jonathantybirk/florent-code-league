"""Sanity tests for tests/ascii_view.py -- pins down the glyph mapping
and capture/write behavior so it stays trustworthy as a debugging tool.
"""

from __future__ import annotations

from fcode import Direction, EntityType, Position, Team

from ascii_view import AsciiReplay, render_ascii
from fake_controller import World


def test_render_ascii_shows_expected_glyphs():
    world = World(width=5, height=2, walls=frozenset({Position(4, 0)}), ore=frozenset({Position(0, 1)}))
    world.spawn(Position(0, 0), Team.A, EntityType.BUILDER_BOT)
    world.spawn(Position(1, 0), Team.A, EntityType.CONVEYOR, Direction.EAST)
    world.spawn(Position(2, 0), Team.B, EntityType.HARVESTER)
    world.spawn(Position(3, 0), Team.B, EntityType.GUNNER, Direction.NORTH)

    rows = render_ascii(world).splitlines()
    assert rows[0] == "u>HG#"
    assert rows[1] == "o...."


def test_builder_on_conveyor_renders_the_builder_on_top():
    world = World(width=1, height=1)
    world.spawn(Position(0, 0), Team.A, EntityType.CONVEYOR, Direction.EAST)
    world.spawn(Position(0, 0), Team.B, EntityType.BUILDER_BOT)

    assert render_ascii(world) == "U"


def test_viewport_restricts_to_the_given_rectangle():
    world = World(width=5, height=5)
    world.spawn(Position(2, 2), Team.A, EntityType.CORE)  # 2x2 footprint: (2,2)-(3,3)

    text = render_ascii(world, top_left=Position(1, 1), bottom_right=Position(3, 3))
    assert text.splitlines() == ["...", ".cc", ".cc"]


def test_ascii_replay_captures_and_writes_frames(tmp_path):
    world = World(width=2, height=1)
    unit_id = world.spawn(Position(0, 0), Team.A, EntityType.BUILDER_BOT)

    replay = AsciiReplay()
    replay.capture(world, label="start")
    world.entities[unit_id].pos = Position(1, 0)
    world.advance_round()
    replay.capture(world, label="after move")

    text = replay.text()
    assert "round 0 (start)" in text
    assert "round 1 (after move)" in text
    assert "u." in text and ".u" in text

    out = tmp_path / "replay.txt"
    replay.write(str(out))
    assert out.read_text(encoding="utf-8") == text
