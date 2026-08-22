"""What is the FASTEST the ring could possibly have gone up, and how late was it really?

`ringtime.py` says the ring took N rounds. That is a number without a scale: N is only bad if some
smaller N was available, and on a map full of walls it may not have been. This computes the floor
by search, so "late" becomes a quantity per map rather than a feeling.

THE SEARCH
  State  (position, turrets placed).  Moving to a passable neighbour costs 1 round; building on an
  orthogonally adjacent firing spot costs 1 round and raises the count. Both are exactly what the
  engine charges -- a Builder's move and its action are mutually exclusive in a round.
  Dijkstra from the Builder's spawn tile to (anywhere, k). ~900 x k states, milliseconds.

A turret OCCUPIES the tile it is built on, so each build must consume a DIFFERENT neighbour. The
first version of this tool ignored that and happily returned a 12-round plan for helheim reading
BUILD (10,5) x4 -- four Sentinels stacked on one square. A floor that prescribes something
physically impossible is not a bound, it is a bug that flatters the search. The state therefore
carries which of the current tile's four neighbours have been used.

It remains a FLOOR: it still assumes every firing spot is free of enemy buildings, and it lets the
Builder walk over ground where it earlier placed a turret. Both are optimistic, which is the right
direction for a lower bound -- but the gap it reports is now at least achievable in principle.

Only games that actually completed k turrets are comparable, and the denominator is printed --
`ringtime.py` originally called the LAST turret the fourth, so a map that built two reported the
best span in the table. A partial ring is not a fast ring.

Usage: python tools/ringfloor.py [bot] [opponent] [k]
"""

import os
import pathlib
import shutil
import sys

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import fcode                                    # noqa: E402
from fcode.fcode_engine import run_game         # noqa: E402
from diag.replay import load_replay             # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
MAPS = sorted(p.stem for p in (ROOT / "maps").glob("*.map26"))
CARD = ((0, -1), (0, 1), (1, 0), (-1, 0))
RAYS = ((0, -1), (0, 1), (1, 0), (-1, 0), (1, -1), (-1, -1), (1, 1), (-1, 1))
MAX_RANGE_SQ = 32


def scrub():
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" not in pc.parts:
            shutil.rmtree(pc, ignore_errors=True)


def firing_spots(foe, walls, w, h):
    """Every tile a Sentinel could stand on and still put the Core on its ray."""
    foot = {(foe[0], foe[1]), (foe[0] + 1, foe[1]),
            (foe[0], foe[1] + 1), (foe[0] + 1, foe[1] + 1)}
    spots = set()
    for target in foot:
        for dx, dy in RAYS:
            span = 1 if (dx == 0 or dy == 0) else 2
            k = 1
            while k * k * span <= MAX_RANGE_SQ:
                key = (target[0] - dx * k, target[1] - dy * k)
                k += 1
                if not (0 <= key[0] < w and 0 <= key[1] < h):
                    continue
                if key in walls or key in foot:
                    continue
                spots.add(key)
    return spots, foot


def floor_rounds(start, spots, walls, foot, w, h, k):
    """Fewest rounds from `start` to k turrets. Dijkstra over (pos, placed, used-neighbour mask).

    The mask is which of THIS tile's four neighbours already hold a turret, so a tile can supply at
    most as many turrets as it has distinct firing-spot neighbours. It resets on a move, which is
    the remaining optimism: a turret placed earlier elsewhere is not re-blocked.
    """
    import heapq

    def passable(p):
        return (0 <= p[0] < w and 0 <= p[1] < h and p not in walls and p not in foot)

    best = {(start, 0, 0): 0}
    pq = [(0, start, 0, 0)]
    while pq:
        cost, pos, placed, mask = heapq.heappop(pq)
        if placed >= k:
            return cost
        if cost > best.get((pos, placed, mask), 1 << 30):
            continue
        for i, (dx, dy) in enumerate(CARD):
            nxt = (pos[0] + dx, pos[1] + dy)
            if passable(nxt):
                key = (nxt, placed, 0)
                if cost + 1 < best.get(key, 1 << 30):
                    best[key] = cost + 1
                    heapq.heappush(pq, (cost + 1, nxt, placed, 0))
            spot = (pos[0] + dx, pos[1] + dy)
            if spot in spots and not (mask & (1 << i)):
                key = (pos, placed + 1, mask | (1 << i))
                if cost + 1 < best.get(key, 1 << 30):
                    best[key] = cost + 1
                    heapq.heappush(pq, (cost + 1, pos, placed + 1, mask | (1 << i)))
    return None


def main():
    bot = sys.argv[1] if len(sys.argv) > 1 else "bots/elias/rush"
    foe_bot = sys.argv[2] if len(sys.argv) > 2 else "bots/zoo/idle"
    k = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    scrub()
    out = ROOT / "replays" / "ringfloor.replay26"
    out.parent.mkdir(parents=True, exist_ok=True)
    print("RING FLOOR  k=%d   (move 1 round, build 1 round; optimistic lower bound)" % k)
    print("%-14s %7s %7s %6s  %s" % ("map", "floor", "actual", "LATE", "result"))
    late_total, measured, skipped = 0, 0, []
    for m in MAPS:
        res = run_game(str(ROOT / bot / "main.py"), str(ROOT / foe_bot / "main.py"), ENGINE,
                       str(ROOT / "maps" / (m + ".map26")), str(out), 1, 0)
        r = load_replay(str(out))
        walls = {(x, y) for y in range(r.height) for x in range(r.width)
                 if r.env[y][x] == 1}
        cores = {t: (x, y) for _i, t, x, y in r.cores}
        spawn = None
        ring = []
        for t, st, ta in r.iter_states():
            for e in ta.placed:
                if e.team != "a":
                    continue
                if e.kind == "builder_bot" and spawn is None:
                    spawn = (e.x, e.y)
                if e.kind == "sentinel":
                    ring.append(t)
        if spawn is None or len(ring) < k:
            skipped.append("%s(%d turrets)" % (m, len(ring)))
            print("%-14s %7s %7s %6s  %s" % (m, "-", "-", "-", "PARTIAL, excluded"))
            continue
        spots, foot = firing_spots(cores["b"], walls, r.width, r.height)
        fl = floor_rounds(spawn, spots, walls, foot, r.width, r.height, k)
        actual = ring[k - 1]
        if fl is None:
            skipped.append("%s(no route)" % m)
            continue
        late = actual - fl
        late_total += late
        measured += 1
        print("%-14s %7d %7d %6d  %s" % (m, fl, actual, late,
                                         "WIN" if res["winner"] == "A" else "loss"))
    scrub()
    print()
    print("MEASURED %d/%d games   TOTAL LATE %d rounds   mean %.1f" % (
        measured, len(MAPS), late_total, late_total / max(measured, 1)))
    if skipped:
        print("skipped: %s" % ", ".join(skipped))


main()
