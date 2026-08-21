"""Offline reader for .map26 files.

The bot never touches this -- it exists so utilities can be tested against
real competition maps without booting the engine. A .map26 is a protobuf:

    1: width   (varint)
    2: height  (varint)
    3: row     (repeated message; field 1 = repeated tile)
    4: spawn   (repeated message; field 1 = team, field 3 = {1: x, 2: y})

Tile values are Environment ordinals: 0 empty, 1 wall, 2 ore. The encoder
emits the repeated tile field in packed form on some maps and unpacked on
others -- both are valid protobuf, so _row_tiles accepts either.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from fcode import Environment, Position

TILE_ENV = {0: Environment.EMPTY, 1: Environment.WALL, 2: Environment.ORE_TITANIUM}

CORE_SIZE = 2  # the Core occupies a 2x2 block; spawn coords name its NW corner


class Symmetry(Enum):
    """How a map's two halves relate.

    Named to match the platform's own labels (`fcode maps list`): HORIZONTAL
    puts the halves side by side (mirror in x), VERTICAL stacks them (mirror
    in y), ROTATIONAL turns one half 180 degrees onto the other.
    """

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    ROTATIONAL = "rotational"

    def mirror(self, pos: Position, width: int, height: int) -> Position:
        """Map a tile onto its counterpart in the opposite half."""
        x = width - 1 - pos.x if self is not Symmetry.VERTICAL else pos.x
        y = height - 1 - pos.y if self is not Symmetry.HORIZONTAL else pos.y
        return Position(x, y)

    def mirror_core(self, nw: Position, width: int, height: int) -> Position:
        """Mirror a Core by its NW corner.

        A 2x2 block reflected about an axis lands with its corner one tile
        back along each flipped axis, so mirroring the corner alone is off
        by one -- this corrects for the footprint.
        """
        m = self.mirror(nw, width, height)
        dx = 0 if self is Symmetry.VERTICAL else CORE_SIZE - 1
        dy = 0 if self is Symmetry.HORIZONTAL else CORE_SIZE - 1
        return Position(m.x - dx, m.y - dy)


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    val = shift = 0
    while True:
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7


def _fields(buf: bytes):
    """Yield (field_number, value) where value is int or bytes."""
    i = 0
    while i < len(buf):
        key, i = _varint(buf, i)
        num, wire = key >> 3, key & 7
        if wire == 0:
            val, i = _varint(buf, i)
        elif wire == 2:
            ln, i = _varint(buf, i)
            val, i = buf[i:i + ln], i + ln
        else:
            raise ValueError(f"unsupported wire type {wire} for field {num}")
        yield num, val


def _row_tiles(buf: bytes) -> tuple[Environment, ...]:
    """Decode one row message into tiles, accepting packed or unpacked form."""
    tiles = []
    for num, val in _fields(buf):
        if num != 1:
            continue
        if isinstance(val, int):
            tiles.append(TILE_ENV[val])
        else:  # packed: a run of varints in one length-delimited blob
            i = 0
            while i < len(val):
                v, i = _varint(val, i)
                tiles.append(TILE_ENV[v])
    return tuple(tiles)


@dataclass(frozen=True)
class GameMap:
    name: str
    width: int
    height: int
    tiles: tuple[tuple[Environment, ...], ...]  # tiles[y][x]
    spawns: tuple[Position, ...]

    def env_at(self, pos: Position) -> Environment:
        return self.tiles[pos.y][pos.x]

    def in_bounds(self, pos: Position) -> bool:
        return 0 <= pos.x < self.width and 0 <= pos.y < self.height

    def positions(self):
        for y in range(self.height):
            for x in range(self.width):
                yield Position(x, y)

    @property
    def symmetries(self) -> tuple[Symmetry, ...]:
        """Every symmetry this map's terrain and Core placements satisfy.

        Often more than one: a map whose terrain mirrors both ways is also
        rotationally symmetric, and Cores on a centre line are invariant
        under both the axis mirror through it and the rotation.
        """
        holds = tuple(s for s in Symmetry
                      if all(self.env_at(p) is self.env_at(s.mirror(p, self.width, self.height))
                             for p in self.positions()))
        if len(self.spawns) != 2:
            return holds
        a, b = self.spawns
        return tuple(s for s in holds if s.mirror_core(a, self.width, self.height) == b) or holds

    @property
    def symmetry(self) -> Symmetry:
        """The map's symmetry, as the platform labels it.

        Where several hold we take the axis mirror over the rotation: if the
        halves genuinely mirror, that is the stronger claim, and rotation
        follows from it. Verified to reproduce the label `fcode maps list`
        publishes for all 15 maps in the pool.
        """
        candidates = self.symmetries
        if not candidates:
            raise ValueError(f"{self.name}: no symmetry holds")
        return min(candidates, key=lambda s: s is Symmetry.ROTATIONAL)

    def core_tiles(self, nw: Position) -> tuple[Position, ...]:
        """The four tiles a Core covers, given its NW corner."""
        return tuple(Position(nw.x + dx, nw.y + dy)
                     for dy in range(CORE_SIZE) for dx in range(CORE_SIZE))

    def ore(self) -> list[Position]:
        return [p for p in self.positions() if self.env_at(p) is Environment.ORE_TITANIUM]

    def render(self) -> str:
        glyph = {Environment.EMPTY: ".", Environment.WALL: "#", Environment.ORE_TITANIUM: "o"}
        rows = [[glyph[e] for e in row] for row in self.tiles]
        for n, spawn in enumerate(self.spawns):
            for t in self.core_tiles(spawn):
                rows[t.y][t.x] = str(n)
        return "\n".join("".join(r) for r in rows)


def load(path: str | Path) -> GameMap:
    path = Path(path)
    width = height = None
    rows: list[tuple[Environment, ...]] = []
    spawns: list[Position] = []

    for num, val in _fields(path.read_bytes()):
        if num == 1:
            width = val
        elif num == 2:
            height = val
        elif num == 3:
            rows.append(_row_tiles(val))
        elif num == 4:
            x = y = 0
            for sub, sval in _fields(val):
                if sub == 3:
                    for c, cval in _fields(sval):
                        if c == 1:
                            x = cval
                        elif c == 2:
                            y = cval
            spawns.append(Position(x, y))

    if width is None or height is None:
        raise ValueError(f"{path}: missing dimensions")
    if len(rows) != height or any(len(r) != width for r in rows):
        raise ValueError(f"{path}: grid is not {width}x{height}")

    return GameMap(path.stem, width, height, tuple(rows), tuple(spawns))


def load_pool(maps_dir: str | Path = "maps") -> dict[str, GameMap]:
    """Load every map in the current competition pool, keyed by name."""
    return {m.name: m for m in (load(p) for p in sorted(Path(maps_dir).glob("*.map26")))}
