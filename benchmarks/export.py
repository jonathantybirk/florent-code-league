"""Flatten a run directory into one CSV, so the evidence is committable.

A run is thousands of small JSON files; this is the same data as one row per
match. Raw run directories are gitignored (they also contain staged copies of
bots, which must never reach `bots/` where tournament discovery would see a
second bot of the same name).

    uv run python -m benchmarks.export --run-dir benchmarks/runs/<name>
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

COLUMNS = [
    "kind", "a", "b", "map", "winner", "win_condition", "turns",
    "a_titanium_collected", "b_titanium_collected",
    "a_first_harvester", "a_harvesters_built", "a_builders_spawned",
    "a_gunners_built", "a_sentinels_built", "a_launchers_built",
    "a_barriers_built", "a_conveyors_built",
    "a_first_core_hit", "a_core_damage_dealt", "a_enemy_core_killed_round",
    "a_core_hp_end", "a_worst_builder_stall", "a_stalled_builders",
    "b_first_harvester", "b_harvesters_built", "b_core_hp_end",
    "b_worst_builder_stall", "duration_s",
]


def rows(run_dir: Path):
    schedule_path = run_dir / "schedule.json"
    schedule = ({m["id"]: m for m in json.loads(schedule_path.read_text())}
                if schedule_path.exists() else {})
    for path in sorted((run_dir / "results").glob("*.json")):
        record = json.loads(path.read_text())
        if record.get("status") != "ok":
            continue
        match = schedule.get(path.stem)
        if match is not None:
            kind, a, b = match["kind"], match["a"], match["b"]
        else:
            # A run directory reused across suite invocations keeps only the
            # last schedule; the filename carries the identity regardless.
            kind, _, rest = path.stem.partition("-")
            left, _, right = rest.partition("-vs-")
            a, b = left, right.rsplit("-", 1)[0]
        engine, metrics = record["engine"], record["metrics"]
        row = {"kind": kind, "a": a, "b": b, "map": record["map"],
               "duration_s": record["duration_s"]}
        for column in COLUMNS:
            if column in row:
                continue
            row[column] = engine.get(column, metrics.get(column))
        yield row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    # benchmarks/runs/ is gitignored, so the default lands in data/ instead.
    out = args.out or (run_dir.parent.parent / "data" / f"{run_dir.name}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows(run_dir):
            writer.writerow(row)
            count += 1
    print(f"{count} matches -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
