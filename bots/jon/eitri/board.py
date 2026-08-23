"""The map as a fixed grid.

Every unit in eitri plans from the same board, so the board is a plain value
object with no notion of what has been seen: the atlas hands us the whole map
on round zero and nothing about the terrain ever changes.  Buildings and bots
come and go on top of it, and that belongs to the executor, not here.

Coordinates are (x, y) with y increasing downward, matching both the atlas
rows and the engine's NORTH = (0, -1).
"""

WALL = "#"
ORE = "O"
EMPTY = "."

# (dx, dy) for the four cardinal steps, in a fixed order so that every unit
# breaks ties the same way and the plans they compute independently agree.
STEPS = ((0, -1), (1, 0), (0, 1), (-1, 0))


def block(anchor):
    """The 2x2 footprint of a Core given its top-left anchor."""
    x, y = anchor
    return frozenset({(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)})


class Board:
    __slots__ = ("name", "width", "height", "rows", "home", "away",
                 "home_tiles", "away_tiles", "ore", "_walk")

    def __init__(self, name, width, height, rows, home, away):
        self.name = name
        self.width = width
        self.height = height
        self.rows = rows
        self.home = home
        self.away = away
        self.home_tiles = block(home)
        self.away_tiles = block(away)
        self.ore = frozenset((x, y)
                             for y, row in enumerate(rows)
                             for x, tile in enumerate(row) if tile == ORE)
        # Walkability is asked for in every BFS, so settle it once.
        solid = set(self.home_tiles) | set(self.away_tiles)
        self._walk = frozenset(
            (x, y)
            for y, row in enumerate(rows)
            for x, tile in enumerate(row)
            if tile != WALL and (x, y) not in solid)

    # ------------------------------------------------------------------
    def inside(self, tile) -> bool:
        return 0 <= tile[0] < self.width and 0 <= tile[1] < self.height

    def at(self, tile) -> str:
        return self.rows[tile[1]][tile[0]]

    def walkable(self, tile) -> bool:
        """Whether a Builder could ever stand here.

        Ore counts as walkable: a deposit is open ground until somebody puts a
        Harvester on it.  Both Cores are solid, including our own -- the 2x2
        footprint is never bot-passable, not even for the team that owns it.
        """
        return tile in self._walk

    def neighbours(self, tile):
        """The walkable cardinal neighbours of `tile`."""
        x, y = tile
        out = []
        for dx, dy in STEPS:
            spot = (x + dx, y + dy)
            if spot in self._walk:
                out.append(spot)
        return out

    def ring(self):
        """Tiles the Core can spawn onto: its adjacent ring, diagonals included.

        Returned in a fixed order -- reading order -- so that ties anywhere
        downstream resolve identically for every unit.
        """
        x, y = self.home
        out = []
        for dy in range(-1, 3):
            for dx in range(-1, 3):
                spot = (x + dx, y + dy)
                if spot not in self.home_tiles and spot in self._walk:
                    out.append(spot)
        return out


def flood(board, sources, blocked=frozenset()):
    """Step counts from the nearest source, over walkable tiles.

    Sources need not be walkable themselves -- a Core's footprint and an ore
    tile under a planned Harvester are both legitimate starting points for
    "how far is this from there" -- so the first expansion goes out of them
    regardless and every later one respects `blocked`.
    """
    dist = {tile: 0 for tile in sources}
    frontier = list(dist)
    step = 0
    while frontier:
        step += 1
        nxt = []
        for tile in frontier:
            x, y = tile
            for dx, dy in STEPS:
                spot = (x + dx, y + dy)
                if spot in dist or spot in blocked:
                    continue
                if not board.walkable(spot):
                    continue
                dist[spot] = step
                nxt.append(spot)
        frontier = nxt
    return dist
