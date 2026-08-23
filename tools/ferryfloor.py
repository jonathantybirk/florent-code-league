"""ringfloor.py, but the Builder is allowed to build its own Launcher and be thrown.

Same Dijkstra, same map data, same spawn tile (read from a real replay vs idle), plus one
extra edge kind:

    HOP:  round T   builder builds a Launcher on an orthogonally adjacent passable tile L
          round T+1 the Launcher throws the builder to any passable tile with d^2 <= 26 of L
          cost 2 rounds, lands anywhere in an 89-tile disc, ARCS OVER WALLS.

Conservative on three counts, all in the direction of understating the ferry:
  * the free move the builder still gets on its throw round (it acts before the higher-id
    Launcher) is not modelled -- worth up to 1 more tile per hop;
  * the launcher tile must be orthogonally adjacent, never diagonal;
  * hops are only allowed before the first turret goes up.

Usage: python ferryfloor.py <max_hops>
"""

import heapq
import os
import pathlib
import shutil
import sys

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import fcode                                    # noqa: E402
from fcode.fcode_engine import run_game         # noqa: E402
from diag.replay import load_replay             # noqa: E402

ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
MAPS = ["auroraveil", "bifrost", "fimbulwinter", "glacierkeep", "helheim", "holmgang", "icefloe",
        "jotunheim", "longhouse", "midgard", "paths", "skald", "stavkirke", "valkyrie",
        "yggdrasil"]
CARD = ((0, -1), (0, 1), (1, 0), (-1, 0))
RAYS = ((0, -1), (0, 1), (1, 0), (-1, 0), (1, -1), (-1, -1), (1, 1), (-1, 1))
MAX_RANGE_SQ = 32
THROW_SQ = 26                     # GameConstants.LAUNCHER_VISION_RADIUS_SQ, measured max d^2
DISC = [(dx, dy) for dx in range(-5, 6) for dy in range(-5, 6)
        if 0 < dx * dx + dy * dy <= THROW_SQ]


def scrub():
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" not in pc.parts:
            shutil.rmtree(pc, ignore_errors=True)


def firing_spots(foe, walls, w, h):
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


def floor_rounds(start, spots, walls, foot, w, h, k, max_hops):
    def passable(p):
        return (0 <= p[0] < w and 0 <= p[1] < h and p not in walls and p not in foot)

    best = {(start, 0, 0, 0): 0}
    pq = [(0, start, 0, 0, 0)]
    while pq:
        cost, pos, placed, mask, hops = heapq.heappop(pq)
        if placed >= k:
            return cost, hops
        if cost > best.get((pos, placed, mask, hops), 1 << 30):
            continue
        for i, (dx, dy) in enumerate(CARD):
            nxt = (pos[0] + dx, pos[1] + dy)
            if passable(nxt):
                key = (nxt, placed, 0, hops)
                if cost + 1 < best.get(key, 1 << 30):
                    best[key] = cost + 1
                    heapq.heappush(pq, (cost + 1, nxt, placed, 0, hops))
            spot = (pos[0] + dx, pos[1] + dy)
            if spot in spots and not (mask & (1 << i)):
                key = (pos, placed + 1, mask | (1 << i), hops)
                if cost + 1 < best.get(key, 1 << 30):
                    best[key] = cost + 1
                    heapq.heappush(pq, (cost + 1, pos, placed + 1, mask | (1 << i), hops))
        # ---- the ferry hop: 2 rounds, an 89-tile disc, over any wall
        if hops < max_hops and placed == 0:
            for dx, dy in CARD:
                lch = (pos[0] + dx, pos[1] + dy)
                if not passable(lch):
                    continue                     # the Launcher needs a buildable tile
                for ox, oy in DISC:
                    land = (lch[0] + ox, lch[1] + oy)
                    if land == pos or not passable(land):
                        continue
                    key = (land, 0, 0, hops + 1)
                    if cost + 2 < best.get(key, 1 << 30):
                        best[key] = cost + 2
                        heapq.heappush(pq, (cost + 2, land, 0, 0, hops + 1))
    return None, 0


def main():
    max_hops = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    k = 4
    scrub()
    out = ROOT / "replays" / "ferryfloor.replay26"
    out.parent.mkdir(parents=True, exist_ok=True)
    print("FERRY FLOOR  k=%d  max_hops=%d   (move 1, build 1, hop 2 rounds)" % (k, max_hops))
    print("%-14s %6s %6s %6s %6s %6s  %s" % (
        "map", "walk", "hop1", "hop2", "best", "saved", "hops used"))
    tot = [0, 0, 0]
    n = 0
    for m in MAPS:
        run_game(str(ROOT / "bots/elias/rush/main.py"), str(ROOT / "bots/zoo/idle/main.py"),
                 ENGINE, str(ROOT / "maps" / (m + ".map26")), str(out), 1, 0)
        r = load_replay(str(out))
        walls = {(x, y) for y in range(r.height) for x in range(r.width) if r.env[y][x] == 1}
        cores = {t: (x, y) for _i, t, x, y in r.cores}
        spawn = None
        for _t, _st, ta in r.iter_states():
            for e in ta.placed:
                if e.team == "a" and e.kind == "builder_bot" and spawn is None:
                    spawn = (e.x, e.y)
        spots, foot = firing_spots(cores["b"], walls, r.width, r.height)
        vals = []
        for h in range(0, max_hops + 1):
            c, used = floor_rounds(spawn, spots, walls, foot, r.width, r.height, k, h)
            vals.append((c, used))
        walk = vals[0][0]
        best, usedh = min(vals, key=lambda v: v[0])
        print("%-14s %6d %6s %6s %6d %6d  %d" % (
            m, walk,
            vals[1][0] if len(vals) > 1 else "-",
            vals[2][0] if len(vals) > 2 else "-",
            best, walk - best, usedh))
        tot[0] += walk
        tot[1] += vals[1][0] if len(vals) > 1 else walk
        tot[2] += best
        n += 1
    print()
    print("MEAN  walk %.1f   hop<=1 %.1f   best %.1f   SAVED %.1f rounds/map" % (
        tot[0] / n, tot[1] / n, tot[2] / n, (tot[0] - tot[2]) / n))
    scrub()


main()
