"""Runs the role-based launcher/economy strategy on twins.map26."""

from __future__ import annotations

from pathlib import Path

import fcode

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_bot_1_vs_starter_on_twins():
    from fcode.fcode_engine import run_game

    bot_1 = PROJECT_ROOT / "bots" / "1" / "main.py"
    bot_starter = PROJECT_ROOT / "bots" / "starter" / "main.py"
    map_path = PROJECT_ROOT / "maps" / "twins.map26"
    replay_path = PROJECT_ROOT / "replay.replay26"
    engine_root = str(Path(fcode.__file__).resolve().parent)

    result = run_game(
        str(bot_1),
        str(bot_starter),
        engine_root,
        str(map_path),
        str(replay_path),
        1,
        10,
    )

    assert replay_path.exists()
    assert result["winner"] == "A"
    assert result["win_condition"] == "core_destroyed"
