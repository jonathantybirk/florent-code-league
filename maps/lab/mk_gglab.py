"""Regenerate the turret-lab arenas: maps/lab/ggopen, ggwall, ggore.

All three are 28x16, rotationally symmetric, Core A anchored at (1,7) and Core B at (25,7).
They share one design constraint: the row y=7 is a clear 22-tile lane between the two Cores, and
the station (10,7) has at least 5 empty tiles in every one of the eight compass directions, so no
turret attack pattern is ever truncated by a map edge.

  ggopen   nothing but the two mandatory ore tiles, tucked in the corners at (5,1) and (5,14).
  ggwall   ggopen + a single WALL at (12,7) (and its rot180 image at (15,8)) -- two tiles east of
           the standard gunner station, so a cardinal ray runs straight into it.
  ggore    ggopen + an ORE tile at (12,7) (image (15,8)) so a Harvester can be planted inside a
           gunner's firing line.

Run:  .venv/Scripts/python.exe maps/lab/mk_gglab.py
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "maps" / "generated"))

from generate_maps import (  # noqa: E402
    EMPTY, ORE, WALL, Core, GameMap, Symmetry, encode, read_map, validate, write_map,
)

W, H = 28, 16
ANCHOR_A = (1, 7)
ANCHOR_B = (25, 7)
ORES = [(5, 1), (5, 14)]


def rot(p):
    return (W - 1 - p[0], H - 1 - p[1])


def make(name, walls=(), ores=()):
    rows = [[EMPTY for _ in range(W)] for _ in range(H)]
    for p in walls:
        for q in (p, rot(p)):
            rows[q[1]][q[0]] = WALL
    for p in ores:
        for q in (p, rot(p)):
            rows[q[1]][q[0]] = ORE
    gm = GameMap(width=W, height=H, rows=rows, symmetry=Symmetry.ROTATIONAL,
                 cores=[Core(entity_id=1, team=0, x=ANCHOR_A[0], y=ANCHOR_A[1]),
                        Core(entity_id=2, team=1, x=ANCHOR_B[0], y=ANCHOR_B[1])])
    errs = validate(gm)
    out = ROOT / "maps" / "lab" / (name + ".map26")
    out.parent.mkdir(parents=True, exist_ok=True)
    write_map(out, gm)
    ok = encode(read_map(out)) == encode(gm)
    print("%-8s errors=%s roundtrip=%s -> %s" % (name, errs, ok, out))


make("ggopen", ores=ORES)
make("ggwall", walls=[(12, 7)], ores=ORES)
make("ggore", ores=ORES + [(12, 7)])
