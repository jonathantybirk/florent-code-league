"""Check .map26 files against the rules the specification actually states."""
import pathlib
import sys

sys.path.insert(0, "analysis/econ")
from maplib import _varint, read_map  # noqa: E402

EMPTY, WALL, ORE = 0, 1, 2


def cores(path):
    data = pathlib.Path(path).read_bytes()
    out, i = [], 0
    while i < len(data):
        key, i = _varint(data, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            _, i = _varint(data, i)
        elif wire == 2:
            length, i = _varint(data, i)
            payload, i = data[i:i + length], i + length
            if field == 4:
                d, j = {}, 0
                while j < len(payload):
                    k, j = _varint(payload, j)
                    if k & 7 == 0:
                        d[k >> 3], j = _varint(payload, j)
                    else:
                        n, j = _varint(payload, j)
                        d[k >> 3], j = payload[j:j + n], j + n
                pos, sub, j = {}, d.get(3, b""), 0
                while j < len(sub):
                    k, j = _varint(sub, j)
                    v, j = _varint(sub, j)
                    pos[k >> 3] = v
                out.append((d.get(1, 1), (pos.get(1, 0), pos.get(2, 0))))
        else:
            raise ValueError(wire)
    return out


def transform(w, h, tile, index):
    x, y = tile
    return ((w - 1 - x, h - 1 - y) if index == 0
            else (w - 1 - x, y) if index == 1 else (x, h - 1 - y))


def check(path):
    problems = []
    w, h, rows = read_map(path)
    if not (8 <= w <= 30 and 8 <= h <= 30):
        problems.append(f"size {w}x{h} outside 8..30")
    if any(c not in (EMPTY, WALL, ORE) for row in rows for c in row):
        problems.append("tile value outside {empty, wall, ore}")

    kinds = [name for index, name in enumerate(("rot180", "mirror-x", "mirror-y"))
             if all(rows[y][x] == rows[transform(w, h, (x, y), index)[1]]
                                     [transform(w, h, (x, y), index)[0]]
                    for y in range(h) for x in range(w))]
    if not kinds:
        problems.append("terrain is not symmetric under any allowed transform")

    found = cores(path)
    if len(found) != 2:
        problems.append(f"{len(found)} cores, expected 2")
    else:
        owners = sorted(o for o, _ in found)
        if owners != [1, 2]:
            problems.append(f"core owners {owners}, expected [1, 2]")
        foot = []
        for _, (cx, cy) in found:
            block = [(cx + dx, cy + dy) for dx in (0, 1) for dy in (0, 1)]
            foot.append(set(block))
            for x, y in block:
                if not (0 <= x < w and 0 <= y < h):
                    problems.append(f"core footprint {(cx, cy)} off-map")
                elif rows[y][x] != EMPTY:
                    problems.append(f"core footprint tile {(x, y)} not empty")
        if len(foot) == 2 and foot[0] & foot[1]:
            problems.append("core footprints overlap")
        # The second Core must be the counterpart of the first under a
        # symmetry the terrain also obeys.
        if len(found) == 2 and kinds:
            a, b = found[0][1], found[1][1]
            ok = False
            for index, name in enumerate(("rot180", "mirror-x", "mirror-y")):
                if name not in kinds:
                    continue
                block = {transform(w, h, (a[0] + dx, a[1] + dy), index)
                         for dx in (0, 1) for dy in (0, 1)}
                if block == {(b[0] + dx, b[1] + dy)
                             for dx in (0, 1) for dy in (0, 1)}:
                    ok = True
            if not ok:
                problems.append(f"cores {a} and {b} not paired by any symmetry "
                                f"the terrain obeys ({','.join(kinds)})")
    return kinds, problems


def main():
    targets = sorted(pathlib.Path(sys.argv[1]).glob("*.map26"))
    bad = 0
    for path in targets:
        kinds, problems = check(path)
        if problems:
            bad += 1
            print(f"FAIL {path.name}  [{','.join(kinds) or 'asymmetric'}]")
            for problem in problems:
                print(f"       {problem}")
    print(f"\n{len(targets) - bad}/{len(targets)} maps in {sys.argv[1]} "
          f"satisfy the stated rules")


if __name__ == "__main__":
    main()
