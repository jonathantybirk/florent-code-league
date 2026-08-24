"""Find the turn-time limit at which a bot's results start to change.

The engine has no timeout flag in its result: an over-budget turn is simply
dropped, so a bot that is too slow silently plays worse instead of erroring.
The only honest probe is to tighten `fcode run --tle` until outcomes move.
Identical results from unlimited down to N means no turn in that sample took
longer than N.

`--tle` binds *both* bots, so a divergence does not by itself say whose turn was
slow. `--attribute` answers that by running mirror matches: if bot-v-itself is
clean at N, that bot's own worst turn is under N.

    uv run python benchmarks/tle.py --bot heimdall
    uv run python benchmarks/tle.py --bot heimdall --attribute
"""
from __future__ import annotations

import argparse
import itertools
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

MAPS = ["longship", "aurora", "runestone", "vase", "sweden"]


def play(a: str, b: str, mp: str, tle: int):
    """One match; returns a comparable outcome signature, or None if it failed."""
    result = subprocess.run(
        ["uv", "run", "fcode", "run", f"bots/luc/{a}", f"bots/luc/{b}",
         f"maps/{mp}.map26", "--tle", str(tle), "--json",
         "--replay", f"/tmp/tle_probe_{a}_{b}_{mp}_{tle}.replay26"],
        capture_output=True, text=True)
    lines = [l for l in result.stdout.splitlines() if l.startswith("{")]
    if not lines:
        return None
    got = json.loads(lines[-1])
    return got["winner"], got["turns"], got["win_condition"]


def sweep(bot, panel, limits, jobs):
    """Compare each limit against unlimited play over the whole panel."""
    cells = list(itertools.product(MAPS, panel, (0, 1)))

    def one(args):
        tle, (mp, opp, seat) = args
        a, b = (bot, opp) if seat == 0 else (opp, bot)
        return (tle, mp, opp, seat), play(a, b, mp, tle)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        got = dict(pool.map(one, itertools.product([0] + limits, cells)))

    def won(key, seat):
        out = got[key]
        return out is not None and out[0] == ("A" if seat == 0 else "B")

    base = {c: got[(0,) + c] for c in cells}
    print(f"  --tle  0: {sum(won((0,)+c, c[2]) for c in cells)}/{len(cells)} wins   baseline (off)")
    for tle in limits:
        moved = sum(1 for c in cells if got[(tle,) + c] != base[c])
        wins = sum(won((tle,) + c, c[2]) for c in cells)
        tag = "identical to unlimited" if moved == 0 else f"{moved}/{len(cells)} games differ"
        print(f"  --tle {tle:2d}: {wins}/{len(cells)} wins   {tag}")


def attribute(bots, limits, jobs):
    """Mirror matches: the lowest limit at which a bot still plays unlimited-identically."""
    def probe(bot):
        hits = []
        for mp in MAPS:
            base = play(bot, bot, mp, 0)
            for tle in limits:
                if play(bot, bot, mp, tle) != base:
                    hits.append((mp, tle))
                    break
        return bot, hits

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for bot, hits in pool.map(probe, bots):
            note = hits if hits else f"never (clean at >={min(limits)}ms on all {len(MAPS)} maps)"
            print(f"  {bot + ' v ' + bot:26s} diverges at: {note}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", default="heimdall")
    ap.add_argument("--panel", default="valkyrie,vigil,ragnarok")
    ap.add_argument("--limits", default="10,8,6,4,2")
    ap.add_argument("--attribute", action="store_true")
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    panel = args.panel.split(",")
    limits = [int(x) for x in args.limits.split(",")]
    if args.attribute:
        attribute([args.bot] + panel, limits, args.jobs)
    else:
        sweep(args.bot, panel, limits, args.jobs)
