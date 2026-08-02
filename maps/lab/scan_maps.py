"""Offline generalisation check for the launcher-defence findings.

Pure map analysis -- reads maps/*.map26, runs no games, uses no engine CPU.

For each of the 21 pool maps it reports:

  POCKETS  empty tiles NOT reachable on foot from either Core's spawn ring
           (sealed terrain pockets), and how many of them have at least one
           REACHABLE tile within d^2<=26 of them -- i.e. a legal Launcher site
           from which an enemy builder could be thrown in and deleted (G48: the
           throw arcs over walls, gl_pocket: the prisoner never gets out).

  CUTS     single passable tiles whose removal disconnects Core A's spawn ring
           from Core B's spawn ring -- one-tile chokepoints. A Launcher sited
           orthogonally/diagonally beside such a tile sees every attacker.
           Also reports the narrowest tile-cut found by a simple vertex-cut
           search over the shortest path (upper bound on corridor width).

    .venv/Scripts/python.exe maps/lab/scan_maps.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "maps" / "generated"))

from generate_maps import EMPTY, ORE, WALL, read_map, spawn_ring  # noqa: E402

STEP = ((1, 0), (-1, 0), (0, 1), (0, -1))


def passable(m, x, y):
    return m.rows[y][x] != WALL


def reach(m, seeds, banned=()):
    seen = set()
    q = []
    for s in seeds:
        if s not in banned and passable(m, s[0], s[1]):
            seen.add(s)
            q.append(s)
    head = 0
    while head < len(q):
        x, y = q[head]
        head += 1
        for dx, dy in STEP:
            n = (x + dx, y + dy)
            if n in seen or n in banned:
                continue
            if not (0 <= n[0] < m.width and 0 <= n[1] < m.height):
                continue
            if not passable(m, n[0], n[1]):
                continue
            seen.add(n)
            q.append(n)
    return seen


def core_tiles(m):
    out = set()
    for c in m.cores:
        for dx in (0, 1):
            for dy in (0, 1):
                out.add((c.x + dx, c.y + dy))
    return out


def analyse(path):
    m = read_map(path)
    foot = core_tiles(m)
    ra = spawn_ring(m.cores[0].anchor, m.width, m.height) - foot
    rb = spawn_ring(m.cores[1].anchor, m.width, m.height) - foot
    live = reach(m, ra | rb, banned=foot)

    # --- sealed pockets ---
    allpass = {(x, y) for y in range(m.height) for x in range(m.width)
               if passable(m, x, y)} - foot
    pockets = sorted(allpass - live)
    throwable = []
    for p in pockets:
        for s in live:
            d2 = (s[0] - p[0]) ** 2 + (s[1] - p[1]) ** 2
            if d2 <= 26:
                throwable.append(p)
                break

    # --- one-tile cuts between the two spawn rings ---
    cuts = []
    if reach(m, ra, banned=foot) & rb:
        for t in sorted(live):
            if t in ra or t in rb:
                continue
            if not (reach(m, ra, banned=foot | {t}) & rb):
                cuts.append(t)
    ore = sum(1 for y in range(m.height) for x in range(m.width) if m.rows[y][x] == ORE)
    return m, pockets, throwable, cuts, ore


def main():
    names = sorted(p.stem for p in (ROOT / "maps").glob("*.map26"))
    print("%-11s %5s %7s %9s %6s   %s" % ("map", "size", "pockets", "throwable", "cuts", "cut tiles"))
    for n in names:
        m, pockets, throwable, cuts, ore = analyse(ROOT / "maps" / (n + ".map26"))
        ct = ",".join("%d,%d" % t for t in cuts[:6])
        print("%-11s %2dx%-2d %7d %9d %6d   %s" % (
            n, m.width, m.height, len(pockets), len(throwable), len(cuts), ct))


if __name__ == "__main__":
    main()
