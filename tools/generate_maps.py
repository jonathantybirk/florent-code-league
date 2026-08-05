"""Generate random symmetric .map26 maps for unknown-terrain testing.

The published pool is 21 maps, every one of which every bot in the field has
been tuned against. A bot that is only measured there cannot be told apart from
a bot that has been fitted to it, and the final is played somewhere else. These
maps are drawn fresh from the rules the real ones obey -- rectangular, 8x8 to
30x30, symmetric, two Cores -- so a score on them is a score on terrain nobody
tuned against.

    uv run python tools/generate_maps.py --out maps/random --count 24 --seed 1

All three symmetries the game's fairness allows are drawn from, in equal
measure: 180-degree rotation, horizontal mirror and vertical mirror. That is
deliberate -- the enemy-Core inference has to pick between exactly those three,
and a test set of only rotations would score a bot that always guesses rotation
as though it were correct.
"""

from __future__ import annotations

import argparse
import random
from collections import deque
from pathlib import Path

EMPTY, WALL, ORE = 0, 1, 2


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _bytes_field(field: int, payload: bytes) -> bytes:
    return _tag(field, 2) + _varint(len(payload)) + payload


def encode(width: int, height: int, grid, cores) -> bytes:
    out = bytearray()
    out += _tag(1, 0) + _varint(width)
    out += _tag(2, 0) + _varint(height)
    for row in grid:
        out += _bytes_field(3, _bytes_field(1, bytes(row)))
    # Entity: field 1 is the id, field 2 the team (omitted for team 0, which is
    # how the shipped maps encode it), field 3 the position.
    for index, (team, (x, y)) in enumerate(cores, start=1):
        position = _tag(1, 0) + _varint(x) + _tag(2, 0) + _varint(y)
        body = _tag(1, 0) + _varint(index)
        if team:
            body += _tag(2, 0) + _varint(team)
        out += _bytes_field(4, body + _bytes_field(3, position))
    return bytes(out)


def _mirror(kind, width, height, x, y):
    if kind == "rot":
        return width - 1 - x, height - 1 - y
    if kind == "mx":
        return width - 1 - x, y
    return x, height - 1 - y


def _core_image(kind, width, height, x, y):
    """Where the 2x2 footprint anchored at (x, y) lands under the symmetry."""
    corners = [_mirror(kind, width, height, x + a, y + b)
               for a in (0, 1) for b in (0, 1)]
    return min(c[0] for c in corners), min(c[1] for c in corners)


def _connected(grid, width, height, start, blocked):
    seen = {start}
    queue = deque([start])
    while queue:
        cx, cy = queue.popleft()
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            spot = cx + dx, cy + dy
            if (spot in seen or not (0 <= spot[0] < width and 0 <= spot[1] < height)
                    or grid[spot[1]][spot[0]] == WALL or spot in blocked):
                continue
            seen.add(spot)
            queue.append(spot)
    return seen


def generate(rng: random.Random, index: int):
    """One playable symmetric map, or None if this draw did not come out legal."""
    kind = ("rot", "mx", "my")[index % 3]
    width = rng.randint(8, 30)
    height = rng.randint(8, 30)
    # A mirror axis needs room on both sides for two distinct Cores.
    if kind == "mx" and width < 10:
        width = 10
    if kind == "my" and height < 10:
        height = 10

    grid = [[EMPTY] * width for _ in range(height)]

    def paint(x, y, value):
        grid[y][x] = value
        mx, my = _mirror(kind, width, height, x, y)
        grid[my][mx] = value

    # Wall structure: a mix of blobs and bars, so both open fields and real
    # corridors occur. Density is drawn per map over the range the pool spans.
    density = rng.uniform(0.0, 0.30)
    budget = int(width * height * density)
    painted = 0
    guard = 0
    while painted < budget and guard < 4000:
        guard += 1
        x, y = rng.randrange(width), rng.randrange(height)
        if rng.random() < 0.5:
            length = rng.randint(2, max(2, min(width, height) // 2))
            horizontal = rng.random() < 0.5
            for step in range(length):
                sx = x + (step if horizontal else 0)
                sy = y + (0 if horizontal else step)
                if 0 <= sx < width and 0 <= sy < height:
                    paint(sx, sy, WALL)
                    painted += 2
        else:
            for dx in range(rng.randint(1, 3)):
                for dy in range(rng.randint(1, 3)):
                    if x + dx < width and y + dy < height:
                        paint(x + dx, y + dy, WALL)
                        painted += 2

    # Cores: an anchor whose 2x2 footprint is clear, and whose image under the
    # symmetry does not overlap it.
    anchors = [(x, y) for x in range(width - 1) for y in range(height - 1)]
    rng.shuffle(anchors)
    core_a = core_b = None
    for x, y in anchors:
        foot_a = {(x + a, y + b) for a in (0, 1) for b in (0, 1)}
        bx, by = _core_image(kind, width, height, x, y)
        foot_b = {(bx + a, by + b) for a in (0, 1) for b in (0, 1)}
        if foot_a & foot_b or not (0 <= bx < width - 1 and 0 <= by < height - 1):
            continue
        if max(abs(x - bx), abs(y - by)) < 5:
            continue
        core_a, core_b = (x, y), (bx, by)
        for tile in foot_a | foot_b:
            grid[tile[1]][tile[0]] = EMPTY
        break
    if core_a is None:
        return None

    foot = {(core_a[0] + a, core_a[1] + b) for a in (0, 1) for b in (0, 1)}
    foot |= {(core_b[0] + a, core_b[1] + b) for a in (0, 1) for b in (0, 1)}

    # Ore, on tiles both sides can reach, in the pool's range of counts.
    for _ in range(rng.randint(2, 12)):
        x, y = rng.randrange(width), rng.randrange(height)
        if (x, y) in foot or grid[y][x] != EMPTY:
            continue
        mx, my = _mirror(kind, width, height, x, y)
        if (mx, my) in foot:
            continue
        paint(x, y, ORE)

    # Playable means one Core can walk to the other.
    start = None
    for dx, dy in ((-1, 0), (2, 0), (0, -1), (0, 2)):
        spot = core_a[0] + dx, core_a[1] + dy
        if (0 <= spot[0] < width and 0 <= spot[1] < height
                and grid[spot[1]][spot[0]] != WALL and spot not in foot):
            start = spot
            break
    if start is None:
        return None
    reach = _connected(grid, width, height, start, foot)
    if not any((core_b[0] + a, core_b[1] + b) in reach
               for a, b in ((-1, 0), (2, 0), (0, -1), (0, 2))):
        return None
    return width, height, grid, [(0, core_a), (1, core_b)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="maps/random")
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    made = 0
    attempts = 0
    while made < args.count and attempts < args.count * 50:
        attempts += 1
        drawn = generate(rng, made)
        if drawn is None:
            continue
        width, height, grid, cores = drawn
        path = out / f"r{made:02d}.map26"
        path.write_bytes(encode(width, height, grid, cores))
        print(f"{path.name}: {width}x{height} cores={[c[1] for c in cores]}")
        made += 1
    return 0 if made == args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())
