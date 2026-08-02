"""Build the defence-area lab arenas into maps/lab/."""
import sys, pathlib
ROOT = pathlib.Path(r"c:/Users/edlun/Desktop/lucky shots/Hackathons/florent-code-league")
sys.path.insert(0, str(ROOT / "maps" / "generated"))
from generate_maps import (GameMap, Core, Symmetry, write_map, read_map, encode,
                           decode, validate, EMPTY, WALL, ORE)

OUT = ROOT / "maps" / "lab"
OUT.mkdir(parents=True, exist_ok=True)


def mk(name, w, h, anchor_a, walls=(), ores=(), sym=Symmetry.ROTATIONAL):
    rows = [[EMPTY] * w for _ in range(h)]
    for (x, y) in walls:
        rows[y][x] = WALL
    for (x, y) in ores:
        rows[y][x] = ORE
    ax, ay = anchor_a
    if sym == Symmetry.ROTATIONAL:
        bx, by = w - 2 - ax, h - 2 - ay
    elif sym == Symmetry.HORIZONTAL:
        bx, by = w - 2 - ax, ay
    else:
        bx, by = ax, h - 2 - ay
    gm = GameMap(w, h, rows, [Core(1, 0, ax, ay), Core(2, 1, bx, by)], sym)
    errs = validate(gm, require_playable=True)
    print(f"{name:<10} {w}x{h} A={anchor_a} B={(bx,by)} errors={errs}")
    if errs:
        errs2 = validate(gm, require_playable=False)
        print("   hard errors:", errs2)
        if errs2:
            return None
    write_map(OUT / f"{name}.map26", gm)
    rt = read_map(OUT / f"{name}.map26")
    assert encode(rt) == encode(gm)
    return gm


def rot(w, h, t):
    return (w - 1 - t[0], h - 1 - t[1])


# ---------------------------------------------------------------- dopen
# 20x12 open field.  Core A anchor (2,5) -> foot (2,5)(3,5)(2,6)(3,6)
#                    Core B anchor (16,5) -> foot (16,5)(17,5)(16,6)(17,6)
# ore pairs far from the action, in the top/bottom rows.
W, H = 20, 12
ores = []
for t in [(6, 0), (9, 0)]:
    ores.append(t)
    ores.append(rot(W, H, t))
mk("dopen", W, H, (2, 5), ores=ores)

# ---------------------------------------------------------------- dcorr
# 20x11 single-tile corridor at y=5 plus the two Core margin pockets.
W, H = 20, 11
empt = set()
for x in range(W):
    empt.add((x, 5))
for x in range(0, 4):
    for y in range(3, 7):
        empt.add((x, y))
for x in range(16, 20):
    for y in range(4, 8):
        empt.add((x, y))
walls = [(x, y) for y in range(H) for x in range(W) if (x, y) not in empt]
mk("dcorr", W, H, (1, 4), walls=walls, ores=[(8, 5), (11, 5)])

# ---------------------------------------------------------------- dore
# 20x12 open, with an ORE tile orthogonally adjacent to each Core footprint so a
# harvester can be planted next to the Core (tiebreak experiments).
# Core A foot (2,5)(3,5)(2,6)(3,6); margin is x 1..4, y 4..7 and must be EMPTY,
# so put ore at (5,5) / rot180 (14,6) -- just outside the margin, 2 tiles from foot.
W, H = 20, 12
mk("dore", W, H, (2, 5), ores=[(5, 5), (14, 6), (5, 6), (14, 5)])

# ---------------------------------------------------------------- dwall
# 20x12 open field with a single WALL tile at (6,5) (and its rot180 twin (13,6)).
# A turret at (9,5) facing WEST has (6,5) squarely in its line -- the terrain-wall
# analogue of the barrier test in d_sent2.
W, H = 20, 12
mk("dwall", W, H, (2, 5), walls=[(6, 5), rot(W, H, (6, 5))],
   ores=[(6, 0), rot(W, H, (6, 0)), (9, 0), rot(W, H, (9, 0))])
