"""Fold per-match result JSONs into one CSV.

Idempotent by match_id, so this can run repeatedly against a directory that LSF jobs are still
writing into -- which is exactly what `hpc fetch` does to stream results in as they land.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

COLUMNS = [
    "match_id",
    "tournament_id",
    "bot_a",
    "bot_a_name",
    "bot_a_commit",
    "bot_b",
    "bot_b_name",
    "bot_b_commit",
    "map",
    "map_set",
    "seed",
    "tle",
    "kind",
    "winner",
    "score_a",
    "win_condition",
    "turns",
    "resign_message",
    "a_titanium",
    "a_titanium_collected",
    "a_units",
    "a_buildings",
    "b_titanium",
    "b_titanium_collected",
    "b_units",
    "b_buildings",
    "status",
    "error",
    "duration_s",
    "host",
    "lsf_job",
    "finished_at",
]


def merge(run_dir: Path) -> tuple[Path, int]:
    """Rewrite matches.csv from every result file present. Returns the path and row count."""
    from tournament.plan import load_manifest

    manifest = load_manifest(run_dir)
    bots = {bot["bot_id"]: bot for bot in manifest["bots"]}

    rows: dict[str, dict] = {}
    records: dict[str, dict] = {}
    for path in sorted((run_dir / "results").glob("*.json")):
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError:
            # A job killed mid-write leaves a truncated file; the atomic rename in run_match
            # should prevent it, but a partial read must never abort the merge.
            print(f"  skipping unreadable {path.name}")
            continue
        row = dict.fromkeys(COLUMNS, "")
        row.update({key: value for key, value in record.items() if key in COLUMNS})
        row["tournament_id"] = manifest["tournament_id"]
        row["map_set"] = manifest["map_set"]
        for side in ("a", "b"):
            bot = bots.get(record.get(f"bot_{side}", ""))
            if bot:
                row[f"bot_{side}_name"] = bot["name"]
                row[f"bot_{side}_commit"] = bot["commit"][:7]
        rows[record["match_id"]] = row
        records[record["match_id"]] = record

    output = run_dir / "matches.csv"
    with open(output, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for match_id in sorted(rows):
            if records[match_id].get("kind", "rating") == "rating":
                writer.writerow(rows[match_id])

    if manifest.get("compliance"):
        from tournament.compliance import write_reports

        write_reports(run_dir, list(records.values()), manifest)
    return output, len(rows)


def read(run_dir: Path) -> list[dict]:
    path = run_dir / "matches.csv"
    if not path.exists():
        raise FileNotFoundError(f"no {path} -- run `merge` first")
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))
