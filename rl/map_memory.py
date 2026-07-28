"""Per-unit persistent map memory: remembers terrain and last-seen occupancy across
turns, well beyond current vision. Stdlib-only (no torch/numpy) so this same module
can be bundled into the pure-Python ladder deployment (see export_pure_python.py),
not just used during training.

Terrain (wall/ore) is static, so once enough directly-observed tiles uniquely match
one of the bundled maps/*.map26 files, the rest of the map's terrain is filled in
immediately from that file -- this mirrors bots/opponent_luc's approach (itself
copied from x/luc's bots/1/utils/map.py), reimplemented here in a trimmed-down form
(env-only matching, no fixed-core disambiguation) since we only need it to produce
network input, not perfect atlas bookkeeping.

Occupancy (buildings/builder bots) *does* need staleness -- it changes during a
match and is only known where memory says a team's own unit last looked. That's
what "rounds since last seen" tracks per tile.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping

from fcode import Controller, Environment, Position, Team

MAPS_DIR = Path(__file__).resolve().parent.parent / "bots" / "rl" / "maps"

_ENV_CODE = {Environment.EMPTY: 0, Environment.WALL: 1, Environment.ORE_TITANIUM: 2}


@dataclass(slots=True)
class TileInfo:
    env: int  # 0 empty, 1 wall, 2 ore -- -1 if still totally unknown
    building_team: int = 0  # 0 none, 1 own, 2 enemy
    builder_team: int = 0  # 0 none, 1 own, 2 enemy
    age: int | None = None  # rounds since last directly observed; None = never seen
    env_known: bool = False


class KnownMap:
    __slots__ = ("name", "width", "height", "grid")

    def __init__(self, name: str, width: int, height: int, grid: list[list[int]]):
        self.name = name
        self.width = width
        self.height = height
        self.grid = grid  # grid[y][x] -> env code

    def env_at(self, x: int, y: int) -> int:
        return self.grid[y][x]


@lru_cache(maxsize=1)
def load_known_maps() -> Mapping[str, KnownMap]:
    if not MAPS_DIR.exists():
        return {}
    return {p.stem: _parse_map_file(p) for p in sorted(MAPS_DIR.glob("*.map26"))}


class MapMemory:
    """One instance per controlled unit -- hold as an instance attribute on Player
    (sub-interpreters keep Player state across rounds within one match)."""

    def __init__(self) -> None:
        self.tiles: dict[Position, TileInfo] = {}
        self.width: int | None = None
        self.height: int | None = None
        self.last_round: int | None = None
        self.candidates: set[str] | None = None  # None until dims known
        self.inferred: KnownMap | None = None

    def update(self, ct: Controller) -> None:
        current_round = ct.get_current_round()
        if self.last_round is not None and current_round > self.last_round:
            elapsed = current_round - self.last_round
            for tile in self.tiles.values():
                if tile.age is not None:
                    tile.age += elapsed
        self.last_round = current_round

        w, h = ct.get_map_width(), ct.get_map_height()
        if self.width != (w, h)[0] or self.height != (w, h)[1]:
            self.width, self.height = w, h
            self.candidates = {
                name
                for name, m in load_known_maps().items()
                if m.width == w and m.height == h
            }

        team = ct.get_team()
        seen_positions = []
        for pos in ct.get_nearby_tiles():
            env_code = _ENV_CODE[ct.get_tile_env(pos)]
            building_team = 0
            b_id = ct.get_tile_building_id(pos)
            if b_id is not None:
                building_team = 1 if ct.get_team(b_id) == team else 2
            builder_team = 0
            u_id = ct.get_tile_builder_bot_id(pos)
            if u_id is not None:
                builder_team = 1 if ct.get_team(u_id) == team else 2

            existing = self.tiles.get(pos)
            if existing is None:
                existing = TileInfo(env=env_code)
                self.tiles[pos] = existing
            existing.env = env_code
            existing.env_known = True
            existing.building_team = building_team
            existing.builder_team = builder_team
            existing.age = 0
            seen_positions.append((pos, env_code))

        if self.inferred is None and self.candidates and len(self.candidates) > 1:
            known = load_known_maps()
            still_valid = set()
            for name in self.candidates:
                m = known[name]
                if all(m.env_at(p.x, p.y) == e for p, e in seen_positions):
                    still_valid.add(name)
            self.candidates = still_valid
            if len(self.candidates) == 1:
                self.inferred = known[next(iter(self.candidates))]

    def _env_at(self, x: int, y: int) -> int:
        tile = self.tiles.get(Position(x, y))
        if tile is not None and tile.env_known:
            return tile.env
        if self.inferred is not None and 0 <= x < self.inferred.width and 0 <= y < self.inferred.height:
            return self.inferred.env_at(x, y)
        return -1  # unknown

    def local_patch(self, ct: Controller, radius: int) -> list[float]:
        """(2r+1)^2 tiles x 6 channels: wall, ore, own_building, enemy_building,
        own_unit, enemy_unit -- from memory, so it reflects last-known state for
        tiles outside current vision instead of going blank."""
        size = 2 * radius + 1
        pos = ct.get_position()
        w, h = self.width or ct.get_map_width(), self.height or ct.get_map_height()
        out = [0.0] * (size * size * 6)
        for gy in range(size):
            for gx in range(size):
                x, y = pos.x + (gx - radius), pos.y + (gy - radius)
                base = (gy * size + gx) * 6
                if x < 0 or y < 0 or x >= w or y >= h:
                    out[base + 0] = 1.0  # out-of-bounds as wall
                    continue
                tile = self.tiles.get(Position(x, y))
                env = tile.env if (tile is not None and tile.env_known) else self._env_at(x, y)
                if env == 1:
                    out[base + 0] = 1.0
                elif env == 2:
                    out[base + 1] = 1.0
                if tile is not None:
                    if tile.building_team == 1:
                        out[base + 2] = 1.0
                    elif tile.building_team == 2:
                        out[base + 3] = 1.0
                    if tile.builder_team == 1:
                        out[base + 4] = 1.0
                    elif tile.builder_team == 2:
                        out[base + 5] = 1.0
        return out

    def coarse_grid(self, ct: Controller, grid_size: int) -> list[float]:
        """grid_size x grid_size cells x 8 channels: the same 6 semantic channels
        (max-pooled per cell), + recency (freshest 1/(1+age) in the cell, 0 if
        never seen), + a self-mask marking the cell containing this unit."""
        w = self.width or ct.get_map_width()
        h = self.height or ct.get_map_height()
        pos = ct.get_position()
        cell_w = max(1, -(-w // grid_size))  # ceil
        cell_h = max(1, -(-h // grid_size))
        out = [0.0] * (grid_size * grid_size * 8)

        self_cx = min(pos.x // cell_w, grid_size - 1)
        self_cy = min(pos.y // cell_h, grid_size - 1)

        for pos_key, tile in self.tiles.items():
            if not (0 <= pos_key.x < w and 0 <= pos_key.y < h):
                continue
            cx = min(pos_key.x // cell_w, grid_size - 1)
            cy = min(pos_key.y // cell_h, grid_size - 1)
            base = (cy * grid_size + cx) * 8
            if tile.env_known:
                if tile.env == 1:
                    out[base + 0] = 1.0
                elif tile.env == 2:
                    out[base + 1] = 1.0
            if tile.building_team == 1:
                out[base + 2] = 1.0
            elif tile.building_team == 2:
                out[base + 3] = 1.0
            if tile.builder_team == 1:
                out[base + 4] = 1.0
            elif tile.builder_team == 2:
                out[base + 5] = 1.0
            if tile.age is not None:
                freshness = 1.0 / (1.0 + tile.age)
                if freshness > out[base + 6]:
                    out[base + 6] = freshness

        # Terrain from the inferred map, for cells with no direct/registry evidence.
        if self.inferred is not None:
            for cy in range(grid_size):
                for cx in range(grid_size):
                    base = (cy * grid_size + cx) * 8
                    if out[base + 0] or out[base + 1]:
                        continue
                    x0, y0 = cx * cell_w, cy * cell_h
                    x1, y1 = min(x0 + cell_w, w), min(y0 + cell_h, h)
                    has_wall = has_ore = False
                    for y in range(y0, y1):
                        for x in range(x0, x1):
                            e = self.inferred.env_at(x, y)
                            has_wall = has_wall or e == 1
                            has_ore = has_ore or e == 2
                    if has_wall:
                        out[base + 0] = 1.0
                    if has_ore:
                        out[base + 1] = 1.0

        self_base = (self_cy * grid_size + self_cx) * 8
        out[self_base + 7] = 1.0
        return out


def _parse_map_file(path: Path) -> KnownMap:
    fields = list(_protobuf_fields(path.read_bytes()))
    width = _required_varint(fields, 1)
    height = _required_varint(fields, 2)
    rows: list[list[int]] = []
    for field_number, wire_type, value in fields:
        if field_number == 3 and wire_type == 2:
            row_fields = list(_protobuf_fields(value))
            raw_tiles = _required_bytes(row_fields, 1)
            # raw tile bytes are already 0=empty/1=wall/2=ore, matching our env codes directly.
            rows.append(list(raw_tiles))
    return KnownMap(name=path.stem, width=width, height=height, grid=rows)


def _required_varint(fields, field_number: int) -> int:
    for number, wire_type, value in fields:
        if number == field_number and wire_type == 0:
            return value
    raise ValueError(f"Missing protobuf varint field {field_number}")


def _required_bytes(fields, field_number: int) -> bytes:
    for number, wire_type, value in fields:
        if number == field_number and wire_type == 2:
            return value
    raise ValueError(f"Missing protobuf bytes field {field_number}")


def _protobuf_fields(data: bytes) -> Iterable[tuple[int, int, int | bytes]]:
    offset = 0
    while offset < len(data):
        key, offset = _read_varint(data, offset)
        field_number = key >> 3
        wire_type = key & 0x07
        if wire_type == 0:
            value, offset = _read_varint(data, offset)
        elif wire_type == 2:
            length, offset = _read_varint(data, offset)
            value = data[offset : offset + length]
            offset += length
        elif wire_type == 1:
            value = data[offset : offset + 8]
            offset += 8
        elif wire_type == 5:
            value = data[offset : offset + 4]
            offset += 4
        else:
            raise ValueError(f"Unsupported protobuf wire type {wire_type}")
        yield field_number, wire_type, value


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
    raise ValueError("Truncated protobuf varint")
