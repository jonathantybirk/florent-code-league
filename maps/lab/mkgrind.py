"""Build the `maps/lab/hg<W>x<H>.map26` family -- the healer-vs-grinder arenas.

TASK 1.1 needs one game per (N healers, M grinders, turret type) cell, and a probe
has no way to receive arguments. So the configuration is encoded in the MAP
DIMENSIONS, which `ct.get_map_width()` / `ct.get_map_height()` hand back for free:

    height H = 10 + 4*N + M      ->  N = (H - 10) // 4,  M = (H - 10) % 4
    width  W = 24  Sentinel, no ammo   (pure attrition: turret cannot shoot back)
             25  Gunner,   no ammo
             26  Sentinel, Core converts ammo (turret shoots back)
             27  Gunner,   Core converts ammo

Terrain is entirely EMPTY, so every H is symmetric under HORIZONTAL reflection and
the geometry near the turret is identical in every cell of the sweep -- only the
dead space south of row 7 changes size.

    Core A (team 0) anchor (1,3)      Core B (team 1) anchor (W-3,3)
    turret tile T = (12,3)            contact tiles: W(11,3) N(12,2) E(13,3) S(12,4)

Travel lanes are chosen so no two bots ever need the same transit tile in any
legal cell (N + M <= 4, because a 1x1 turret has only four orthogonal neighbours):

    row 3  west  -> healer W and the constructor      row 3  east -> grinder E
    row 0        -> healer N                          row 1       -> grinder N
    row 6        -> healer S                          row 7       -> grinder S
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "generated"))

from generate_maps import (  # noqa: E402
    Core,
    GameMap,
    Symmetry,
    matching_symmetries,
    write_map,
    EMPTY,
)

OUT = pathlib.Path(__file__).resolve().parent
WIDTHS = (24, 25, 26, 27)


def build(width, height):
    rows = [[EMPTY for _ in range(width)] for _ in range(height)]
    return GameMap(
        width=width,
        height=height,
        rows=rows,
        cores=[
            Core(entity_id=1, team=0, x=1, y=3),
            Core(entity_id=2, team=1, x=width - 3, y=3),
        ],
        symmetry=Symmetry.HORIZONTAL,
    )


def main():
    made = 0
    for width in WIDTHS:
        for healers in range(4):
            for grinders in range(4):
                if healers + grinders > 4:
                    continue
                height = 10 + 4 * healers + grinders
                gm = build(width, height)
                assert Symmetry.HORIZONTAL in matching_symmetries(gm), (width, height)
                path = OUT / ("hg%dx%d.map26" % (width, height))
                write_map(path, gm)
                made += 1
    print("wrote %d arenas in %s" % (made, OUT))


if __name__ == "__main__":
    main()
