"""Mirrored round-robin benchmark: one bot against a panel, both seats, every map.

Every pairing is played twice with the seats swapped, because the engine gives the
first-spawning team a real advantage (Team A wins ~58-60% of identical-bot mirrors),
so a single-seat score is not a measurement of the bot.

    uv run python tools/bench.py <bot> --panel vidar,odin --maps 8 --jobs 8

Prints a per-opponent table and the total. Exit status is 0 always; read the number.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WINNER = re.compile(r"Winner:\s+(\S+)")


def maps_available() -> list[str]:
    return sorted(p.stem for p in (ROOT / "maps").glob("*.map26"))


def play(bot_a: str, bot_b: str, map_name: str, tle: int, seed: int) -> str | None:
    """Return the *path* of the winning bot, or None if the match did not resolve."""
    cmd = ["uv", "run", "fcode", "run", bot_a, bot_b, map_name,
           "--seed", str(seed)]
    if tle:
        cmd += ["--tle", str(tle)]
    try:
        out = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=600
        ).stdout
    except subprocess.TimeoutExpired:
        return None
    m = WINNER.search(out)
    if not m:
        return None
    # fcode prints the bot's directory name, not the path we passed in.
    name = m.group(1)
    return bot_a if name == bot_a.rsplit("/", 1)[-1] else bot_b


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bot")
    ap.add_argument("--panel", required=True, help="comma list of opponent bot paths")
    ap.add_argument("--maps", default="", help="comma list of map names, or a count")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--tle", type=int, default=0, help="per-turn CPU limit in ms")
    ap.add_argument("--seed", type=int, default=1, help="engine seed")
    args = ap.parse_args()

    all_maps = maps_available()
    if not args.maps:
        maps = all_maps
    elif args.maps.isdigit():
        maps = all_maps[: int(args.maps)]
    else:
        maps = args.maps.split(",")

    panel = args.panel.split(",")
    jobs: list[tuple[str, str, str]] = []
    for opp in panel:
        for m in maps:
            jobs.append((opp, m, "A"))  # our bot spawns first
            jobs.append((opp, m, "B"))  # opponent spawns first

    results: dict[str, list[int]] = {opp: [0, 0, 0] for opp in panel}  # win, loss, unresolved

    def run_one(job):
        opp, m, seat = job
        a, b = (args.bot, opp) if seat == "A" else (opp, args.bot)
        w = play(a, b, m, args.tle, args.seed)
        return opp, m, seat, w

    with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for opp, m, seat, w in ex.map(run_one, jobs):
            r = results[opp]
            if w is None:
                r[2] += 1
            elif w == args.bot:
                r[0] += 1
            else:
                r[1] += 1

    print(f"\n{args.bot}  —  {len(maps)} maps x both seats\n")
    print(f"{'opponent':26s} {'W':>4} {'L':>4} {'?':>3}  {'rate':>6}")
    print("-" * 50)
    tw = tl = tu = 0
    for opp in panel:
        w, l, u = results[opp]
        tw += w
        tl += l
        tu += u
        n = w + l
        print(f"{opp:26s} {w:4d} {l:4d} {u:3d}  {(w/n if n else 0):6.3f}")
    print("-" * 50)
    n = tw + tl
    print(f"{'TOTAL':26s} {tw:4d} {tl:4d} {tu:3d}  {(tw/n if n else 0):6.3f}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
