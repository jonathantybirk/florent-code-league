"""Round-robin / cross-table benchmark over many bots at once.

    uv run python scratch/matrix.py --bots a,b,c [--vs d,e] [--maps m1,m2]

With --vs, every bot in --bots is played against every bot in --vs. Without it,
--bots plays a full round robin against itself. Every pairing is played on both
sides of every map, so the table is symmetric by construction.
"""
import argparse
import concurrent.futures as cf
import itertools
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
ALL_MAPS = sorted(p.name[:-6] for p in (ROOT / "maps").glob("*.map26"))
RESULT = re.compile(r"Winner:\s+(\S+)\s+\((.*?), turn (\d+)\)")


def play(a, b, mapname):
    handle, replay = tempfile.mkstemp(suffix=".replay26")
    os.close(handle)
    try:
        out = subprocess.run(
            ["uv", "run", "fcode", "run", a, b, f"maps/{mapname}.map26",
             "--replay", replay, "--seed", "1"],
            cwd=ROOT, capture_output=True, text=True, timeout=600,
        ).stdout.replace("\n", " ")
        found = RESULT.search(out)
        if found is None:
            return None
        winner = found.group(1)
        an, bn = a.split("/")[-1], b.split("/")[-1]
        return "A" if winner == an else ("B" if winner == bn else None)
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            os.unlink(replay)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bots", required=True)
    ap.add_argument("--vs", default=None)
    ap.add_argument("--maps", default=None)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    bots = args.bots.split(",")
    rivals = args.vs.split(",") if args.vs else bots
    maps = args.maps.split(",") if args.maps else ALL_MAPS
    pairs = ([(x, y) for x in bots for y in rivals] if args.vs
             else list(itertools.combinations(bots, 2)))

    jobs = [(x, y, m) for x, y in pairs for m in maps]
    jobs += [(y, x, m) for x, y in pairs for m in maps]
    print(f"{len(bots)} bots x {len(rivals)} rivals x {len(maps)} maps "
          f"= {len(jobs)} games", file=sys.stderr, flush=True)

    score = defaultdict(int)          # (bot, rival) -> wins
    played = defaultdict(int)
    with cf.ThreadPoolExecutor(args.jobs) as ex:
        futures = {ex.submit(play, *j): j for j in jobs}
        for done, future in enumerate(cf.as_completed(futures), 1):
            first, second, _ = futures[future]
            side = future.result()
            if side is None:
                continue
            win, lose = (first, second) if side == "A" else (second, first)
            score[(win, lose)] += 1
            played[(first, second)] += 1
            played[(second, first)] += 1
            if done % 200 == 0:
                print(f"  {done}/{len(jobs)}", file=sys.stderr, flush=True)

    label = {b: b.split("/")[-1][:17] for b in set(bots) | set(rivals)}
    width = max(len(v) for v in label.values()) + 1
    header = " " * (width + 2) + " ".join(f"{label[r][:8]:>8s}" for r in rivals)
    print(header)
    rows = []
    for bot in bots:
        wins = losses = 0
        cells = []
        for rival in rivals:
            if rival == bot:
                cells.append(f"{'-':>8s}")
                continue
            w, l = score[(bot, rival)], score[(rival, bot)]
            wins, losses = wins + w, losses + l
            cells.append(f"{w:>3d}-{l:<4d}")
        total = wins + losses
        rows.append((wins / max(total, 1), bot, wins, losses, cells))
    for rate, bot, wins, losses, cells in sorted(rows, reverse=True):
        print(f"{label[bot]:>{width}s}  " + " ".join(cells)
              + f"   | {wins:4d}-{losses:<4d} {100 * rate:5.1f}%")


main()
