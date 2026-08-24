"""Which pool starts a change turns, against a reference pattern from the same rival.

The mirror on the pool is exactly determined by (map, seat) -- every cell of a
five-seed run came back 5-0 or 0-5 -- so one seed is the whole measurement, and a
change is worth exactly the starts where it turns a loss into a win.

    uv run python tools/flips.py /tmp/base_pattern.csv /tmp/cand.csv
"""
from __future__ import annotations

import csv, sys


def read(path):
    with open(path) as fh:
        return {(r["map"], r["seat"]): r["result"] for r in csv.DictReader(fh)}


def main() -> int:
    base, cand = read(sys.argv[1]), read(sys.argv[2])
    won, lost = [], []
    for key in sorted(base):
        if key not in cand:
            continue
        if base[key] == "L" and cand[key] == "W":
            won.append(key)
        elif base[key] == "W" and cand[key] == "L":
            lost.append(key)
    print(f"gained {len(won)}: " + ", ".join(f"{m} {s}" for m, s in won))
    print(f"lost   {len(lost)}: " + ", ".join(f"{m} {s}" for m, s in lost))
    print(f"net {len(won) - len(lost):+d} starts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
