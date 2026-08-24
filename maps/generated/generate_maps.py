"""Generate and validate fair, symmetric Florent Code League maps.

Hard validation follows the published rules and the official map editor:

* rectangular 8..30 by 8..30 terrain;
* EMPTY, WALL, and ORE_TITANIUM tiles only;
* exactly two non-overlapping 2x2 Cores;
* a one-tile EMPTY margin around each Core;
* terrain and Core placement symmetric under 180-degree rotation, horizontal
  reflection, or vertical reflection.

Generation additionally applies explicit playability policies: the two Core
spawn rings are connected and at least two reachable ore tiles exist. Those
policies make useful test arenas, but are not claimed as published guarantees.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
import random
import sys


EMPTY = 0
WALL = 1
ORE = 2
TERRAIN = {EMPTY, WALL, ORE}
MIN_SIZE = 8
MAX_SIZE = 30


class Symmetry(IntEnum):
    ROTATIONAL = 0
    HORIZONTAL = 1  # reflection across the vertical axis: x -> width - 1 - x
    VERTICAL = 2    # reflection across the horizontal axis: y -> height - 1 - y

    @property
    def label(self) -> str:
        return {
            Symmetry.ROTATIONAL: "rot",
            Symmetry.HORIZONTAL: "mirror-x",
            Symmetry.VERTICAL: "mirror-y",
        }[self]


@dataclass(frozen=True)
class Core:
    entity_id: int
    team: int
    x: int
    y: int

    @property
    def anchor(self) -> tuple[int, int]:
        return self.x, self.y


@dataclass
class GameMap:
    width: int
    height: int
    rows: list[list[int]]
    cores: list[Core]
    # Older bundled maps omit field 5, so their symmetry must be inferred.
    symmetry: Symmetry | None


def transform(
    tile: tuple[int, int], width: int, height: int, symmetry: Symmetry
) -> tuple[int, int]:
    x, y = tile
    if symmetry == Symmetry.ROTATIONAL:
        return width - 1 - x, height - 1 - y
    if symmetry == Symmetry.HORIZONTAL:
        return width - 1 - x, y
    return x, height - 1 - y


def transform_core_anchor(
    anchor: tuple[int, int], width: int, height: int, symmetry: Symmetry
) -> tuple[int, int]:
    """Transform a 2x2 footprint and return its transformed top-left tile."""
    x, y = anchor
    if symmetry == Symmetry.ROTATIONAL:
        return width - 2 - x, height - 2 - y
    if symmetry == Symmetry.HORIZONTAL:
        return width - 2 - x, y
    return x, height - 2 - y


def footprint(anchor: tuple[int, int]) -> set[tuple[int, int]]:
    x, y = anchor
    return {(x + dx, y + dy) for dx in (0, 1) for dy in (0, 1)}


def core_margin(
    anchor: tuple[int, int], width: int, height: int
) -> set[tuple[int, int]]:
    x, y = anchor
    return {
        (px, py)
        for px in range(x - 1, x + 3)
        for py in range(y - 1, y + 3)
        if 0 <= px < width and 0 <= py < height
    }


def spawn_ring(
    anchor: tuple[int, int], width: int, height: int
) -> set[tuple[int, int]]:
    return core_margin(anchor, width, height) - footprint(anchor)


def _varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative protobuf varint")
    output = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        output.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(output)


def _field_varint(number: int, value: int) -> bytes:
    return _varint(number << 3) + _varint(value)


def _field_bytes(number: int, value: bytes) -> bytes:
    return _varint((number << 3) | 2) + _varint(len(value)) + value


def encode(game_map: GameMap) -> bytes:
    if game_map.symmetry is None:
        raise ValueError("encoding requires explicit symmetry metadata")
    output = bytearray()
    output += _field_varint(1, game_map.width)
    output += _field_varint(2, game_map.height)
    for row in game_map.rows:
        output += _field_bytes(3, _field_bytes(1, bytes(row)))
    for core in sorted(game_map.cores, key=lambda item: item.entity_id):
        position = _field_varint(1, core.x) + _field_varint(2, core.y)
        body = _field_varint(1, core.entity_id)
        if core.team:
            body += _field_varint(2, core.team)
        body += _field_bytes(3, position)
        output += _field_bytes(4, body)
    # Current bundled maps predate this editor metadata and omit field 5. The
    # current official editor writes it; the engine accepts both forms.
    output += _field_varint(5, int(game_map.symmetry))
    return bytes(output)


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if offset >= len(data):
            raise ValueError("truncated protobuf varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift > 63:
            raise ValueError("protobuf varint is too long")


def _fields(data: bytes) -> list[tuple[int, int, int | bytes]]:
    offset = 0
    result: list[tuple[int, int, int | bytes]] = []
    while offset < len(data):
        key, offset = _read_varint(data, offset)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, offset = _read_varint(data, offset)
        elif wire == 2:
            length, offset = _read_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ValueError("truncated protobuf bytes field")
            value, offset = data[offset:end], end
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        result.append((number, wire, value))
    return result


def _single_varint(
    fields: list[tuple[int, int, int | bytes]], number: int, default: int | None = None
) -> int:
    values = [value for field, wire, value in fields if field == number and wire == 0]
    if not values:
        if default is not None:
            return default
        raise ValueError(f"missing protobuf field {number}")
    if len(values) != 1 or not isinstance(values[0], int):
        raise ValueError(f"invalid protobuf field {number}")
    return values[0]


def decode(data: bytes) -> GameMap:
    top = _fields(data)
    width = _single_varint(top, 1)
    height = _single_varint(top, 2)
    raw_rows = [
        value for number, wire, value in top if number == 3 and wire == 2
    ]
    rows: list[list[int]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, bytes):
            raise ValueError("invalid row field")
        row_fields = _fields(raw_row)
        tiles = [
            value
            for number, wire, value in row_fields
            if number == 1 and wire == 2
        ]
        if len(tiles) != 1 or not isinstance(tiles[0], bytes):
            raise ValueError("invalid tile row")
        rows.append(list(tiles[0]))

    cores: list[Core] = []
    for raw_core in [
        value for number, wire, value in top if number == 4 and wire == 2
    ]:
        if not isinstance(raw_core, bytes):
            raise ValueError("invalid Core field")
        core_fields = _fields(raw_core)
        entity_id = _single_varint(core_fields, 1)
        team = _single_varint(core_fields, 2, 0)
        positions = [
            value
            for number, wire, value in core_fields
            if number == 3 and wire == 2
        ]
        if len(positions) != 1 or not isinstance(positions[0], bytes):
            raise ValueError("invalid Core position")
        position_fields = _fields(positions[0])
        cores.append(
            Core(
                entity_id,
                team,
                _single_varint(position_fields, 1, 0),
                _single_varint(position_fields, 2, 0),
            )
        )

    symmetry_values = [
        value for number, wire, value in top if number == 5 and wire == 0
    ]
    if len(symmetry_values) > 1:
        raise ValueError("multiple symmetry metadata fields")
    if symmetry_values:
        try:
            symmetry = Symmetry(symmetry_values[0])
        except ValueError as error:
            raise ValueError(
                f"unknown symmetry value {symmetry_values[0]}"
            ) from error
    else:
        symmetry = None
    return GameMap(width, height, rows, cores, symmetry)


def read_map(path: Path) -> GameMap:
    return decode(path.read_bytes())


def write_map(path: Path, game_map: GameMap) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode(game_map))


def matching_symmetries(game_map: GameMap) -> list[Symmetry]:
    """Return every editor-supported symmetry that swaps the two teams."""
    if len(game_map.cores) != 2:
        return []
    first, second = sorted(game_map.cores, key=lambda item: item.team)
    matches = []
    for symmetry in Symmetry:
        if transform_core_anchor(
            first.anchor, game_map.width, game_map.height, symmetry
        ) != second.anchor:
            continue
        symmetric = True
        for y in range(game_map.height):
            for x in range(game_map.width):
                tx, ty = transform(
                    (x, y), game_map.width, game_map.height, symmetry
                )
                if game_map.rows[y][x] != game_map.rows[ty][tx]:
                    symmetric = False
                    break
            if not symmetric:
                break
        if symmetric:
            matches.append(symmetry)
    return matches


def _reachable(
    game_map: GameMap, starts: set[tuple[int, int]]
) -> set[tuple[int, int]]:
    blocked = set().union(*(footprint(core.anchor) for core in game_map.cores))
    queue = deque(
        tile
        for tile in starts
        if tile not in blocked and game_map.rows[tile[1]][tile[0]] != WALL
    )
    seen = set(queue)
    while queue:
        x, y = queue.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == dy == 0:
                    continue
                nxt = x + dx, y + dy
                if (
                    nxt in seen
                    or nxt in blocked
                    or not (0 <= nxt[0] < game_map.width and 0 <= nxt[1] < game_map.height)
                    or game_map.rows[nxt[1]][nxt[0]] == WALL
                ):
                    continue
                seen.add(nxt)
                queue.append(nxt)
    return seen


def validate(game_map: GameMap, require_playable: bool = True) -> list[str]:
    errors: list[str] = []
    width, height = game_map.width, game_map.height
    if not (MIN_SIZE <= width <= MAX_SIZE and MIN_SIZE <= height <= MAX_SIZE):
        errors.append(
            f"dimensions must each be {MIN_SIZE}..{MAX_SIZE}, got {width}x{height}"
        )
    if len(game_map.rows) != height:
        errors.append(f"expected {height} rows, got {len(game_map.rows)}")
    for y, row in enumerate(game_map.rows):
        if len(row) != width:
            errors.append(f"row {y} has width {len(row)}, expected {width}")
        invalid = sorted(set(row) - TERRAIN)
        if invalid:
            errors.append(f"row {y} contains invalid terrain values {invalid}")
    if errors:
        return errors

    if len(game_map.cores) != 2:
        errors.append(f"expected exactly two Cores, got {len(game_map.cores)}")
        return errors
    cores = sorted(game_map.cores, key=lambda item: item.team)
    if {core.team for core in cores} != {0, 1}:
        errors.append("Core teams must be exactly 0 and 1")
    if {core.entity_id for core in cores} != {1, 2}:
        errors.append("Core entity ids must be exactly 1 and 2")
    for core in cores:
        if not (0 <= core.x < width - 1 and 0 <= core.y < height - 1):
            errors.append(f"Core {core.team} footprint is out of bounds")
    if errors:
        return errors

    first, second = cores
    if footprint(first.anchor) & footprint(second.anchor):
        errors.append("Core footprints overlap")
    if max(abs(first.x - second.x), abs(first.y - second.y)) <= 2:
        errors.append("Core footprints need a one-tile clear margin")
    protected = core_margin(first.anchor, width, height) | core_margin(
        second.anchor, width, height
    )
    for x, y in sorted(protected):
        if game_map.rows[y][x] != EMPTY:
            errors.append(f"Core margin tile {(x, y)} is not EMPTY")

    valid_symmetries = matching_symmetries(game_map)
    if not valid_symmetries:
        errors.append(
            "terrain and Core placement have no valid rotational, "
            "left-right, or top-bottom symmetry"
        )
    elif (
        game_map.symmetry is not None
        and game_map.symmetry not in valid_symmetries
    ):
        errors.append(
            f"field-5 symmetry says {game_map.symmetry.label}, but valid "
            f"symmetries are {[item.label for item in valid_symmetries]}"
        )

    if require_playable and not errors:
        first_ring = spawn_ring(first.anchor, width, height)
        second_ring = spawn_ring(second.anchor, width, height)
        reached = _reachable(game_map, first_ring)
        if not (reached & second_ring):
            errors.append("playability: Core spawn rings are not connected")
        reachable_ore = {
            tile
            for tile in reached
            if game_map.rows[tile[1]][tile[0]] == ORE
        }
        if len(reachable_ore) < 2:
            errors.append("playability: fewer than two reachable ore tiles")
    return errors


def _core_pair(
    rng: random.Random, width: int, height: int, symmetry: Symmetry
) -> tuple[tuple[int, int], tuple[int, int]]:
    candidates = []
    # Keep the full twelve-tile spawn ring in bounds. This is a generation
    # policy matching the current pool, not a published map guarantee.
    for y in range(1, height - 2):
        for x in range(1, width - 2):
            first = x, y
            second = transform_core_anchor(first, width, height, symmetry)
            if not (1 <= second[0] < width - 2 and 1 <= second[1] < height - 2):
                continue
            if max(abs(x - second[0]), abs(y - second[1])) <= 2:
                continue
            # Prefer substantial separation while retaining some compact maps.
            separation = max(abs(x - second[0]), abs(y - second[1]))
            candidates.extend([(first, second)] * max(1, separation - 2))
    if not candidates:
        raise ValueError(f"no valid Core placement on {width}x{height}")
    return rng.choice(candidates)


def _orbits(
    width: int, height: int, symmetry: Symmetry
) -> list[tuple[tuple[int, int], ...]]:
    seen: set[tuple[int, int]] = set()
    result = []
    for y in range(height):
        for x in range(width):
            tile = x, y
            if tile in seen:
                continue
            paired = transform(tile, width, height, symmetry)
            orbit = tuple(sorted({tile, paired}))
            seen.update(orbit)
            result.append(orbit)
    return result


def _smooth(
    rows: list[list[int]],
    width: int,
    height: int,
    symmetry: Symmetry,
    protected: set[tuple[int, int]],
    rounds: int,
) -> list[list[int]]:
    orbits = _orbits(width, height, symmetry)
    for _ in range(rounds):
        previous = [row[:] for row in rows]
        for orbit in orbits:
            if any(tile in protected for tile in orbit):
                for x, y in orbit:
                    rows[y][x] = EMPTY
                continue
            x, y = orbit[0]
            neighbours = 0
            total = 0
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == dy == 0:
                        continue
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and 0 <= ny < height:
                        total += 1
                        neighbours += previous[ny][nx] == WALL
            ratio = neighbours / max(total, 1)
            value = WALL if ratio >= 0.58 else EMPTY if ratio <= 0.28 else previous[y][x]
            for ox, oy in orbit:
                rows[oy][ox] = value
    return rows


def generate_one(rng: random.Random, index: int) -> GameMap:
    for _attempt in range(500):
        width = rng.randint(MIN_SIZE, MAX_SIZE)
        height = rng.randint(MIN_SIZE, MAX_SIZE)
        symmetry = rng.choice(list(Symmetry))
        try:
            first_anchor, second_anchor = _core_pair(rng, width, height, symmetry)
        except ValueError:
            continue
        cores = [
            Core(1, 0, *first_anchor),
            Core(2, 1, *second_anchor),
        ]
        protected = core_margin(first_anchor, width, height) | core_margin(
            second_anchor, width, height
        )
        rows = [[EMPTY for _ in range(width)] for _ in range(height)]
        density = rng.uniform(0.03, 0.30)
        for orbit in _orbits(width, height, symmetry):
            if any(tile in protected for tile in orbit):
                continue
            if rng.random() < density:
                for x, y in orbit:
                    rows[y][x] = WALL
        rows = _smooth(
            rows,
            width,
            height,
            symmetry,
            protected,
            rng.randint(0, 2),
        )
        candidate = GameMap(width, height, rows, cores, symmetry)
        first_reached = _reachable(
            candidate, spawn_ring(first_anchor, width, height)
        )
        if not (
            first_reached & spawn_ring(second_anchor, width, height)
        ):
            continue

        ore_candidates = []
        for orbit in _orbits(width, height, symmetry):
            if (
                any(tile in protected for tile in orbit)
                or any(rows[y][x] == WALL for x, y in orbit)
                or not all(tile in first_reached for tile in orbit)
            ):
                continue
            ore_candidates.append(orbit)
        rng.shuffle(ore_candidates)
        area = width * height
        target = rng.randint(2, min(24, max(4, area // 28)))
        ore_count = 0
        for orbit in ore_candidates:
            for x, y in orbit:
                rows[y][x] = ORE
            ore_count += len(orbit)
            if ore_count >= target:
                break
        if ore_count < 2:
            continue
        errors = validate(candidate, require_playable=True)
        if not errors:
            return candidate
    raise RuntimeError(f"failed to generate map {index} after 500 attempts")


def _statistics(game_map: GameMap) -> str:
    walls = sum(tile == WALL for row in game_map.rows for tile in row)
    ores = sum(tile == ORE for row in game_map.rows for tile in row)
    labels = [symmetry.label for symmetry in matching_symmetries(game_map)]
    symmetry_label = (
        game_map.symmetry.label
        if game_map.symmetry is not None
        else "|".join(labels)
    )
    return (
        f"{game_map.width}x{game_map.height} {symmetry_label} "
        f"walls={walls} ores={ores} "
        f"cores={game_map.cores[0].anchor}/{game_map.cores[1].anchor}"
    )


def command_generate(args: argparse.Namespace) -> int:
    output = Path(args.output)
    rng = random.Random(args.seed)
    written = []
    for index in range(args.count):
        game_map = generate_one(rng, index)
        name = (
            f"random-{args.seed}-{index:03d}-{game_map.symmetry.label}-"
            f"{game_map.width}x{game_map.height}.map26"
        )
        path = output / name
        if path.exists() and not args.overwrite:
            raise FileExistsError(f"{path} exists; pass --overwrite to replace it")
        write_map(path, game_map)
        round_trip = read_map(path)
        errors = validate(round_trip, require_playable=True)
        if errors:
            raise ValueError(f"{path}: {'; '.join(errors)}")
        written.append(path)
        print(f"{path}: {_statistics(round_trip)}")
    print(f"generated and validated {len(written)} maps in {output}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    paths: list[Path] = []
    for raw in args.paths:
        path = Path(raw)
        if path.is_dir():
            paths.extend(sorted(path.glob("*.map26")))
        else:
            paths.append(path)
    failures = 0
    for path in paths:
        try:
            game_map = read_map(path)
            errors = validate(game_map, require_playable=not args.rules_only)
        except (OSError, ValueError) as error:
            errors = [str(error)]
        if errors:
            failures += 1
            print(f"INVALID {path}:")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"valid {path}: {_statistics(game_map)}")
    print(f"validated {len(paths)} maps; failures={failures}")
    return bool(failures)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(required=True)

    generate = subcommands.add_parser("generate", help="generate random maps")
    generate.add_argument("--count", type=int, default=24)
    generate.add_argument("--seed", type=int, default=20260731)
    generate.add_argument(
        "--output", default=str(Path(__file__).resolve().parent)
    )
    generate.add_argument("--overwrite", action="store_true")
    generate.set_defaults(handler=command_generate)

    validate_command = subcommands.add_parser(
        "validate", help="validate map files or directories"
    )
    validate_command.add_argument("paths", nargs="+")
    validate_command.add_argument(
        "--rules-only",
        action="store_true",
        help="skip generator playability policies",
    )
    validate_command.set_defaults(handler=command_validate)
    return result


def main() -> int:
    args = parser().parse_args()
    if getattr(args, "count", 1) < 1:
        raise ValueError("--count must be positive")
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
