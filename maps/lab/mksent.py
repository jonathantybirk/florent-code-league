"""Build `maps/lab/sentwall.map26` -- the decisive Sentinel-through-walls arena.

12x10. Core A anchor (1,4), Core B anchor (9,4). A two-tile-thick WALL band at
x=5,6 spanning y=0..7, with a gap at y=8,9 so a builder can walk around it and
place a barrier on the far side.

Geometry that makes it decisive:
  Sentinel on (4,4) facing EAST reaches 5 cardinal tiles -> (5..9,4), d^2=25<=32.
  (5,4) and (6,4) are WALL. (9,4) is a Core B footprint tile.
  A Gunner on (4,4) reaches only 3 tiles -> (7,4), so it cannot reach the Core
  even with a clear lane. That asymmetry is the point: any damage to Core B from
  (4,4) can only be a Sentinel shot that crossed two walls.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "generated"))

from generate_maps import Core, GameMap, Symmetry, write_map, EMPTY, WALL  # noqa: E402

W, H = 12, 10
rows = [[EMPTY for _ in range(W)] for _ in range(H)]
for y in range(0, 8):
    rows[y][5] = WALL
    rows[y][6] = WALL

gm = GameMap(
    width=W,
    height=H,
    rows=rows,
    cores=[Core(entity_id=1, team=0, x=1, y=4), Core(entity_id=2, team=1, x=9, y=4)],
    symmetry=Symmetry.HORIZONTAL,
)
out = pathlib.Path(__file__).resolve().parent / "sentwall.map26"
write_map(out, gm)
print("wrote", out)
for y in range(H):
    print("".join("#" if rows[y][x] == WALL else "." for x in range(W)))
