"""Rebuild the spawn-denial / kill-box lab arenas.

Run from the repo root:

    .venv/Scripts/python.exe maps/lab/mklab.py

Every arena here is MIRROR-X symmetric with both Core anchors on the horizontal centre line
(y == (height - 2) // 2).  That is deliberate: with y on the centre line the ROT180 transform and
the MIRROR-X transform give the *same* anchor, and the MIRROR-Y transform gives our *own* anchor.
So a probe can infer the enemy Core anchor with

    cands = {rot180(a), mirrorx(a), mirrory(a)} - {a}      # exactly one element on these arenas

with no map table and no ambiguity.  `ringedge` breaks the *bounds* assumption (Core flush against
the map border, so the 12-tile ring is clipped) while keeping the centre-line property.

Arenas
------
ringtight  12x10  A(2,4)  B(8,4)   3 tiles between the two rings - fastest seal
ringopen   16x12  A(2,5)  B(12,5)  7 tiles between the two rings - normal seal
ringfar    26x14  A(2,6)  B(22,6)  17 tiles between the two rings - walk-cost measurement
ringedge   12x10  A(0,4)  B(10,4)  Cores flush against the left/right border; ring is 8 tiles
kboxopen   16x12  A(2,5)  B(12,5)  same as ringopen (kept separate so kill-box probes are stable)
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
    spawn_ring,
    validate,
    write_map,
)

MIRROR_X = Symmetry.HORIZONTAL


def build(name, w, h, ax, ay, ore):
    """Mirror-x arena, no walls, `ore` given as the left-hand tiles (mirrored automatically)."""
    bx, by = w - 2 - ax, ay
    rows = [[EMPTY for _ in range(w)] for _ in range(h)]
    for ox, oy in ore:
        rows[oy][ox] = ORE
        rows[oy][w - 1 - ox] = ORE
    gm = GameMap(w, h, rows, [Core(1, 0, ax, ay), Core(2, 1, bx, by)], MIRROR_X)
    errors = validate(gm, require_playable=False)
    if errors:
        raise SystemExit(f"{name}: {errors}")
    path = HERE / f"{name}.map26"
    write_map(path, gm)
    back = read_map(path)
    ra = spawn_ring((ax, ay), w, h)
    rb = spawn_ring((bx, by), w, h)
    print(
        f"{path.name:<16} {w}x{h} A=({ax},{ay}) B=({bx},{by}) "
        f"ringA={len(ra)} ringB={len(rb)} bytes={path.stat().st_size} "
        f"roundtrip={'ok' if back.rows == gm.rows else 'FAIL'}"
    )


def main():
    build("ringtight", 12, 10, 2, 4, [(5, 0)])
    build("ringopen", 16, 12, 2, 5, [(7, 1)])
    build("ringfar", 26, 14, 2, 6, [(12, 1)])
    build("ringedge", 12, 10, 0, 4, [(5, 0)])
    build("kboxopen", 16, 12, 2, 5, [(7, 1)])


if __name__ == "__main__":
    main()
