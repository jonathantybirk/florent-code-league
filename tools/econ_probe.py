"""Measure a bot's economy on the same axis the ladder study used.

`analyze_top_mining.parse_replay` reports titanium collected at fixed
checkpoints, which is how the top-ten builds in `scratch/current_top10_200`
were characterised. Running our own replays through the same parser makes the
two numbers directly comparable instead of two different measurements of
"economy".

Play against a passive opponent to read the economy on its own, or against a
real one to read what survives contact:

    uv run python tools/econ_probe.py bots/jon/brokkr
    uv run python tools/econ_probe.py bots/jon/brokkr --vs bots/rivals/steward
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_top_mining import parse_replay  # noqa: E402
from sweep import POOL, ROOT  # noqa: E402

CHECKPOINTS = ("10", "25", "50", "100", "200")


def run_one(task):
    bot, opponent, map_name, seed = task
    replay = Path(f"/tmp/econ_{map_name}_{seed}.replay26")
    command = ["uv", "run", "fcode", "run", bot, opponent, map_name,
               "--seed", str(seed), "--json", "--mark", "0", "--tle", "0",
               "--replay", str(replay)]
    try:
        proc = subprocess.run(command, cwd=ROOT, capture_output=True,
                              text=True, timeout=600)
        summary = json.loads(proc.stdout.strip().splitlines()[-1])
        parsed = parse_replay(replay)
    except Exception as exc:
        return {"map": map_name, "error": str(exc)[:160]}
    # We are always side 0 here; the probe deliberately does not swap seats,
    # because economy is being measured, not the seat advantage in a fight.
    team = parsed["teams"][0]
    return {
        "map": map_name,
        "final": summary["a_titanium_collected"],
        "turns": summary["turns"],
        "harvesters": team["built"].get("harvester", 0),
        "conveyors": team["built"].get("conveyor", 0),
        "bots": team["built"].get("bot", 0),
        "first_harvester": team["first"].get("harvester"),
        "checkpoints": {c: team["checkpoints"].get(c, {}).get("titanium_collected", 0)
                        for c in CHECKPOINTS},
        "live_200": team["checkpoints"].get("200", {}).get("live", {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bot")
    parser.add_argument("--vs", default="bots/common/donothingbot")
    parser.add_argument("--maps", default=",".join(POOL))
    parser.add_argument("--jobs", type=int, default=10)
    args = parser.parse_args()

    maps = [m.strip() for m in args.maps.split(",") if m.strip()]
    tasks = [(args.bot, args.vs, m, 1) for m in maps]
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        rows = list(pool.map(run_one, tasks))

    good = [r for r in rows if "error" not in r]
    print(f"{args.bot}  vs  {args.vs}")
    header = "".join(f"{'t' + c:>7}" for c in CHECKPOINTS)
    print(f"{'map':<14}{header}{'final':>8}{'harv':>6}{'conv':>6}{'bots':>6}{'1stH':>6}")
    for row in good:
        cells = "".join(f"{row['checkpoints'][c]:>7}" for c in CHECKPOINTS)
        first = row["first_harvester"]
        print(f"{row['map']:<14}{cells}{row['final']:>8}{row['harvesters']:>6}"
              f"{row['conveyors']:>6}{row['bots']:>6}"
              f"{'-' if first is None else first:>6}")
    if good:
        print(f"\n{'MEAN':<14}" + "".join(
            f"{sum(r['checkpoints'][c] for r in good) // len(good):>7}"
            for c in CHECKPOINTS)
            + f"{sum(r['final'] for r in good) // len(good):>8}"
            + f"{sum(r['harvesters'] for r in good) / len(good):>6.1f}"
            + f"{sum(r['conveyors'] for r in good) / len(good):>6.1f}"
            + f"{sum(r['bots'] for r in good) / len(good):>6.1f}")
        firsts = [r["first_harvester"] for r in good if r["first_harvester"] is not None]
        if firsts:
            print(f"first harvester: median round {sorted(firsts)[len(firsts) // 2]}"
                  f"  (never built on {len(good) - len(firsts)} of {len(good)} maps)")
    for row in rows:
        if "error" in row:
            print(f"ERROR {row['map']}: {row['error']}")


if __name__ == "__main__":
    main()
