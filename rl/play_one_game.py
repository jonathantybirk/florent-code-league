"""Runs exactly one match through the engine and prints the result as JSON on stdout.

Kept as a standalone subprocess (invoked by rl/self_play.py) rather than called
in-process: the compiled fcode engine drives bot code through Rust sub-interpreters,
and having touched that machinery once in a process appears to leave torch's autograd
engine unable to run a backward pass afterwards in the same process ("autograd engine
was called while holding the GIL"). Isolating each match in its own process sidesteps
that entirely, at the cost of one process spawn per game.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import fcode
from fcode.fcode_engine import run_game

ENGINE_ROOT = str(Path(fcode.__file__).resolve().parent)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bot_a")
    parser.add_argument("bot_b")
    parser.add_argument("map_path")
    parser.add_argument("replay_path")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--tle", type=int, default=0)
    args = parser.parse_args()

    result = run_game(args.bot_a, args.bot_b, ENGINE_ROOT, args.map_path, args.replay_path, args.seed, args.tle)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
