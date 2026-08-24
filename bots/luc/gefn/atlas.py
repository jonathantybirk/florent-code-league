"""Published-map oracle deliberately excluded from fair bots.

Dimensions plus our fixed Core anchor uniquely identify every map in the
current official pool.  Once identified, the bundled map supplies static
terrain and the opposing Core before either has been scouted.  Unknown maps
return ``None`` and retain Tempest Fast's ordinary observation-only policy.
"""

from dataclasses import dataclass
from fcode import Environment

from atlas_data import ROWS


@dataclass(frozen=True, slots=True)
class AtlasMap:
    name: str
    width: int
    height: int
    enemy_core: tuple[int, int]
    walls: frozenset[tuple[int, int]]
    ores: frozenset[tuple[int, int]]


_INDEX = {
    (18, 18, (2, 14)): ("atoll", (14, 2)),
    (18, 18, (14, 2)): ("atoll", (2, 14)),
    (26, 26, (3, 22)): ("aurora", (21, 2)),
    (26, 26, (21, 2)): ("aurora", (3, 22)),
    (21, 8, (0, 6)): ("bridge", (19, 6)),
    (21, 8, (19, 6)): ("bridge", (0, 6)),
    (16, 16, (2, 11)): ("crossfire", (12, 3)),
    (16, 16, (12, 3)): ("crossfire", (2, 11)),
    (12, 12, (1, 8)): ("duel", (9, 2)),
    (12, 12, (9, 2)): ("duel", (1, 8)),
    (20, 20, (2, 15)): ("fjord", (16, 3)),
    (20, 20, (16, 3)): ("fjord", (2, 15)),
    (25, 25, (2, 20)): ("hive", (21, 3)),
    (25, 25, (21, 3)): ("hive", (2, 20)),
    (16, 16, (0, 0)): ("jackpot", (14, 14)),
    (16, 16, (14, 14)): ("jackpot", (0, 0)),
    (28, 20, (2, 8)): ("longship", (24, 8)),
    (28, 20, (24, 8)): ("longship", (2, 8)),
    (14, 18, (2, 2)): ("pinch", (2, 14)),
    (14, 18, (2, 14)): ("pinch", (2, 2)),
    (24, 24, (2, 2)): ("quarry", (20, 20)),
    (24, 24, (20, 20)): ("quarry", (2, 2)),
    (24, 24, (2, 11)): ("runestone", (20, 11)),
    (24, 24, (20, 11)): ("runestone", (2, 11)),
    (16, 12, (4, 5)): ("showdown", (10, 5)),
    (16, 12, (10, 5)): ("showdown", (4, 5)),
    (22, 22, (2, 17)): ("skerry", (18, 3)),
    (22, 22, (18, 3)): ("skerry", (2, 17)),
    (10, 10, (1, 1)): ("sprint", (7, 7)),
    (10, 10, (7, 7)): ("sprint", (1, 1)),
    (20, 26, (2, 2)): ("strait", (2, 22)),
    (20, 26, (2, 22)): ("strait", (2, 2)),
    (12, 8, (0, 6)): ("string", (10, 0)),
    (12, 8, (10, 0)): ("string", (0, 6)),
    (25, 15, (0, 0)): ("sweden", (0, 13)),
    (25, 15, (0, 13)): ("sweden", (0, 0)),
    (21, 21, (2, 2)): ("twins", (2, 17)),
    (21, 21, (2, 17)): ("twins", (2, 2)),
    (11, 16, (0, 0)): ("vase", (9, 0)),
    (11, 16, (9, 0)): ("vase", (0, 0)),
    (24, 24, (2, 19)): ("vault", (20, 3)),
    (24, 24, (20, 3)): ("vault", (2, 19)),
}


def identify(width: int, height: int, own_core: tuple[int, int]):
    match = _INDEX.get((width, height, own_core))
    if match is None:
        return None
    name, enemy_core = match
    walls, ores = _terrain(name)
    return AtlasMap(name, width, height, enemy_core, walls, ores)


def identify_visible(ct, own_core: tuple[int, int]):
    """Accept an atlas key only when every currently visible tile agrees."""
    known = identify(ct.get_map_width(), ct.get_map_height(), own_core)
    if known is None:
        return None
    for position in ct.get_nearby_tiles():
        tile = tuple(position)
        expected = (Environment.WALL if tile in known.walls else
                    Environment.ORE_TITANIUM if tile in known.ores else
                    Environment.EMPTY)
        if ct.get_tile_env(position) != expected:
            return None
    return known


def _terrain(name: str):
    walls, ores = set(), set()
    for y, row in enumerate(ROWS[name]):
        for x, tile in enumerate(row):
            if tile == "#":
                walls.add((x, y))
            elif tile == "O":
                ores.add((x, y))
    return frozenset(walls), frozenset(ores)
