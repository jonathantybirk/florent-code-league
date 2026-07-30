#!/usr/bin/env python
"""Build ``bot/atlas.py`` -- the offline map atlas for the 15-map competition pool.

Run from the repo root::

    .\\.venv\\Scripts\\python.exe tools\\build_atlas.py

What this does
--------------
1. Parses every ``maps/*.map26`` (protobuf, schema in ``docs/reference/map26-file-format.md``).
   The varint/field reader is lifted from the working parsers prior agents left in the session
   scratchpad (``parse_maps.py`` / ``mapio.py``) -- same code, tidied and given a docstring.
2. Determines the symmetry of each map **empirically**: it tries every candidate transform and
   keeps only those that map the wall set onto itself, the ore set onto itself, *and* Core A's
   2x2 footprint onto Core B's footprint. Nothing is assumed.
3. Checks that the runtime fingerprint ``(width, height, own_core_pos, team)`` is unique across
   all 15 maps. Aborts loudly if two maps collide (the atlas would be unsafe).
4. Emits a pure-stdlib ``bot/atlas.py`` with literal tuples and a tiny import-time loop.

Verified engine facts this relies on (probe: resign-message channel, all 15 maps x both teams):
  * a Core's ``ct.get_position()`` == the ``.map26`` Core anchor, exactly.
  * ``get_map_width()/get_map_height()`` == the ``.map26`` width/height.
  * the Core footprint is ``{(x,y), (x+1,y), (x,y+1), (x+1,y+1)}`` -- ``get_tile_building_id``
    returns the Core's id at those four offsets and ``None`` at every neighbouring tile.
  * owner 1 == Team A, owner 2 == Team B.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAPS_DIR = REPO / "maps"
OUT_PATH = REPO / "bot" / "atlas.py"

EMPTY, WALL, ORE = 0, 1, 2


# ---------------------------------------------------------------------------
# .map26 parsing (protobuf, no schema published -- hand-rolled wire reader)
# ---------------------------------------------------------------------------

def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7


def fields(data: bytes, offset: int = 0, end: int | None = None) -> list[tuple[int, int, object]]:
    """Decode a protobuf message into ``(field_number, wire_type, value)`` triples."""
    if end is None:
        end = len(data)
    out = []
    while offset < end:
        key, offset = read_varint(data, offset)
        fn, wt = key >> 3, key & 0x07
        if wt == 0:
            v, offset = read_varint(data, offset)
        elif wt == 1:
            v, offset = data[offset:offset + 8], offset + 8
        elif wt == 2:
            ln, offset = read_varint(data, offset)
            v, offset = data[offset:offset + ln], offset + ln
        elif wt == 5:
            v, offset = data[offset:offset + 4], offset + 4
        else:
            raise ValueError(f"unsupported wire type {wt}")
        out.append((fn, wt, v))
    return out


def load_map(path: Path):
    """Return ``(width, height, grid, cores)``.

    ``grid[y][x]`` is 0 EMPTY / 1 WALL / 2 ORE_TITANIUM.
    ``cores`` is ``{1: (x, y), 2: (x, y)}`` keyed by owner (1 = Team A, 2 = Team B).
    """
    data = path.read_bytes()
    w = h = None
    rows: list[bytes] = []
    cores: dict[int, tuple[int, int]] = {}
    for fn, wt, v in fields(data):
        if fn == 1 and wt == 0:
            w = v
        elif fn == 2 and wt == 0:
            h = v
        elif fn == 3 and wt == 2:
            for f2, w2, v2 in fields(v):
                if f2 == 1 and w2 == 2:
                    rows.append(v2)
        elif fn == 4 and wt == 2:
            owner = None
            pos = None
            for f2, w2, v2 in fields(v):
                if f2 == 1 and w2 == 0:
                    owner = v2
                elif f2 == 3 and w2 == 2:
                    px = py = 0
                    for f3, _w3, v3 in fields(v2):
                        if f3 == 1:
                            px = v3
                        elif f3 == 2:
                            py = v3
                    pos = (px, py)
            if owner is None or pos is None:
                raise ValueError(f"{path.name}: malformed Core record")
            if owner in cores:
                raise ValueError(f"{path.name}: duplicate Core owner {owner}")
            cores[owner] = pos
    if w is None or h is None:
        raise ValueError(f"{path.name}: missing width/height")
    if len(rows) != h:
        raise ValueError(f"{path.name}: {len(rows)} rows, height says {h}")
    for y, row in enumerate(rows):
        if len(row) != w:
            raise ValueError(f"{path.name}: row {y} has {len(row)} cols, width says {w}")
        for b in row:
            if b not in (EMPTY, WALL, ORE):
                raise ValueError(f"{path.name}: unknown tile byte {b} in row {y}")
    if set(cores) != {1, 2}:
        raise ValueError(f"{path.name}: expected Core owners {{1, 2}}, got {sorted(cores)}")
    return w, h, [list(r) for r in rows], cores


# ---------------------------------------------------------------------------
# geometry / symmetry
# ---------------------------------------------------------------------------

def core_tiles(anchor: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    """The four tiles a Core occupies. Anchor is the top-left (verified in-engine)."""
    x, y = anchor
    return ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1))


# Candidate transforms, in the preference order used to pick the canonical one.
# Naming convention (documented in the generated module too):
#   mirror_x -> the x coordinate flips (reflection across the vertical centre line)
#   mirror_y -> the y coordinate flips (reflection across the horizontal centre line)
#   diag     -> anti-diagonal reflection, square maps only
TRANSFORMS = (
    ("rot180",   lambda x, y, w, h: (w - 1 - x, h - 1 - y)),
    ("mirror_x", lambda x, y, w, h: (w - 1 - x, y)),
    ("mirror_y", lambda x, y, w, h: (x, h - 1 - y)),
    ("diag",     lambda x, y, w, h: (h - 1 - y, w - 1 - x)),
)
# Tested but never emitted: if a map were symmetric ONLY under this one the atlas format
# would have to grow a second diagonal variant, so the generator aborts instead.
DIAG_MAIN = ("diag_main", lambda x, y, w, h: (y, x))


def valid_transforms(w, h, walls, ore, foot_a, foot_b):
    """Every candidate transform that maps the terrain onto itself and Core A onto Core B."""
    ok = []
    for name, fn in TRANSFORMS + (DIAG_MAIN,):
        if name in ("diag", "diag_main") and w != h:
            continue
        if frozenset(fn(x, y, w, h) for (x, y) in walls) != walls:
            continue
        if frozenset(fn(x, y, w, h) for (x, y) in ore) != ore:
            continue
        if frozenset(fn(x, y, w, h) for (x, y) in foot_a) != foot_b:
            continue
        ok.append(name)
    return ok


# ---------------------------------------------------------------------------
# emit
# ---------------------------------------------------------------------------

def fmt_points(points, indent: int, width: int = 96) -> str:
    """Render a sequence of (x, y) as a wrapped Python tuple literal."""
    if not points:
        return "()"
    pad = " " * indent
    parts = ["(%d,%d)," % (x, y) for (x, y) in points]
    lines: list[str] = []
    cur = ""
    for part in parts:
        if cur and len(pad) + len(cur) + len(part) > width:
            lines.append(pad + cur)
            cur = part
        else:
            cur += part
    if cur:
        lines.append(pad + cur)
    body = "\n".join(lines)
    return "(\n" + body + "\n" + " " * (indent - 2) + ")"


HEADER = '''"""Offline map atlas for the Florent Code League 2026 15-map pool.

GENERATED by ``tools/build_atlas.py`` from ``maps/*.map26`` -- DO NOT EDIT BY HAND.

Pure stdlib (no imports at all), safe inside the bot sandbox and cheap to import in every
per-unit sub-interpreter.

Public interface
----------------
``identify(width, height, core_pos, team)``
    Return the record dict for this game, or ``None`` when the fingerprint is unrecognised.
    Never raises. ``core_pos`` is OUR Core's reported ``Position`` (any (x, y) sequence);
    ``team`` is ``'a'`` or ``'b'`` (a ``Team`` enum or ``'Team.A'`` also works).

``mirror(record, pos)``
    Map a position to its counterpart in the enemy half, using that map's symmetry.

``by_name(name, team)`` / ``MAP_NAMES``
    Offline lookups for tools and tests.

Record keys
-----------
``name``            str
``width``           int
``height``          int
``walls``           frozenset of (x, y) -- every WALL tile on the map
``ore``             tuple of (x, y)     -- every ORE_TITANIUM tile, row-major sorted
``own_core``        (x, y)              -- OUR Core anchor, resolved for the calling team
``enemy_core``      (x, y)              -- THEIR Core anchor
``own_core_tiles``  tuple of 4 (x, y)   -- the 2x2 footprint our Core occupies
``enemy_core_tiles``tuple of 4 (x, y)
``symmetry``        str -- one of 'rot180', 'mirror_x', 'mirror_y', 'diag'

Symmetry naming: ``mirror_x`` flips the x coordinate (reflection across the vertical centre
line), ``mirror_y`` flips y, ``rot180`` flips both, ``diag`` is the anti-diagonal reflection
``(x, y) -> (h-1-y, w-1-x)`` (square maps only). Each map's symmetry was determined
empirically -- the transform provably maps walls onto walls, ore onto ore and Core A's
footprint onto Core B's.

Engine facts this rests on (all probe-verified on 15/15 maps, both teams):
a Core's ``get_position()`` is the map-file anchor and is the TOP-LEFT of its 2x2 footprint;
``get_map_width()/get_map_height()`` match the file; owner 1 == Team A, owner 2 == Team B.
"""

'''


def build_module(records) -> str:
    out = [HEADER]
    out.append("# name, w, h, walls, ore, coreA anchor, coreB anchor, symmetry\n")
    out.append("_DATA = (\n")
    for r in records:
        out.append('    ("%s", %d, %d,\n' % (r["name"], r["width"], r["height"]))
        out.append("     " + fmt_points(r["walls"], 8) + ",\n")
        out.append("     " + fmt_points(r["ore"], 8) + ",\n")
        out.append('     (%d,%d), (%d,%d), "%s"),\n'
                   % (r["core_a"][0], r["core_a"][1], r["core_b"][0], r["core_b"][1],
                      r["symmetry"]))
    out.append(")\n\n")
    out.append('''MAP_NAMES = tuple(_d[0] for _d in _DATA)

# fingerprint (width, height, core_x, core_y, team) -> fully resolved record.
# Verified unique across all 15 maps x both teams, so this is a single dict hit.
_BY_FP = {}
_BY_NAME = {}

for _name, _w, _h, _walls, _ore, _ca, _cb, _sym in _DATA:
    _wf = frozenset(_walls)
    _ta = (_ca, (_ca[0] + 1, _ca[1]), (_ca[0], _ca[1] + 1), (_ca[0] + 1, _ca[1] + 1))
    _tb = (_cb, (_cb[0] + 1, _cb[1]), (_cb[0], _cb[1] + 1), (_cb[0] + 1, _cb[1] + 1))
    _ra = {"name": _name, "width": _w, "height": _h, "walls": _wf, "ore": _ore,
           "own_core": _ca, "enemy_core": _cb,
           "own_core_tiles": _ta, "enemy_core_tiles": _tb, "symmetry": _sym}
    _rb = {"name": _name, "width": _w, "height": _h, "walls": _wf, "ore": _ore,
           "own_core": _cb, "enemy_core": _ca,
           "own_core_tiles": _tb, "enemy_core_tiles": _ta, "symmetry": _sym}
    _BY_FP[(_w, _h, _ca[0], _ca[1], "a")] = _ra
    _BY_FP[(_w, _h, _cb[0], _cb[1], "b")] = _rb
    _BY_NAME[_name] = (_ra, _rb)

del _name, _w, _h, _walls, _ore, _ca, _cb, _sym, _wf, _ta, _tb, _ra, _rb


def identify(width, height, core_pos, team):
    """Return the map record dict for this game, or None if unknown.

    ``core_pos`` is OUR core's reported Position (x, y). ``team`` is 'a' or 'b'.
    O(1): one tuple build plus one dict lookup. Never raises -- callers get None and
    fall back to their no-atlas path.
    """
    try:
        t = team if type(team) is str else str(team)
        t = t.strip().lower()
        if t.endswith("a"):
            t = "a"
        elif t.endswith("b"):
            t = "b"
        else:
            return None
        return _BY_FP.get((int(width), int(height), int(core_pos[0]), int(core_pos[1]), t))
    except Exception:
        return None


def mirror(record, pos):
    """Map ``pos`` to the matching tile in the other half, per this map's symmetry.

    Returns a plain ``(x, y)`` tuple. Applying it twice is the identity.
    """
    try:
        x = int(pos[0])
        y = int(pos[1])
        w = record["width"]
        h = record["height"]
        s = record["symmetry"]
        if s == "rot180":
            return (w - 1 - x, h - 1 - y)
        if s == "mirror_x":
            return (w - 1 - x, y)
        if s == "mirror_y":
            return (x, h - 1 - y)
        return (h - 1 - y, w - 1 - x)
    except Exception:
        return None


def by_name(name, team):
    """Offline lookup by map name (for tools and tests). None if unknown."""
    pair = _BY_NAME.get(name)
    if pair is None:
        return None
    return pair[0] if str(team).strip().lower().endswith("a") else pair[1]
''')
    return "".join(out)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    paths = sorted(MAPS_DIR.glob("*.map26"))
    if not paths:
        print(f"no maps found in {MAPS_DIR}", file=sys.stderr)
        return 1

    records = []
    for path in paths:
        w, h, grid, cores = load_map(path)
        walls = frozenset((x, y) for y in range(h) for x in range(w) if grid[y][x] == WALL)
        ore = frozenset((x, y) for y in range(h) for x in range(w) if grid[y][x] == ORE)
        ca, cb = cores[1], cores[2]
        foot_a, foot_b = frozenset(core_tiles(ca)), frozenset(core_tiles(cb))
        if foot_a & foot_b:
            raise ValueError(f"{path.name}: Core footprints overlap")
        for tile in foot_a | foot_b:
            x, y = tile
            if not (0 <= x < w and 0 <= y < h):
                raise ValueError(f"{path.name}: Core footprint tile {tile} off-map")
            if grid[y][x] != EMPTY:
                raise ValueError(f"{path.name}: Core footprint tile {tile} is not EMPTY")

        ok = valid_transforms(w, h, walls, ore, foot_a, foot_b)
        emittable = [t for t in ok if t != "diag_main"]
        if not emittable:
            print(f"FATAL {path.name}: no candidate transform maps the terrain onto itself "
                  f"(diag_main only: {ok})", file=sys.stderr)
            return 2
        sym = emittable[0]  # TRANSFORMS is already in preference order

        records.append(dict(
            name=path.stem, width=w, height=h,
            walls=sorted(walls, key=lambda p: (p[1], p[0])),
            ore=sorted(ore, key=lambda p: (p[1], p[0])),
            core_a=ca, core_b=cb, symmetry=sym, all_sym=ok,
        ))

    # ---- fingerprint uniqueness -------------------------------------------------
    seen: dict[tuple, list[str]] = {}
    for r in records:
        for team, anchor in (("a", r["core_a"]), ("b", r["core_b"])):
            key = (r["width"], r["height"], anchor[0], anchor[1], team)
            seen.setdefault(key, []).append(f"{r['name']}/{team}")
    collisions = {k: v for k, v in seen.items() if len(v) > 1}

    # Also report the weaker fingerprint that ignores `team`, since a caller could in
    # principle key on (w, h, core_pos) alone.
    seen_noteam: dict[tuple, list[str]] = {}
    for r in records:
        for team, anchor in (("a", r["core_a"]), ("b", r["core_b"])):
            seen_noteam.setdefault((r["width"], r["height"], anchor), []).append(
                f"{r['name']}/{team}")
    collisions_noteam = {k: v for k, v in seen_noteam.items() if len(v) > 1}

    print("=== map atlas ===")
    print(f"{'map':<11} {'size':>7} {'walls':>6} {'ore':>4} {'coreA':>9} {'coreB':>9} "
          f"{'symmetry':<9} all-valid-transforms")
    for r in records:
        print(f"{r['name']:<11} {r['width']:>3}x{r['height']:<3} {len(r['walls']):>6} "
              f"{len(r['ore']):>4} {str(r['core_a']):>9} {str(r['core_b']):>9} "
              f"{r['symmetry']:<9} {','.join(r['all_sym'])}")

    print()
    if collisions:
        print("FATAL: fingerprint (width, height, own_core_pos, team) is NOT unique:")
        for k, v in collisions.items():
            print(f"  {k} -> {v}")
        print("  extend the fingerprint before shipping this atlas")
        return 3
    print("fingerprint (width, height, own_core_pos, team): UNIQUE across all "
          f"{len(records)} maps x 2 teams ({len(seen)} distinct keys)")
    if collisions_noteam:
        print("note: dropping `team` from the key WOULD collide:")
        for k, v in collisions_noteam.items():
            print(f"  {k} -> {v}")
    else:
        print("      it stays unique even without `team` in the key "
              f"({len(seen_noteam)} distinct keys) -- team is only used to resolve "
              "own/enemy")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = build_module(records)
    OUT_PATH.write_text(text, encoding="utf-8", newline="\n")
    size = OUT_PATH.stat().st_size
    print(f"\nwrote {OUT_PATH} ({size} bytes, {text.count(chr(10)) + 1} lines)")

    # ---- import cost -------------------------------------------------------------
    sys.dont_write_bytecode = True  # a stray __pycache__ makes the engine run the bot INERT
    src = OUT_PATH.read_text(encoding="utf-8")
    code = compile(src, str(OUT_PATH), "exec")
    times = []
    for _ in range(9):
        ns: dict = {}
        t0 = time.perf_counter()
        exec(code, ns)
        times.append((time.perf_counter() - t0) * 1000.0)
    times.sort()
    print(f"import (exec of compiled module body): median {times[len(times) // 2]:.3f} ms, "
          f"min {times[0]:.3f} ms, max {times[-1]:.3f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
