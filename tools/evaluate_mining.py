#!/usr/bin/env python
"""Report strategy timing and construction cadence from arbitrary replays."""

from __future__ import annotations

import argparse
from pathlib import Path

from gcs_viz import TYPE_MARKERS, _fields, _pos, _unwrap


def evaluate(path: Path, team: int) -> None:
    top = _fields(path.read_bytes())
    builders, builds, moves = [], [], {}
    for round_no, round_data in enumerate(v for f, _, v in top if f == 3):
        for _, _, event in _fields(round_data):
            fields = _unwrap(event)
            numbers = {field for field, _, _ in fields}
            if {1, 3, 4}.issubset(numbers):
                data = {field: value for field, _, value in fields}
                marker = next((field for field in numbers if field >= 10), None)
                kind = TYPE_MARKERS.get(marker)
                if data.get(2, 0) != team:
                    continue
                if kind == "builder_bot":
                    builders.append(round_no)
                    moves.setdefault(data[1], []).append((round_no, _pos(data[3])))
                elif kind in ("conveyor", "harvester"):
                    builds.append((round_no, kind, _pos(data[3])))
                continue
            if fields and fields[0][0] == 2:
                move = {field: value for field, _, value in _fields(fields[0][2])}
                if move.get(1) in moves:
                    moves[move[1]].append((round_no, _pos(move[2])))

    harvesters = [round_no for round_no, kind, _ in builds if kind == "harvester"]
    conveyors = [round_no for round_no, kind, _ in builds if kind == "conveyor"]
    reversals = sum(
        first[1] == third[1]
        for history in moves.values()
        for first, _, third in zip(history, history[1:], history[2:])
    )
    gaps = [right[0] - left[0] for left, right in zip(builds, builds[1:])]
    print(
        f"{path}: team={'AB'[team]} builders={builders} "
        f"first_conveyor={conveyors[0] if conveyors else None} "
        f"harvesters={harvesters} builds={len(builds)} reversals={reversals} "
        f"max_build_gap={max(gaps, default=0)}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path, nargs="+")
    parser.add_argument("--team", choices=("A", "B"), default="A")
    args = parser.parse_args()
    for replay in args.replay:
        evaluate(replay, ord(args.team) - ord("A"))
