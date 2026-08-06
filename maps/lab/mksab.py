"""Build `maps/lab/sab.map26` -- the sabotage-economics arena.

22x10, HORIZONTAL symmetry (mirror x -> 21-x), no walls.

  Core A anchor (2,4) -> foot (2,4)(3,4)(2,5)(3,5)
  Core B anchor (18,4) -> foot (18,4)(19,4)(18,5)(19,5)
  home ore     (6,4) <-> (15,4)          -- one ore per side, so denying it denies 100%
  midfield ore (10,8) <-> (11,8)         -- exactly equidistant from both Cores

The geometry that makes the sabotage exchange measurable:

  Team B's only chain is  harvester(15,4) -> conveyor(16,4)E -> conveyor(17,4)E -> Core foot(18,4).
  (17,4) is the TERMINAL conveyor: cutting it zeroes the whole upstream chain.

  Team A hits (17,4) from the SOUTH along the empty column x=17:
    GUNNER at (17,7) facing NORTH -> ray (17,6)(17,5)(17,4), d^2=9 <= 13.
    SENTINEL at (17,9) facing NORTH -> reach 5 -> (17,8)..(17,4), d^2=25 <= 32, and
    unblocked, so it still hits (17,4) with A's OWN builder parked on (17,5) -- which is
    what the cut-then-occupy variant needs, since (17,5) is the only tile adjacent to
    (17,4) that team A can stand on.

  Team B's builder parks on (17,3), BEHIND the target relative to the ray, so it can rebuild
  (17,4) every round without ever eclipsing it.
"""

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "maps" / "generated"))

from generate_maps import (Core, GameMap, Symmetry, write_map, read_map,  # noqa: E402
                           encode, validate, EMPTY, ORE)

W, H = 22, 10
rows = [[EMPTY] * W for _ in range(H)]
for (x, y) in [(6, 4), (15, 4), (10, 8), (11, 8)]:
    rows[y][x] = ORE

gm = GameMap(
    width=W,
    height=H,
    rows=rows,
    cores=[Core(entity_id=1, team=0, x=2, y=4), Core(entity_id=2, team=1, x=18, y=4)],
    symmetry=Symmetry.HORIZONTAL,
)

errs = validate(gm, require_playable=True)
print("validate:", errs)
out = ROOT / "maps" / "lab" / "sab.map26"
write_map(out, gm)
assert encode(read_map(out)) == encode(gm)
print("wrote", out)
for y in range(H):
    print("".join("O" if rows[y][x] == ORE else "." for x in range(W)))
