"""Rebuild the launcher-lab arenas in maps/lab/.

The first exploit hunt's arenas were lost. This regenerates every map the
launcher probes (bots/probes/gl_*, gg_*) need, using the official codec in
maps/generated/generate_maps.py.

    .venv/Scripts/python.exe maps/lab/mkmaps.py

Arenas
  glopen  26x14 open ground, cores (1,6)/(23,6), one ore pair at (10,2)/(15,11).
          The default pen arena: nothing on the map can block or protect anyone.
  glbox   glopen + a SEALED one-tile terrain pocket at (12,2) (walled on all
          four sides) and its rot180 twin at (13,11). Throw-into-pocket tests.
  glchain 30x12 open ground, cores (1,5)/(27,5). Long straight run for
          multi-launcher chain throws and ferry throughput.
  glchoke 26x14 with a full-height double wall band at x=12,13 and a single
          one-tile gap at y=6. mirror-x. The only route between the cores is
          (13,6)->(12,6); routing around a pen sited there is impossible.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "maps" / "generated"))

from generate_maps import (  # noqa: E402
    EMPTY,
    ORE,
    WALL,
    Core,
    GameMap,
    Symmetry,
    transform_core_anchor,
    validate,
    write_map,
)

OUT = ROOT / "maps" / "lab"


def blank(w, h, anchor_a, symmetry):
    rows = [[EMPTY] * w for _ in range(h)]
    ax, ay = anchor_a
    bx, by = transform_core_anchor(anchor_a, w, h, symmetry)
    cores = [Core(1, 0, ax, ay), Core(2, 1, bx, by)]
    return GameMap(width=w, height=h, rows=rows, cores=cores, symmetry=symmetry)


def put(m, x, y, v):
    m.rows[y][x] = v


def emit(name, m):
    errs = validate(m)
    path = OUT / (name + ".map26")
    write_map(path, m)
    ax, ay = m.cores[0].anchor
    bx, by = m.cores[1].anchor
    print("%-8s %2dx%-2d coreA=(%d,%d) coreB=(%d,%d) %s"
          % (name, m.width, m.height, ax, ay, bx, by,
             "OK" if not errs else "ERRORS " + str(errs)))


def glopen():
    m = blank(26, 14, (1, 6), Symmetry.ROTATIONAL)
    put(m, 10, 2, ORE)
    put(m, 15, 11, ORE)
    return m


def glbox():
    m = glopen()
    # sealed one-tile pocket at (12,2); rot180 twin pocket at (13,11)
    for x, y in ((12, 1), (11, 2), (13, 2), (12, 3)):
        put(m, x, y, WALL)
        put(m, m.width - 1 - x, m.height - 1 - y, WALL)
    return m


def glchain():
    m = blank(30, 12, (1, 5), Symmetry.ROTATIONAL)
    put(m, 14, 1, ORE)
    put(m, 15, 10, ORE)
    return m


def glchoke():
    m = blank(26, 14, (1, 6), Symmetry.HORIZONTAL)
    for y in range(14):
        if y == 6:
            continue
        put(m, 12, y, WALL)
        put(m, 13, y, WALL)
    put(m, 5, 1, ORE)
    put(m, 20, 1, ORE)
    return m


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    emit("glopen", glopen())
    emit("glbox", glbox())
    emit("glchain", glchain())
    emit("glchoke", glchoke())


if __name__ == "__main__":
    main()
