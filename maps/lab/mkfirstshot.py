"""Build `maps/lab/firstshot.map26` -- the turret first-strike arena.

16x9, completely open (no walls, no ore). Horizontal (mirror-x) symmetry, so
x -> 15 - x.

    Core A anchor (1,4)  -> footprint (1,4)(2,4)(1,5)(2,5)
    Core B anchor (13,4) -> footprint (13,4)(14,4)(13,5)(14,5)

Duel geometry on row y=4:

    x:  0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15
    y=4 . A A s . b T . . T  b  .  s  B  B  .

    A = Core A       B = Core B
    s = spawn tile   b = builder standing tile   T = turret tile

  Team A turret at (6,4) facing EAST  -- Sentinel line (7..11,4), Gunner line (7..9,4)
  Team B turret at (9,4) facing WEST  -- Sentinel line (8..4,4),  Gunner line (8..6,4)

  mirror(6) = 9, so the two turret tiles are exact mirror images: the arena is
  fair and neither side has a geometric edge. Each turret is in the other's
  attack set for BOTH turret types (d = 3, d^2 = 9 <= 13 <= 32).

  After building, each builder steps to y=3 ((5,3) / (10,3)) so it sits OFF the
  y=4 firing line and survives to report. From (5,3): d^2 to (6,4) = 2 and to
  (9,4) = 17, both <= 20 (BUILDER_BOT_VISION_RADIUS_SQ), so the observer sees
  both turrets for the whole duel.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "generated"))

from generate_maps import Core, GameMap, Symmetry, write_map, EMPTY  # noqa: E402

W, H = 16, 9
rows = [[EMPTY for _ in range(W)] for _ in range(H)]

gm = GameMap(
    width=W,
    height=H,
    rows=rows,
    cores=[Core(entity_id=1, team=0, x=1, y=4), Core(entity_id=2, team=1, x=13, y=4)],
    symmetry=Symmetry.HORIZONTAL,
)
out = pathlib.Path(__file__).resolve().parent / "firstshot.map26"
write_map(out, gm)
print("wrote", out)
