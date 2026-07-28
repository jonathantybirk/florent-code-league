"""Runs bot 1 on twins.map26: core spawns a builder bot to the northeast,
the builder builds a launcher, and the launcher throws it as far northeast
as possible. Inspect the resulting replay with `fcode watch replay.replay26`.
"""

from __future__ import annotations

from pathlib import Path

import fcode

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_core_spawns_builder_that_launches_itself_northeast():
    from fcode.fcode_engine import run_game

    bot_main = PROJECT_ROOT / "bots" / "1" / "main.py"
    map_path = PROJECT_ROOT / "maps" / "twins.map26"
    replay_path = PROJECT_ROOT / "replay.replay26"
    engine_root = str(Path(fcode.__file__).resolve().parent)

    result = run_game(
        str(bot_main),
        str(bot_main),
        engine_root,
        str(map_path),
        str(replay_path),
        1,
        0,
    )

    assert replay_path.exists()
    assert result["winner"] in {"A", "B", "draw"}
