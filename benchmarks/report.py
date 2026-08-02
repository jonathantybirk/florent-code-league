"""Aggregate a benchmark run into per-bot mechanic tables.

    uv run python -m benchmarks.report --run-dir benchmarks/runs/<name>

Prints a markdown report; --json writes the aggregate rows for further use.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def load(run_dir: Path) -> list[dict]:
    rows = []
    for path in (run_dir / "results").glob("*.json"):
        row = json.loads(path.read_text())
        if row.get("status") == "ok":
            rows.append(row)
    return rows


def median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 1) if values else None


def mean(values):
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 2) if values else None


def aggregate(rows: list[dict]) -> dict:
    """Group by (suite kind, subject bot) and summarise mechanics."""
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        kind = row.get("_kind")
        if kind is None:
            # Recover the suite kind from the result filename convention.
            continue
        by_key[(kind, row["_subject"])].append(row)
    out = {}
    for (kind, bot), group in sorted(by_key.items()):
        m = [r["metrics"] for r in group]
        e = [r["engine"] for r in group]
        wins = sum(1 for r in group if str(r["engine"]["winner"]).lower() == "a")
        summary = {
            "games": len(group),
            "wins": wins,
            "kill_round": median([x["a_enemy_core_killed_round"] for x in m]),
            "first_harvester": median([x["a_first_harvester"] for x in m]),
            "harv@100": mean([x["a_harvesters_at"]["100"] for x in m]),
            "harv@300": mean([x["a_harvesters_at"]["300"] for x in m]),
            "collected": mean([x["a_titanium_collected"] for x in e]),
            "stalled": mean([x["a_stalled_builders"] for x in m]),
            "worst_stall": median([x["a_worst_builder_stall"] for x in m]),
            "core_hp_end": mean([x["a_core_hp_end"] for x in m]),
            "survived": sum(
                1 for x in m
                if x["a_core_hp_end"] > 0 and x["rounds"] >= 999
            ),
        }
        out[f"{kind}/{bot}"] = summary
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    schedule = {m["id"]: m
                for m in json.loads((run_dir / "schedule.json").read_text())}
    rows = []
    for path in (run_dir / "results").glob("*.json"):
        row = json.loads(path.read_text())
        if row.get("status") != "ok":
            continue
        match = schedule.get(path.stem)
        if match is None:
            continue
        row["_kind"] = match["kind"]
        row["_subject"] = match["a"]
        row["_opponent"] = match["b"]
        rows.append(row)

    agg = aggregate(rows)
    if args.json:
        args.json.write_text(json.dumps(agg, indent=1))

    kinds = sorted({key.split("/")[0] for key in agg})
    for kind in kinds:
        print(f"\n## {kind}")
        header = ("bot", "games", "wins", "kill_rd", "1st_harv", "harv@100",
                  "harv@300", "collected", "stalled", "worst_stall",
                  "hp_end", "survived")
        print("| " + " | ".join(header) + " |")
        print("|" + "---|" * len(header))
        entries = [(key.split("/")[1], s) for key, s in agg.items()
                   if key.startswith(kind + "/")]
        entries.sort(key=lambda kv: (-kv[1]["wins"], kv[0]))
        for bot, s in entries:
            print(f"| {bot} | {s['games']} | {s['wins']} | {s['kill_round']} "
                  f"| {s['first_harvester']} | {s['harv@100']} "
                  f"| {s['harv@300']} | {s['collected']} | {s['stalled']} "
                  f"| {s['worst_stall']} | {s['core_hp_end']} "
                  f"| {s['survived']} |")

    # Head-to-head win matrix.
    h2h = [r for r in rows if r["_kind"] == "h2h"]
    if h2h:
        score: dict[str, float] = defaultdict(float)
        games: dict[str, int] = defaultdict(int)
        pair: dict[tuple[str, str], float] = defaultdict(float)
        pair_n: dict[tuple[str, str], int] = defaultdict(int)
        for r in h2h:
            a, b = r["_subject"], r["_opponent"]
            win = (1.0 if str(r["engine"]["winner"]).lower() == "a"
                   else 0.5 if r["metrics"]["win_condition"] == "coinflip"
                   else 0.0)
            score[a] += win
            score[b] += 1 - win
            games[a] += 1
            games[b] += 1
            pair[(a, b)] += win
            pair[(b, a)] += 1 - win
            pair_n[(a, b)] += 1
            pair_n[(b, a)] += 1
        print("\n## h2h totals")
        bots = sorted(score, key=lambda x: -score[x] / games[x])
        for bot in bots:
            print(f"| {bot} | {score[bot]:.1f}/{games[bot]} "
                  f"| {100 * score[bot] / games[bot]:.0f}% |")
        print("\n## h2h matrix (row's score vs column, out of "
              + str(max(pair_n.values())) + ")")
        print("| vs | " + " | ".join(bots) + " |")
        print("|" + "---|" * (len(bots) + 1))
        for a in bots:
            cells = []
            for b in bots:
                if a == b:
                    cells.append("—")
                else:
                    cells.append(f"{pair[(a, b)]:.1f}")
            print(f"| {a} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
