"""Rebuild .map26 files from downloaded .replay26 replays.

The live map pool changed on 2026-08-06 (15 new maps, 3 shared) and the new
maps were never in `maps/`, so every local benchmark ran on ~17 maps the
ladder does not play — which is a fair candidate for why local edges kept
failing to transfer live. A replay's opening snapshot carries the whole
board: field 1 width, field 2 height, field 3 one row-message per map row
(field 1 = tile bytes, 0 empty / 1 wall / 2 ore), field 4 the two Cores —
the same fields, in the same encoding, as the .map26 format written by
tools/generate_maps.py. Extraction is re-serialization.

    uv run python tools/extract_maps.py <name>=<replay> [...] --out maps/live

Only replays of published-ladder matches we played or downloaded are used;
the held-out evaluation set stays untouched.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from benchmarks.replay import fields, message_dict  # noqa: E402
from tools.generate_maps import encode  # noqa: E402


def extract(replay_path: Path) -> bytes:
    top = fields(replay_path.read_bytes())
    snapshot = message_dict(next(v for n, _, v in top if n == 1))
    width = snapshot[1][0]
    height = snapshot[2][0]
    grid = []
    for raw in snapshot[3]:
        row = message_dict(raw)
        grid.append(list(row[1][0]))
    if len(grid) != height or any(len(r) != width for r in grid):
        raise ValueError(f"{replay_path}: grid {len(grid)} rows does not match "
                         f"{width}x{height}")
    cores = []
    for raw in snapshot[4]:
        core = message_dict(raw)
        team = core.get(2, [0])[0]
        pos_msg = message_dict(core[3][0])
        pos = (pos_msg.get(1, [0])[0], pos_msg.get(2, [0])[0])
        cores.append((team, pos))
    return encode(width, height, grid, cores)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pairs", nargs="+", help="name=path/to/replay26")
    parser.add_argument("--out", default="maps/live")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for pair in args.pairs:
        name, _, path = pair.partition("=")
        target = out / f"{name}.map26"
        if target.exists():
            print(f"{target.name}: exists, skipped")
            continue
        data = extract(Path(path))
        target.write_bytes(data)
        print(f"{target.name}: {len(data)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
