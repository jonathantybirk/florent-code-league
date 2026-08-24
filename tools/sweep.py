"""Play two bots over the whole map pool in both seats and report the result.

Every pair plays every map from both sides, which is what makes first-player
advantage cancel in the aggregate rather than showing up as skill. Matches run
with `--tle 0` so they are deterministic and two sweeps of the same code agree
match for match; timing is a separate question, measured by `--tle 10` with
`--compliance`, because a bot that is slow on one map should show up as slow
rather than as weak.

    uv run python tools/sweep.py bots/jon/brokkr bots/rivals/hildr
    uv run python tools/sweep.py A B --maps holmgang,skald --seeds 3
    uv run python tools/sweep.py A B --compliance
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POOL = ("auroraveil", "bifrost", "fimbulwinter", "glacierkeep", "helheim",
        "holmgang", "icefloe", "jotunheim", "longhouse", "midgard", "paths",
        "skald", "stavkirke", "valkyrie", "yggdrasil")


def play(task):
    bot_a, bot_b, map_name, seed, tle = task
    command = ["uv", "run", "fcode", "run", bot_a, bot_b, map_name,
               "--seed", str(seed), "--json", "--mark", "0",
               "--tle", str(tle), "--replay", f"/tmp/sweep_{map_name}_{seed}.replay26"]
    try:
        proc = subprocess.run(command, cwd=ROOT, capture_output=True,
                              text=True, timeout=600)
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:                       # a crash is a result too
        return {"map": map_name, "seed": seed, "error": str(exc)[:200]}
    result["map"] = map_name
    result["seed"] = seed
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bot_a")
    parser.add_argument("bot_b")
    parser.add_argument("--maps", default=",".join(POOL))
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=10)
    parser.add_argument("--compliance", action="store_true",
                        help="run at the ladder's 10 ms limit and report timeouts")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    maps = [m.strip() for m in args.maps.split(",") if m.strip()]
    tle = 10 if args.compliance else 0

    # Both seats: (a, b) and (b, a). The second is folded back so "our" bot is
    # always bot_a in the report.
    tasks = []
    for map_name in maps:
        for seed in range(1, args.seeds + 1):
            tasks.append((args.bot_a, args.bot_b, map_name, seed, tle))
            tasks.append((args.bot_b, args.bot_a, map_name, seed, tle))

    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(play, tasks))

    rows = []
    for task, result in zip(tasks, results):
        swapped = task[0] == args.bot_b
        if "error" in result:
            rows.append({**result, "won": None, "swapped": swapped})
            continue
        winner = result.get("winner")
        won = (winner == "B") if swapped else (winner == "A")
        ours, theirs = ("b", "a") if swapped else ("a", "b")
        rows.append({
            "map": result["map"], "seed": result["seed"], "swapped": swapped,
            "won": won, "turns": result["turns"],
            "win_condition": result["win_condition"],
            "mined": result[f"{ours}_titanium_collected"],
            "opp_mined": result[f"{theirs}_titanium_collected"],
            "buildings": result[f"{ours}_buildings"],
            "opp_buildings": result[f"{theirs}_buildings"],
            "units": result[f"{ours}_units"],
        })

    _report(args, rows)
    if args.json_out:
        args.json_out.write_text(json.dumps(rows, indent=2))


def _report(args, rows) -> None:
    errors = [r for r in rows if r.get("won") is None]
    played = [r for r in rows if r.get("won") is not None]
    wins = sum(1 for r in played if r["won"])

    print(f"{args.bot_a}  vs  {args.bot_b}"
          + ("   [10 ms limit enforced]" if args.compliance else ""))
    print(f"{'map':<14}{'seat A':>8}{'seat B':>8}{'mined':>9}{'opp':>9}"
          f"{'turns':>7}  win condition")
    by_map: dict[str, list] = {}
    for row in played:
        by_map.setdefault(row["map"], []).append(row)
    for map_name in sorted(by_map):
        group = by_map[map_name]
        a = _mark([r for r in group if not r["swapped"]])
        b = _mark([r for r in group if r["swapped"]])
        mined = sum(r["mined"] for r in group) // max(1, len(group))
        opp = sum(r["opp_mined"] for r in group) // max(1, len(group))
        turns = sum(r["turns"] for r in group) // max(1, len(group))
        conditions = {r["win_condition"] for r in group}
        print(f"{map_name:<14}{a:>8}{b:>8}{mined:>9}{opp:>9}{turns:>7}  "
              + ",".join(sorted(conditions)))

    if played:
        print(f"\n{wins}/{len(played)} games ({wins / len(played):.1%})")
        mined = sum(r["mined"] for r in played) / len(played)
        opp = sum(r["opp_mined"] for r in played) / len(played)
        print(f"mean titanium collected {mined:.0f} vs {opp:.0f}")
        losses = [r for r in played if not r["won"]]
        if losses:
            quick = sorted(losses, key=lambda r: r["turns"])[:3]
            print("fastest losses: "
                  + ", ".join(f"{r['map']}@{r['turns']}({r['win_condition']})"
                              for r in quick))
    for row in errors:
        print(f"ERROR {row['map']} seed {row['seed']}: {row.get('error')}")


def _mark(group) -> str:
    if not group:
        return "-"
    return "".join("W" if r["won"] else "L" for r in group)


if __name__ == "__main__":
    main()
