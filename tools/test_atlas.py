#!/usr/bin/env python
"""Verify ``bot/atlas.py`` against the actual ``maps/*.map26`` files.

Run from the repo root::

    .\\.venv\\Scripts\\python.exe tools\\test_atlas.py

Checks, per map, for BOTH teams:
  * ``identify(w, h, own_core_pos, team)`` returns that map's record and nothing else
  * the record's walls / ore / core anchors / core footprints match the map file byte for byte
  * the claimed symmetry really maps the wall set onto itself and the ore set onto itself
  * the claimed symmetry maps our Core's footprint exactly onto the recorded enemy footprint,
    i.e. ``enemy_core`` is where the symmetry says it is
Plus, globally: fingerprint uniqueness, ``identify`` returning None (never raising) on junk,
``mirror`` being an involution, the module importing no third-party code, and the module
surviving the engine's AST validator rules.

Sets ``sys.dont_write_bytecode`` and asserts no ``bot/__pycache__`` is left behind -- a stray
``__pycache__`` in a bot directory makes the engine silently run the bot INERT.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # MUST come before importing anything from bot/

import ast
import importlib.util
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import build_atlas as B  # noqa: E402  (the generator doubles as the reference parser)

ATLAS_PATH = REPO / "bot" / "atlas.py"

FAILURES: list[str] = []
CHECKS = 0


def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        FAILURES.append(msg)
    return bool(cond)


def load_atlas():
    spec = importlib.util.spec_from_file_location("_atlas_under_test", ATLAS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TRANSFORM = {
    "rot180":   lambda x, y, w, h: (w - 1 - x, h - 1 - y),
    "mirror_x": lambda x, y, w, h: (w - 1 - x, y),
    "mirror_y": lambda x, y, w, h: (x, h - 1 - y),
    "diag":     lambda x, y, w, h: (h - 1 - y, w - 1 - x),
}

RECORD_KEYS = {"name", "width", "height", "walls", "ore", "own_core", "enemy_core",
               "own_core_tiles", "enemy_core_tiles", "symmetry"}


def main() -> int:
    global CHECKS
    atlas = load_atlas()

    paths = sorted((REPO / "maps").glob("*.map26"))
    check(len(paths) == 15, f"expected 15 maps in maps/, found {len(paths)}")

    truth = {}
    for path in paths:
        w, h, grid, cores = B.load_map(path)
        truth[path.stem] = dict(
            w=w, h=h,
            walls=frozenset((x, y) for y in range(h) for x in range(w) if grid[y][x] == B.WALL),
            ore=frozenset((x, y) for y in range(h) for x in range(w) if grid[y][x] == B.ORE),
            core_a=cores[1], core_b=cores[2],
        )

    print(f"{'map':<11} {'size':>7} {'team':<5} {'sym':<9} {'own_core':>9} {'enemy':>9} "
          f"{'walls':>6} {'ore':>4}  result")

    # ---- per map, per team -------------------------------------------------------
    for name in sorted(truth):
        t = truth[name]
        for team, own, enemy in (("a", t["core_a"], t["core_b"]),
                                 ("b", t["core_b"], t["core_a"])):
            rec = atlas.identify(t["w"], t["h"], own, team)
            if not check(rec is not None, f"{name}/{team}: identify() returned None"):
                print(f"{name:<11} {t['w']:>3}x{t['h']:<3} {team:<5} {'-':<9} {str(own):>9} "
                      f"{'-':>9} {'-':>6} {'-':>4}  FAIL (None)")
                continue

            check(set(rec) == RECORD_KEYS,
                  f"{name}/{team}: record keys {sorted(set(rec) ^ RECORD_KEYS)} unexpected")
            check(rec["name"] == name, f"{name}/{team}: identified as {rec['name']!r}")
            check(rec["width"] == t["w"] and rec["height"] == t["h"],
                  f"{name}/{team}: size {rec['width']}x{rec['height']} != {t['w']}x{t['h']}")

            # terrain matches the map file exactly
            check(isinstance(rec["walls"], frozenset),
                  f"{name}/{team}: 'walls' is {type(rec['walls']).__name__}, want frozenset")
            check(rec["walls"] == t["walls"], f"{name}/{team}: wall set differs from map file")
            check(isinstance(rec["ore"], tuple),
                  f"{name}/{team}: 'ore' is {type(rec['ore']).__name__}, want tuple")
            check(len(rec["ore"]) == len(set(rec["ore"])), f"{name}/{team}: duplicate ore tiles")
            check(frozenset(rec["ore"]) == t["ore"], f"{name}/{team}: ore set differs from file")
            check(not (t["walls"] & t["ore"]), f"{name}/{team}: a tile is both wall and ore")

            # cores resolved for the calling team
            check(tuple(rec["own_core"]) == tuple(own),
                  f"{name}/{team}: own_core {rec['own_core']} != {own}")
            check(tuple(rec["enemy_core"]) == tuple(enemy),
                  f"{name}/{team}: enemy_core {rec['enemy_core']} != {enemy}")
            check(tuple(rec["own_core_tiles"]) == B.core_tiles(own),
                  f"{name}/{team}: own_core_tiles {rec['own_core_tiles']} wrong")
            check(tuple(rec["enemy_core_tiles"]) == B.core_tiles(enemy),
                  f"{name}/{team}: enemy_core_tiles {rec['enemy_core_tiles']} wrong")
            check(len(rec["own_core_tiles"]) == 4 and len(rec["enemy_core_tiles"]) == 4,
                  f"{name}/{team}: core footprint is not 4 tiles")
            # footprints are on-map, empty, and disjoint from terrain
            for tile in tuple(rec["own_core_tiles"]) + tuple(rec["enemy_core_tiles"]):
                check(0 <= tile[0] < t["w"] and 0 <= tile[1] < t["h"],
                      f"{name}/{team}: core tile {tile} off-map")
                check(tile not in t["walls"] and tile not in t["ore"],
                      f"{name}/{team}: core tile {tile} sits on wall/ore")

            # ---- the claimed symmetry is real ------------------------------------
            sym = rec["symmetry"]
            if check(sym in TRANSFORM, f"{name}/{team}: unknown symmetry {sym!r}"):
                fn = TRANSFORM[sym]
                w, h = t["w"], t["h"]
                mapped_walls = frozenset(fn(x, y, w, h) for (x, y) in rec["walls"])
                mapped_ore = frozenset(fn(x, y, w, h) for (x, y) in rec["ore"])
                check(mapped_walls == rec["walls"],
                      f"{name}/{team}: {sym} does NOT map the wall set onto itself "
                      f"({len(mapped_walls - rec['walls'])} tiles land off-set)")
                check(mapped_ore == frozenset(rec["ore"]),
                      f"{name}/{team}: {sym} does NOT map the ore set onto itself "
                      f"({len(mapped_ore - frozenset(rec['ore']))} tiles land off-set)")
                # empties too (walls+ore self-mapping implies it, assert anyway)
                allt = frozenset((x, y) for y in range(h) for x in range(w))
                check(frozenset(fn(x, y, w, h) for (x, y) in allt) == allt,
                      f"{name}/{team}: {sym} is not a bijection of the board")
                # enemy_core is where the symmetry says it is
                mapped_foot = frozenset(fn(x, y, w, h) for (x, y) in rec["own_core_tiles"])
                check(mapped_foot == frozenset(rec["enemy_core_tiles"]),
                      f"{name}/{team}: {sym} maps our footprint to {sorted(mapped_foot)}, "
                      f"but enemy_core_tiles is {sorted(rec['enemy_core_tiles'])}")
                # and mirror() agrees with the transform, and is an involution
                for p in [rec["own_core"], (0, 0), (w - 1, h - 1), (w // 3, h // 2)]:
                    m = atlas.mirror(rec, p)
                    check(m == fn(p[0], p[1], w, h),
                          f"{name}/{team}: mirror({p}) = {m}, transform says "
                          f"{fn(p[0], p[1], w, h)}")
                    check(atlas.mirror(rec, m) == tuple(p),
                          f"{name}/{team}: mirror is not an involution at {p}")
                check(atlas.mirror(rec, rec["own_core_tiles"][0]) in rec["enemy_core_tiles"],
                      f"{name}/{team}: mirror of our anchor is not in the enemy footprint")

            # by_name agrees with identify
            check(atlas.by_name(name, team) is rec, f"{name}/{team}: by_name() disagrees")

            ok = not FAILURES or not any(f.startswith(f"{name}/{team}:") for f in FAILURES)
            print(f"{name:<11} {t['w']:>3}x{t['h']:<3} {team:<5} {rec['symmetry']:<9} "
                  f"{str(rec['own_core']):>9} {str(rec['enemy_core']):>9} "
                  f"{len(rec['walls']):>6} {len(rec['ore']):>4}  {'ok' if ok else 'FAIL'}")

    # ---- no map answers to another map's fingerprint ------------------------------
    fps = {}
    for name in sorted(truth):
        t = truth[name]
        for team, own in (("a", t["core_a"]), ("b", t["core_b"])):
            fps.setdefault((t["w"], t["h"], own, team), []).append(name)
    check(all(len(v) == 1 for v in fps.values()),
          f"fingerprint collision: {[(k, v) for k, v in fps.items() if len(v) > 1]}")
    check(len(fps) == 30, f"expected 30 distinct fingerprints, got {len(fps)}")
    check(len(atlas.MAP_NAMES) == 15 and set(atlas.MAP_NAMES) == set(truth),
          f"MAP_NAMES mismatch: {atlas.MAP_NAMES}")

    # ---- unknown fingerprints return None, never raise ----------------------------
    bad_inputs = [
        (999, 999, (1, 1), "a"), (18, 18, (0, 0), "a"), (18, 18, (2, 14), "z"),
        (12, 12, (1, 8), "b"),          # right map+pos, WRONG team -> unknown
        (18, 18, (14, 2), "a"),         # right map, enemy anchor as own -> unknown
        (-1, -1, (-5, -5), "a"), (0, 0, (0, 0), "b"),
        (None, None, None, None), ("18", "18", ("2", "14"), "A"),
        (18.0, 18.0, (2.0, 14.0), "a"), (18, 18, (2, 14), None), (18, 18, "xy", "a"),
        (18, 18, (2,), "a"), (18, 18, (2, 14, 9), "a"), (18, 18, object(), "a"),
    ]
    # these three are junk-shaped but still legitimately resolve atoll: identify() only
    # reads core_pos[0]/[1] and coerces with int(), and 'A'/'Team.A' normalise to 'a'
    expect_hit = {(18, 18, (2, 14), "a"), ("18", "18", ("2", "14"), "A"),
                  (18.0, 18.0, (2.0, 14.0), "a"), (18, 18, (2, 14, 9), "a")}
    for args in bad_inputs:
        try:
            got = atlas.identify(*args)
        except Exception as exc:  # noqa: BLE001
            FAILURES.append(f"identify{args!r} raised {type(exc).__name__}: {exc}")
            CHECKS += 1
            continue
        want_hit = tuple(args) in expect_hit or args in expect_hit
        if want_hit:
            check(got is not None and got["name"] == "atoll",
                  f"identify{args!r} should still resolve atoll, got {got}")
        else:
            check(got is None, f"identify{args!r} should be None, got "
                               f"{got['name'] if got else got}")
    check(atlas.mirror({"width": 1, "height": 1, "symmetry": "nope"}, None) is None,
          "mirror() should return None on junk, not raise")

    # ---- works with the real engine types ----------------------------------------
    try:
        from fcode import Position, Team
        t = truth["atoll"]
        r1 = atlas.identify(18, 18, Position(*t["core_a"]), "a")
        check(r1 is not None and r1["name"] == "atoll", "identify() failed on a Position")
        r2 = atlas.identify(18, 18, Position(*t["core_b"]), Team.B)
        check(r2 is not None and r2["name"] == "atoll" and r2["own_core"] == t["core_b"],
              "identify() failed on a Team enum")
    except ImportError:
        print("(fcode not importable -- skipped Position/Team interop check)")

    # ---- shippability: pure stdlib + engine AST validator -------------------------
    src = ATLAS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    check(not imports, f"atlas.py must import nothing, found {len(imports)} import(s)")
    check(not any(isinstance(n, ast.Try) and n.finalbody for n in ast.walk(tree)),
          "atlas.py uses finally: -- the engine AST validator rejects it")
    allowed = {"Exception", "GameError"}
    for n in ast.walk(tree):
        if isinstance(n, ast.ExceptHandler):
            check(n.type is not None, "atlas.py uses a bare except: -- validator rejects it")
            check(isinstance(n.type, ast.Name), "atlas.py uses a non-Name exception type")
            if isinstance(n.type, ast.Name):
                check(n.type.id in allowed,
                      f"atlas.py catches {n.type.id!r}, not in {sorted(allowed)}")
    for fn_name in ("identify", "mirror", "by_name"):
        check(any(isinstance(n, ast.FunctionDef) and n.name == fn_name
                  for n in tree.body), f"atlas.py is missing top-level {fn_name}()")

    # ---- cost --------------------------------------------------------------------
    code = compile(src, str(ATLAS_PATH), "exec")
    times = []
    for _ in range(11):
        ns: dict = {}
        t0 = time.perf_counter()
        exec(code, ns)
        times.append((time.perf_counter() - t0) * 1000.0)
    times.sort()
    med = times[len(times) // 2]

    call = []
    t = truth["atoll"]
    for _ in range(7):
        t0 = time.perf_counter()
        for _ in range(1000):
            atlas.identify(18, 18, t["core_a"], "a")
        call.append((time.perf_counter() - t0) * 1000.0)
    call.sort()

    # importing atlas.py must not leave a .pyc behind (G30: a stray __pycache__ inside a
    # bot directory makes the engine silently run the whole bot INERT)
    pyc = REPO / "bot" / "__pycache__"
    stray = sorted(p.name for p in pyc.glob("*.pyc")) if pyc.exists() else []
    check(not any(s.startswith("atlas.") for s in stray),
          f"loading atlas.py left {[s for s in stray if s.startswith('atlas.')]} in {pyc}")

    print()
    if stray:
        print("!! WARNING: bot/__pycache__ exists and holds " + ", ".join(stray))
        print("!! G30: a stray __pycache__ in a bot directory makes the engine run the bot")
        print("!! INERT. Delete bot/__pycache__ before any match or submission.")
        print()
    print(f"module size          : {ATLAS_PATH.stat().st_size} bytes, "
          f"{src.count(chr(10)) + 1} lines")
    print(f"import (module body) : median {med:.3f} ms  (min {times[0]:.3f}, "
          f"max {times[-1]:.3f})")
    per1k = call[len(call) // 2]
    print(f"identify() call      : {per1k:.4f} ms per 1000 calls ({per1k:.4f} us each)")
    print(f"maps                 : {len(truth)}   fingerprints: {len(fps)} (all unique)")
    print(f"checks run           : {CHECKS}")
    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}):")
        for f in FAILURES:
            print("  -", f)
        return 1
    print(f"ALL {CHECKS} CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
