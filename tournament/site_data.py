"""Generate the static data bundle consumed by lucasrgpedersen.com/botrankings.

The ranking index is intentionally small. Detailed opponent, map and matchup data is split into
one JSON file per bot so the browser only downloads it when somebody opens that bot.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from tournament import plan as planning
from tournament import registry


def _read(path: Path) -> list[dict]:
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))


def _slug(bot_id: str) -> str:
    readable = "".join(character if character.isalnum() else "-" for character in bot_id)
    readable = "-".join(part for part in readable.split("-") if part).lower()[:52]
    digest = hashlib.sha256(bot_id.encode()).hexdigest()[:8]
    return f"{readable}-{digest}"


def _score(row: dict, bot_id: str) -> float:
    score_a = float(row["score_a"])
    return score_a if row["bot_a"] == bot_id else 1.0 - score_a


def _timing_value(value: str | None) -> int | str | None:
    if not value:
        return None
    return value if value.startswith(">") else int(value)


def _record(rows: list[dict], bot_id: str) -> dict:
    scores = [_score(row, bot_id) for row in rows]
    wins = sum(score == 1.0 for score in scores)
    draws = sum(score == 0.5 for score in scores)
    losses = len(scores) - wins - draws
    return {
        "games": len(scores),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "win_rate": round(sum(scores) / len(scores), 4) if scores else 0.0,
    }


def _game(row: dict, bot_id: str) -> dict:
    side = "gold" if row["bot_a"] == bot_id else "silver"
    opponent_id = row["bot_b"] if side == "gold" else row["bot_a"]
    score = _score(row, bot_id)
    return {
        "side": side,
        "opponent_id": opponent_id,
        "result": "win" if score == 1.0 else "draw" if score == 0.5 else "loss",
        "turns": int(row["turns"]),
        "win_condition": row.get("win_condition", ""),
        "match_id": row["match_id"],
    }


def _metadata(run_dir: Path) -> dict[str, dict]:
    """Collect historical manifests, then let the current registry override their metadata."""
    found: dict[str, dict] = {}
    for manifest in sorted(planning.RUNS_ROOT.glob("*/manifest.json")):
        try:
            bots = json.loads(manifest.read_text())["bots"]
        except (KeyError, json.JSONDecodeError):
            continue
        for bot in bots:
            found[bot["bot_id"]] = bot
    own_manifest = run_dir / "manifest.json"
    if own_manifest.exists():
        for bot in json.loads(own_manifest.read_text()).get("bots", []):
            found[bot["bot_id"]] = bot
    try:
        for spec in registry.load(validate=False):
            found[spec.bot_id] = {
                "bot_id": spec.bot_id,
                "name": spec.name,
                "commit": spec.commit,
                "path": spec.path,
                "tags": list(spec.tags),
            }
    except (FileNotFoundError, ValueError):
        pass
    return found


def _compliance(run_dir: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    freshness: dict[str, tuple[int, int]] = {}
    paths = set(planning.RUNS_ROOT.glob("*/compliance.csv"))
    own = run_dir / "compliance.csv"
    if own.exists():
        paths.add(own)
    for path in sorted(paths):
        version = 0
        manifest_path = path.parent / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text())
            version = int((manifest.get("compliance") or {}).get("version", 0))
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        key = (version, path.stat().st_mtime_ns)
        for row in _read(path):
            bot_id = row["bot_id"]
            if key >= freshness.get(bot_id, (-1, -1)):
                found[bot_id] = {**row, "version": version}
                freshness[bot_id] = key
    return found


def build(run_dir: Path, output_dir: Path) -> dict:
    ratings_path = run_dir / "ratings-distinct.csv"
    if not ratings_path.exists():
        ratings_path = run_dir / "ratings.csv"
    matches_path = run_dir / "matches-distinct.csv"
    if not matches_path.exists():
        matches_path = run_dir / "matches.csv"

    ratings = _read(ratings_path)
    rated_ids = {row["bot_id"] for row in ratings}
    matches = [
        row
        for row in _read(matches_path)
        if row.get("status") == "ok"
        and row.get("winner")
        and row["bot_a"] in rated_ids
        and row["bot_b"] in rated_ids
        and row.get("kind", "rating") == "rating"
    ]
    metadata = _metadata(run_dir)
    compliance = _compliance(run_dir)
    rating_by_id = {row["bot_id"]: row for row in ratings}
    slug_by_id = {bot_id: _slug(bot_id) for bot_id in rated_ids}
    rank_by_id = {row["bot_id"]: int(row["rank"]) for row in ratings}

    by_bot: dict[str, list[dict]] = defaultdict(list)
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in matches:
        a, b = row["bot_a"], row["bot_b"]
        by_bot[a].append(row)
        by_bot[b].append(row)
        by_pair[tuple(sorted((a, b)))].append(row)

    # Series records are calculated once and surfaced in the ranking table.
    series = {bot_id: {"wins": 0, "ties": 0, "losses": 0} for bot_id in rated_ids}
    for (left, right), pair_rows in by_pair.items():
        left_score = sum(_score(row, left) for row in pair_rows)
        midpoint = len(pair_rows) / 2
        if left_score > midpoint:
            series[left]["wins"] += 1
            series[right]["losses"] += 1
        elif left_score < midpoint:
            series[right]["wins"] += 1
            series[left]["losses"] += 1
        else:
            series[left]["ties"] += 1
            series[right]["ties"] += 1

    ranking_rows = []
    for rating in ratings:
        bot_id = rating["bot_id"]
        info = metadata.get(bot_id, {})
        timing = compliance.get(bot_id, {})
        tags = info.get("tags", [])
        ranking_rows.append(
            {
                "rank": int(rating["rank"]),
                "bot_id": bot_id,
                "name": info.get("name", rating.get("name") or bot_id.split("@")[0]),
                "commit": rating.get("commit") or info.get("commit", "")[:7],
                "slug": slug_by_id[bot_id],
                "tags": tags,
                "unfair": "unfair" in tags,
                "games": int(rating["games"]),
                "wins": int(rating["wins"]),
                "draws": int(rating["draws"]),
                "losses": int(rating["losses"]),
                "win_rate": float(rating["win_rate"]),
                "melo_r": float(rating["melo_r"]),
                "melo_r_elo": float(rating["melo_r_elo"]),
                "nash_prob": float(rating["nash_prob"]),
                "nash_average": float(rating["nash_average"]),
                "nash_rank": int(rating["nash_rank"]),
                "rank_delta": int(rating["rank_delta"]),
                "aggregate_rank": int(rating.get("aggregate_rank", rating["rank"])),
                "aggregate_melo_r": float(rating.get("aggregate_melo_r", rating["melo_r"])),
                "aggregate_melo_r_elo": float(
                    rating.get("aggregate_melo_r_elo", rating["melo_r_elo"])
                ),
                "aggregate_nash_prob": float(
                    rating.get("aggregate_nash_prob", rating["nash_prob"])
                ),
                "aggregate_nash_average": float(
                    rating.get("aggregate_nash_average", rating["nash_average"])
                ),
                "aggregate_nash_rank": int(
                    rating.get("aggregate_nash_rank", rating["nash_rank"])
                ),
                "aggregate_rank_delta": int(
                    rating.get("aggregate_rank_delta", rating["rank_delta"])
                ),
                "series": series[bot_id],
                "compliance": {
                    "status": timing.get("status", "unknown"),
                    "version": int(timing.get("version", 0)),
                    "samples": int(timing["samples"]) if timing.get("samples") else 0,
                    "min_turn_us": _timing_value(timing.get("min_turn_us")),
                    "p25_turn_us": _timing_value(timing.get("p25_turn_us")),
                    "p50_turn_us": _timing_value(timing.get("p50_turn_us")),
                    "p75_turn_us": _timing_value(timing.get("p75_turn_us")),
                    "max_turn_us": _timing_value(timing.get("max_turn_us")),
                    "timeouts": int(timing["timeouts"]) if timing.get("timeouts") else 0,
                },
            }
        )

    details_dir = output_dir / "bots"
    details_dir.mkdir(parents=True, exist_ok=True)
    expected_files = set()
    for ranking in ranking_rows:
        bot_id = ranking["bot_id"]
        bot_rows = by_bot[bot_id]
        opponent_groups: dict[str, list[dict]] = defaultdict(list)
        map_groups: dict[str, list[dict]] = defaultdict(list)
        matchup_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for row in bot_rows:
            opponent = row["bot_b"] if row["bot_a"] == bot_id else row["bot_a"]
            opponent_groups[opponent].append(row)
            map_groups[row["map"]].append(row)
            matchup_groups[(opponent, row["map"])].append(row)

        opponents = []
        for opponent_id, group in opponent_groups.items():
            gold = [row for row in group if row["bot_a"] == bot_id]
            silver = [row for row in group if row["bot_b"] == bot_id]
            overall = _record(group, bot_id)
            opponents.append(
                {
                    "opponent_id": opponent_id,
                    "name": rating_by_id[opponent_id].get("name")
                    or opponent_id.split("@")[0],
                    "rank": rank_by_id[opponent_id],
                    **overall,
                    "gold": _record(gold, bot_id),
                    "silver": _record(silver, bot_id),
                    "series": "win"
                    if overall["wins"] + overall["draws"] / 2 > overall["games"] / 2
                    else "loss"
                    if overall["wins"] + overall["draws"] / 2 < overall["games"] / 2
                    else "tie",
                }
            )
        opponents.sort(key=lambda row: (row["rank"], row["opponent_id"]))

        maps = []
        for map_name, group in map_groups.items():
            gold = [row for row in group if row["bot_a"] == bot_id]
            silver = [row for row in group if row["bot_b"] == bot_id]
            maps.append(
                {
                    "map": map_name,
                    **_record(group, bot_id),
                    "gold": _record(gold, bot_id),
                    "silver": _record(silver, bot_id),
                }
            )
        maps.sort(key=lambda row: row["map"])

        matchups = []
        for (opponent_id, map_name), group in matchup_groups.items():
            matchups.append(
                {
                    "opponent_id": opponent_id,
                    "map": map_name,
                    **_record(group, bot_id),
                    "games_detail": sorted(
                        (_game(row, bot_id) for row in group), key=lambda row: row["side"]
                    ),
                }
            )
        matchups.sort(key=lambda row: (rank_by_id[row["opponent_id"]], row["map"]))

        detail = {
            "bot": ranking,
            "opponents": opponents,
            "maps": maps,
            "matchups": matchups,
        }
        filename = f"{ranking['slug']}.json"
        expected_files.add(filename)
        (details_dir / filename).write_text(
            json.dumps(detail, separators=(",", ":"), ensure_ascii=False) + "\n"
        )

    # Remove stale detail documents when a duplicate disappears from the canonical field.
    for path in details_dir.glob("*.json"):
        if path.name not in expected_files:
            path.unlink()

    duplicate_rows = []
    duplicate_path = run_dir / "duplicates.csv"
    if duplicate_path.exists():
        duplicate_rows = _read(duplicate_path)

    maps = sorted({row["map"] for row in matches})
    index = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_id": run_dir.name,
        "field": {
            "bots": len(rated_ids),
            "matches": len(matches),
            "maps": len(maps),
            "games_per_pair": 2 * len(maps),
        },
        "maps": maps,
        "rankings": ranking_rows,
        "duplicates": duplicate_rows,
        "methodology": {
            "primary": "bot + map tasks",
            "description": "Each (opponent bot, map) is a separate task after combining the two side-swapped games.",
            "nash": "The default is agent-vs-task Nash averaging; aggregate-over-maps ratings remain available as a view switch.",
            "sides": "Every pair plays every official map twice, swapping Gold and Silver.",
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.json").write_text(
        json.dumps(index, separators=(",", ":"), ensure_ascii=False) + "\n"
    )
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    index = build(args.run_dir.resolve(), args.output.resolve())
    print(
        f"wrote {index['field']['bots']} bots and {index['field']['matches']} matches "
        f"to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
