"""Rebuild the COST-SCALE / UNIT-CAP / SELF-DESTRUCT lab arenas.

Run from the repo root:

    .venv/Scripts/python.exe maps/lab/mkcs.py

These are deliberately separate files from `mklab.py`'s ring/kill-box arenas so the two probe
families cannot break each other.  Both arenas are ROT180 symmetric with zero walls and only two
ore tiles, parked in opposite corners well away from every build row.

Arenas
------
csopen   26x14  A(1,6)  B(23,6)  ore (24,1) / (1,12)
         Rows y=3..11 are completely free, so a Builder Bot can serpentine
         (walk y=4 build y=3, walk y=6 build y=5, walk y=8 build y=9, walk y=10 build y=11)
         and drop ~88 barriers without ever touching terrain.  Cores are 22 apart so the
         opponent never interferes with a scale measurement.

cstiny   12x10  A(1,4)  B(9,4)   ore (10,1) / (1,8)
         Same shape, small, for probes that want the two teams close.

cslab    26x14  A(1,6)  B(23,6)  ore (5,5) / (20,8) as well as (24,1) / (1,12)
         csopen plus an ore tile at (5,5), orthogonally adjacent to the standard reporting
         position (5,6), so a probe can build a HARVESTER without walking anywhere.  Kept
         separate from csopen because csopen's probes build barriers and gunners on (5,5).
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "generated"))

from generate_maps import (  # noqa: E402
    EMPTY,
    ORE,
    Core,
    GameMap,
    Symmetry,
    read_map,
    validate,
    write_map,
)


def build(name, w, h, ax, ay, ore):
    """Rot180 arena, no walls. `ore` tiles are given once; the partner is added automatically."""
    bx, by = w - 2 - ax, h - 2 - ay
    rows = [[EMPTY for _ in range(w)] for _ in range(h)]
    for ox, oy in ore:
        rows[oy][ox] = ORE
        rows[h - 1 - oy][w - 1 - ox] = ORE
    gm = GameMap(w, h, rows, [Core(1, 0, ax, ay), Core(2, 1, bx, by)], Symmetry.ROTATIONAL)
    errors = validate(gm, require_playable=False)
    if errors:
        raise SystemExit("%s: %s" % (name, errors))
    path = HERE / ("%s.map26" % name)
    write_map(path, gm)
    back = read_map(path)
    print("%-14s %dx%d A=(%d,%d) B=(%d,%d) bytes=%d roundtrip=%s" % (
        path.name, w, h, ax, ay, bx, by, path.stat().st_size,
        "ok" if back.rows == gm.rows and back.cores == gm.cores else "FAIL"))


def main():
    build("csopen", 26, 14, 1, 6, [(24, 1)])
    build("cstiny", 12, 10, 1, 4, [(10, 1)])
    build("cslab", 26, 14, 1, 6, [(24, 1), (5, 5)])


if __name__ == "__main__":
    main()
