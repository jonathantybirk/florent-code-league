"""The two Core positions of a .map26, in team order (A first, B second)."""
from __future__ import annotations

import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def cores(path: pathlib.Path) -> list[tuple[int, int]]:
    data = path.read_bytes()
    # Position submessage: field 3, length 4, {x, y} -- coordinates are all < 128,
    # so every varint here is a single byte.
    return [(x[0], y[0]) for x, y in re.findall(rb"\x1a\x04\x08(.)\x10(.)", data, re.S)]


def size(path: pathlib.Path) -> tuple[int, int]:
    data = path.read_bytes()
    return data[1], data[3]     # field 1 (width), field 2 (height), both single-byte varints


if __name__ == "__main__":
    for name in sys.argv[1:]:
        p = ROOT / "maps" / f"{name}.map26"
        print(name, size(p), cores(p))
