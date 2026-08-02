"""Rebuild the arenas the API-surface sweep needs.  Run:

    .venv/Scripts/python.exe maps/lab/mkapi.py

apilab   24x14 rot180.  Core A anchor (1,6).  A builder homed at (6,6) has, orthogonally:
         N (6,5) ORE, S (6,7) ORE, W (5,6) WALL, E (7,6) EMPTY.  That single square exercises
         every terrain type plus a free build slot, which is what the passability table needs.
         Ore at (8,6) too, so a harvester can also be planted east of a second stance.
apilos   24x14 rot180.  Same Core, but a solid wall column at x=8 spanning y=2..10 with no gap
         near the Core.  A builder at (6,6) is 2 tiles from the wall, so tiles at x=9..10 sit
         behind it and well inside the builder's r^2=20 vision disc -- the line-of-sight test.
The turn-order race uses the existing maps/lab/close.map26 (14x11, Cores 7 apart on the same row).
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "generated"))

from generate_maps import EMPTY, ORE, WALL, Core, GameMap, Symmetry, write_map  # noqa: E402


def build(name, w, h, ore, walls, ax, ay):
    rows = [[EMPTY] * w for _ in range(h)]
    for x, y in walls:
        rows[y][x] = WALL
    for x, y in ore:
        rows[y][x] = ORE
    # Force 180-degree rotational symmetry by copying the whole grid onto its image.
    for y in range(h):
        for x in range(w):
            if rows[y][x] != EMPTY:
                rows[h - 1 - y][w - 1 - x] = rows[y][x]
    bx, by = w - 2 - ax, h - 2 - ay
    for anchor in ((ax, ay), (bx, by)):
        for py in range(anchor[1] - 1, anchor[1] + 3):
            for px in range(anchor[0] - 1, anchor[0] + 3):
                if 0 <= px < w and 0 <= py < h:
                    rows[py][px] = EMPTY
    gm = GameMap(width=w, height=h, rows=rows,
                 cores=[Core(entity_id=0, team=0, x=ax, y=ay),
                        Core(entity_id=1, team=1, x=bx, y=by)],
                 symmetry=Symmetry.ROTATIONAL)
    write_map(HERE / (name + ".map26"), gm)
    print("wrote %s %dx%d coreA=(%d,%d) coreB=(%d,%d)" % (name, w, h, ax, ay, bx, by))


def main():
    build("apilab", 24, 14, ore=[(6, 5), (6, 7), (8, 6)], walls=[(5, 6)], ax=1, ay=6)
    build("apilos", 24, 14, ore=[(6, 5)], walls=[(8, y) for y in range(2, 11)], ax=1, ay=6)


if __name__ == "__main__":
    main()
