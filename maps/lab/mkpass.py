"""Build `maps/lab/passlab.map26` -- the arena for the definitive 2.3.6 passability table.

    .venv/Scripts/python.exe maps/lab/mkpass.py

22x12, 180-degree rotational symmetry. Core A anchor (1,5) (footprint (1..2, 5..6)),
Core B anchor (19,5) (footprint (19..20, 5..6)).

Everything the sweep needs, laid out so one builder can walk a straight line:

  (3,5)   own-Core stance.  WEST -> (2,5) is Core A footprint;
                            NORTH -> (3,4) is where the parked friendly builder sits.
  (6,9)   terrain stance.   NORTH -> (6,8) ORE, WEST -> (5,9) WALL, EAST -> (7,9) EMPTY.
  row 10  building lane.    Fully EMPTY x=0..21. The builder walks east along it and
                            builds each prop on row 9 to its NORTH, so a prop that
                            cannot be destroyed never blocks the lane.
  (9,9)   ORE, reachable from lane stance (9,10) -- the own-Harvester site.
  (11,7)  ORE, with EMPTY (10,7) and (12,7) either side -- the enemy-Harvester site
                            (team A stands west, team B stands east).
  (18,5)  enemy-Core stance. EAST -> (19,5) is Core B footprint.

Rotational images of the placed terrain land at (16,2) WALL and (15,3)/(12,2)/(10,4) ORE,
all clear of both Core margins and of every stance and lane above.
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "generated"))

from generate_maps import EMPTY, ORE, WALL, Core, GameMap, Symmetry, write_map  # noqa: E402

W, H = 22, 12
AX, AY = 1, 5
BX, BY = W - 2 - AX, H - 2 - AY          # (19, 5)

WALLS = [(5, 9)]
ORES = [(6, 8), (9, 9), (11, 7)]


def main():
    rows = [[EMPTY] * W for _ in range(H)]
    for x, y in WALLS:
        rows[y][x] = WALL
    for x, y in ORES:
        rows[y][x] = ORE
    # Force 180-degree rotational symmetry.
    for y in range(H):
        for x in range(W):
            if rows[y][x] != EMPTY:
                rows[H - 1 - y][W - 1 - x] = rows[y][x]
    # One-tile EMPTY margin around both Cores.
    for ax, ay in ((AX, AY), (BX, BY)):
        for py in range(ay - 1, ay + 3):
            for px in range(ax - 1, ax + 3):
                if 0 <= px < W and 0 <= py < H:
                    rows[py][px] = EMPTY

    gm = GameMap(
        width=W,
        height=H,
        rows=rows,
        cores=[Core(entity_id=0, team=0, x=AX, y=AY), Core(entity_id=1, team=1, x=BX, y=BY)],
        symmetry=Symmetry.ROTATIONAL,
    )
    out = HERE / "passlab.map26"
    write_map(out, gm)
    ch = {EMPTY: ".", WALL: "#", ORE: "o"}
    print("wrote %s  %dx%d  coreA=(%d,%d) coreB=(%d,%d)" % (out, W, H, AX, AY, BX, BY))
    print("    " + "".join(str(x % 10) for x in range(W)))
    for y in range(H):
        print("%3d " % y + "".join(ch[v] for v in rows[y]))


if __name__ == "__main__":
    main()
