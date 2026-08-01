"""Short, instrumented checks of the ladder's 10 ms per-unit turn limit.

Compliance matches are deliberately separate from rating matches.  They run a staged copy of the
submission as player A against a passive harness bot.  The wrapper calls the engine's official
``get_cpu_time_elapsed()`` clock after each successful ``run()`` and writes compact start/end
markers into the temporary replay.  The runner extracts them before deleting the replay.

This module must remain standard-library only: :mod:`tournament.plan` imports it on paths that are
also used by local match workers.
"""

from __future__ import annotations

import csv
import math
import shutil
from pathlib import Path

from tournament.maps import label
from tournament.registry import BotSpec

VERSION = 4
LIMIT_US = 10_000
CLOSE_US = 9_000
# The probe measures against LIMIT_US itself.  A slightly looser engine watchdog prevents the
# replay markers from creating the timeout they are trying to observe.  A start without an end,
# followed by the same entity running next round, still proves that it hit this looser guard.
GUARD_TLE_MS = 12
SAMPLE_ROUNDS = 25
MAPS = ("atoll", "duel", "quarry")
BASELINE_ID = f"__compliance_baseline__@v{VERSION}"
START_MARKER = f"FCL_COMPLIANCE_START:v{VERSION}"
END_MARKER = f"FCL_COMPLIANCE_END:v{VERSION}"
ERROR_MARKER = f"FCL_COMPLIANCE_ERROR:v{VERSION}"

WRAPPER = f'''"""Generated timing wrapper; the pinned submission is in _submission.py."""

from _submission import Player as _SubmissionPlayer

class Player(_SubmissionPlayer):
    def run(self, ct):
        round_number = ct.get_current_round()
        entity_id = ct.get_id()
        marker_started = ct.get_cpu_time_elapsed()
        print("{START_MARKER}:{{}}:{{}}".format(round_number, entity_id))
        marker_overhead = ct.get_cpu_time_elapsed() - marker_started
        try:
            super().run(ct)
        except Exception:
            print("{ERROR_MARKER}:{{}}:{{}}".format(round_number, entity_id))
            raise
        elapsed = ct.get_cpu_time_elapsed() - marker_overhead
        print("{END_MARKER}:{{}}:{{}}:{{}}".format(round_number, entity_id, elapsed))
'''

BASELINE = f'''"""Generated passive opponent for timing-compliance checks."""


class Player:
    def run(self, ct):
        if ct.get_current_round() > {SAMPLE_ROUNDS}:
            ct.resign("FCL_COMPLIANCE_BASELINE_END:v{VERSION}")
'''

RAW_COLUMNS = [
    "match_id",
    "tournament_id",
    "bot_id",
    "bot_name",
    "bot_commit",
    "map",
    "seed",
    "guard_tle_ms",
    "result",
    "match_status",
    "error",
    "turns",
    "samples",
    "min_turn_us",
    "p25_turn_us",
    "p50_turn_us",
    "p75_turn_us",
    "max_turn_us",
    "max_round",
    "timeouts",
    "bot_exceptions",
    "terminal_starts",
    "close_threshold_us",
    "limit_us",
    "host",
    "lsf_job",
    "finished_at",
]

SUMMARY_COLUMNS = [
    "bot_id",
    "bot_name",
    "bot_commit",
    "status",
    "matches_planned",
    "matches_completed",
    "matches_reported",
    "samples",
    "min_turn_us",
    "p25_turn_us",
    "p50_turn_us",
    "p75_turn_us",
    "max_turn_us",
    "timeouts",
    "bot_exceptions",
    "close_threshold_us",
    "limit_us",
]


def stage(specs: list[BotSpec], run_dir: Path, rating_mains: dict[str, str]) -> dict[str, str]:
    """Create instrumented copies and return bot_id -> wrapped main path relative to run_dir."""
    destination = run_dir / "compliance-stage"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    mains: dict[str, str] = {}
    for spec in specs:
        source = run_dir / rating_mains[spec.bot_id]
        target = destination / spec.bot_id
        shutil.copytree(source.parent, target)
        (target / "main.py").rename(target / "_submission.py")
        (target / "main.py").write_text(WRAPPER)
        mains[spec.bot_id] = str((target / "main.py").relative_to(run_dir))

    baseline = destination / BASELINE_ID
    baseline.mkdir()
    (baseline / "main.py").write_text(BASELINE)
    mains[BASELINE_ID] = str((baseline / "main.py").relative_to(run_dir))
    return mains


def result_status(record: dict) -> str:
    if record.get("status") != "ok":
        return "error"
    if int(record.get("compliance_timeouts", 0)):
        return "exceeded"
    maximum = int(record.get("compliance_max_turn_us", 0))
    if maximum > LIMIT_US:
        return "exceeded"
    if maximum >= CLOSE_US:
        return "close"
    if int(record.get("compliance_exceptions", 0)):
        return "bot_error"
    if not int(record.get("compliance_samples", 0)):
        return "no_report"
    return "pass"


def _turn_samples(record: dict) -> list[int]:
    values = record.get("compliance_turn_us", [])
    if not isinstance(values, list):
        return []
    return [int(value) for value in values]


def timing_percentiles(samples: list[int], timeouts: int = 0) -> dict[str, int | str]:
    """Return nearest-rank percentiles, treating watchdog timeouts as censored observations."""
    if not samples and not timeouts:
        return {
            "min_turn_us": "",
            "p25_turn_us": "",
            "p50_turn_us": "",
            "p75_turn_us": "",
            "max_turn_us": "",
        }
    ordered = sorted(samples)
    observations = len(ordered) + timeouts
    censored = f">{GUARD_TLE_MS * 1000}"

    def percentile(fraction: float) -> int | str:
        rank = 0 if fraction == 0 else math.ceil(fraction * observations) - 1
        return ordered[rank] if rank < len(ordered) else censored

    return {
        "min_turn_us": percentile(0),
        "p25_turn_us": percentile(0.25),
        "p50_turn_us": percentile(0.50),
        "p75_turn_us": percentile(0.75),
        "max_turn_us": percentile(1),
    }


def raw_row(record: dict, manifest: dict) -> dict:
    bots = {bot["bot_id"]: bot for bot in manifest["bots"]}
    bot = bots.get(record.get("bot_a", ""), {})
    samples = int(record.get("compliance_samples", 0))
    has_distribution = isinstance(record.get("compliance_turn_us"), list)
    timings = timing_percentiles(
        _turn_samples(record), int(record.get("compliance_timeouts", 0))
    ) if has_distribution else timing_percentiles([])
    # v3 and older result files retained only their maximum. Keep that evidence while leaving
    # the unrecoverable distribution fields blank.
    if timings["max_turn_us"] == "" and samples:
        timings["max_turn_us"] = record.get("compliance_max_turn_us", "")
    row = {
        "match_id": record.get("match_id", ""),
        "tournament_id": manifest["tournament_id"],
        "bot_id": record.get("bot_a", ""),
        "bot_name": bot.get("name", ""),
        "bot_commit": str(bot.get("commit", ""))[:7],
        "map": record.get("map", ""),
        "seed": record.get("seed", ""),
        "guard_tle_ms": record.get("tle", ""),
        "result": result_status(record),
        "match_status": record.get("status", ""),
        "error": record.get("error", ""),
        "turns": record.get("turns", ""),
        "samples": samples,
        **timings,
        "max_round": record.get("compliance_max_round", "") if samples else "",
        "timeouts": record.get("compliance_timeouts", 0),
        "bot_exceptions": record.get("compliance_exceptions", 0),
        "terminal_starts": record.get("compliance_terminal_starts", 0),
        "close_threshold_us": CLOSE_US,
        "limit_us": LIMIT_US,
        "host": record.get("host", ""),
        "lsf_job": record.get("lsf_job", ""),
        "finished_at": record.get("finished_at", ""),
    }
    return row


def _write(path: Path, columns: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_reports(run_dir: Path, records: list[dict], manifest: dict) -> tuple[Path, Path, int]:
    """Write durable per-match and per-bot compliance CSVs from available result records."""
    config = manifest.get("compliance") or {}
    target_ids = config.get("targets", [])
    planned = config.get("matches_per_bot", len(MAPS))
    bots = {bot["bot_id"]: bot for bot in manifest["bots"]}

    compliance_records = [record for record in records if record.get("kind") == "compliance"]
    raw = [raw_row(record, manifest) for record in compliance_records]
    raw.sort(key=lambda row: (row["bot_id"], row["map"], str(row["seed"])))
    raw_path = run_dir / "compliance_matches.csv"
    _write(raw_path, RAW_COLUMNS, raw)

    summary: list[dict] = []
    for bot_id in target_ids:
        bot = bots[bot_id]
        bot_rows = [row for row in raw if row["bot_id"] == bot_id]
        reported = [row for row in bot_rows if row["result"] in {"pass", "close", "exceeded"}]
        statuses = {row["result"] for row in bot_rows}
        if "exceeded" in statuses:
            status = "exceeded"
        elif "close" in statuses:
            status = "close"
        elif len(bot_rows) < planned:
            status = "pending"
        elif len(reported) < planned:
            status = "inconclusive"
        else:
            status = "pass"
        maxima = [
            int(row["max_turn_us"])
            for row in bot_rows
            if row["max_turn_us"] != "" and not str(row["max_turn_us"]).startswith(">")
        ]
        bot_records = [
            record for record in compliance_records if record.get("bot_a") == bot_id
        ]
        samples_us = [
            elapsed
            for record in bot_records
            for elapsed in _turn_samples(record)
        ]
        timeouts = sum(int(row["timeouts"]) for row in bot_rows)
        complete_distribution = bool(bot_records) and all(
            isinstance(record.get("compliance_turn_us"), list) for record in bot_records
        )
        timings = (
            timing_percentiles(samples_us, timeouts)
            if complete_distribution
            else timing_percentiles([])
        )
        if timings["max_turn_us"] == "" and maxima:
            timings["max_turn_us"] = max(maxima)
        summary.append(
            {
                "bot_id": bot_id,
                "bot_name": bot["name"],
                "bot_commit": bot["commit"][:7],
                "status": status,
                "matches_planned": planned,
                "matches_completed": len(bot_rows),
                "matches_reported": len(reported),
                "samples": sum(int(row["samples"]) for row in bot_rows),
                **timings,
                "timeouts": timeouts,
                "bot_exceptions": sum(int(row["bot_exceptions"]) for row in bot_rows),
                "close_threshold_us": CLOSE_US,
                "limit_us": LIMIT_US,
            }
        )

    summary_path = run_dir / "compliance.csv"
    _write(summary_path, SUMMARY_COLUMNS, summary)
    return raw_path, summary_path, len(raw)


def read_summary(run_dir: Path) -> list[dict]:
    path = run_dir / "compliance.csv"
    if not path.exists():
        return []
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))


def render(rows: list[dict]) -> str:
    if not rows:
        return "no compliance checks planned"
    widths = {
        "bot": max(3, max(len(row["bot_id"]) for row in rows)),
        "status": max(6, max(len(row["status"]) for row in rows)),
    }
    lines = [
        f"{'bot':<{widths['bot']}}  {'status':<{widths['status']}}  "
        f"{'turn time ms (min/p25/p50/p75/max)':>39}  samples  matches",
        f"{'-' * widths['bot']}  {'-' * widths['status']}  {'-' * 39}  -------  -------",
    ]
    for row in rows:
        values = []
        for key in ("min_turn_us", "p25_turn_us", "p50_turn_us", "p75_turn_us", "max_turn_us"):
            value = row.get(key, "")
            if str(value).startswith(">"):
                values.append(f">{int(str(value)[1:]) / 1000:.3f}")
            else:
                values.append(f"{int(value) / 1000:.3f}" if value else "-")
        timings = "/".join(values)
        matches = f"{row['matches_completed']}/{row['matches_planned']}"
        lines.append(
            f"{row['bot_id']:<{widths['bot']}}  {row['status']:<{widths['status']}}  "
            f"{timings:>39}  {row['samples']:>7}  {matches:>7}"
        )
    return "\n".join(lines)


def manifest_config(specs: list[BotSpec], map_paths: list[Path]) -> dict:
    return {
        "version": VERSION,
        "targets": [spec.bot_id for spec in specs],
        "maps": [label(path) for path in map_paths],
        "matches_per_bot": len(map_paths),
        "sample_rounds": SAMPLE_ROUNDS,
        "close_threshold_us": CLOSE_US,
        "limit_us": LIMIT_US,
        "guard_tle_ms": GUARD_TLE_MS,
    }
