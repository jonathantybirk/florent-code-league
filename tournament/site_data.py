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

from maps.generated.generate_maps import read_map
from tournament import plan as planning
from tournament import registry
from tournament import report
from tournament.maps import resolve as resolve_map
from tournament.outcome import score_a as evaluation_score_a
from tournament.rating import evaluate


def _read(path: Path) -> list[dict]:
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))


def _slug(bot_id: str) -> str:
    readable = "".join(character if character.isalnum() else "-" for character in bot_id)
    readable = "-".join(part for part in readable.split("-") if part).lower()[:52]
    digest = hashlib.sha256(bot_id.encode()).hexdigest()[:8]
    return f"{readable}-{digest}"


def _score(row: dict, bot_id: str) -> float:
    score_a = evaluation_score_a(row)
    return score_a if row["bot_a"] == bot_id else 1.0 - score_a


def _timing_value(value: str | None) -> int | str | None:
    if not value:
        return None
    return value if value.startswith(">") else int(value)


def _is_rating_match(row: dict) -> bool:
    """Historical rating rows predate the `kind` column and read back as an empty string."""
    return row.get("kind") in (None, "", "rating")


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


def _series(rows: list[dict], bot_ids: set[str]) -> dict[str, dict[str, int]]:
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_pair[tuple(sorted((row["bot_a"], row["bot_b"])))].append(row)

    result = {bot_id: {"wins": 0, "ties": 0, "losses": 0} for bot_id in bot_ids}
    for (left, right), pair_rows in by_pair.items():
        left_score = sum(_score(row, left) for row in pair_rows)
        midpoint = len(pair_rows) / 2
        if left_score > midpoint:
            result[left]["wins"] += 1
            result[right]["losses"] += 1
        elif left_score < midpoint:
            result[right]["wins"] += 1
            result[left]["losses"] += 1
        else:
            result[left]["ties"] += 1
            result[right]["ties"] += 1
    return result


def _ranking_rows(
    ratings: list[dict],
    metadata: dict[str, dict],
    compliance: dict[str, dict],
    series: dict[str, dict[str, int]],
) -> list[dict]:
    rows = []
    for rating in ratings:
        bot_id = rating["bot_id"]
        info = metadata.get(bot_id, {})
        timing = compliance.get(bot_id, {})
        tags = info.get("tags", [])
        rows.append(
            {
                "rank": int(rating["rank"]),
                "bot_id": bot_id,
                "name": info.get("name", rating.get("name") or bot_id.split("@")[0]),
                "commit": rating.get("commit") or info.get("commit", "")[:7],
                "slug": _slug(bot_id),
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
    return rows


def _benchmark(
    matches: list[dict],
    bot_ids: set[str],
    metadata: dict[str, dict],
    compliance: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    """Re-evaluate one field and return its match and ranking rows.

    Ratings are relative to the field: removing an entrant changes every remaining bot's mElo and
    Nash values.  Keeping this operation explicit prevents the website's timing toggle from being
    implemented as a misleading client-side filter of ratings calculated against a larger field.
    """
    scoped_matches = [
        row for row in matches if row["bot_a"] in bot_ids and row["bot_b"] in bot_ids
    ]
    rating_rows = report.records(evaluate(scoped_matches), metadata)
    return (
        scoped_matches,
        _ranking_rows(
            rating_rows,
            metadata,
            compliance,
            _series(scoped_matches, bot_ids),
        ),
    )


def _map_catalog(map_names: list[str]) -> list[dict]:
    result = []
    for name in map_names:
        [map_path] = resolve_map(name)
        game_map = read_map(map_path)
        result.append(
            {
                "name": name,
                "slug": name.replace("/", "--"),
                "width": game_map.width,
                "height": game_map.height,
                "terrain": game_map.rows,
                "cores": [
                    {"team": core.team, "x": core.x, "y": core.y}
                    for core in game_map.cores
                ],
            }
        )
    return result


def build(run_dir: Path, output_dir: Path) -> dict:
    ratings_path = run_dir / "ratings-distinct.csv"
    if not ratings_path.exists():
        ratings_path = run_dir / "ratings.csv"
    matches_path = run_dir / "matches-distinct.csv"
    if not matches_path.exists():
        matches_path = run_dir / "matches.csv"

    ratings = _read(ratings_path)
    rated_ids = {row["bot_id"] for row in ratings}
    benchmark_matches = [
        row
        for row in _read(matches_path)
        if row.get("status") == "ok"
        and row.get("winner")
        and row["bot_a"] in rated_ids
        and row["bot_b"] in rated_ids
        and _is_rating_match(row)
    ]
    # Keep detail documents stable for now. Their existing contract contains the explicitly typed
    # rows from the current pooled run; the benchmark additionally needs the older rating rows
    # whose pre-`kind` CSV cells are empty.
    detail_matches = [row for row in benchmark_matches if row.get("kind") == "rating"]
    metadata = _metadata(run_dir)
    compliance = _compliance(run_dir)
    all_matches, ranking_rows_including_over_time = _benchmark(
        benchmark_matches, rated_ids, metadata, compliance
    )
    within_time_ids = {
        bot_id
        for bot_id in rated_ids
        if compliance.get(bot_id, {}).get("status", "unknown") != "exceeded"
    }
    within_time_matches, ranking_rows = _benchmark(
        benchmark_matches, within_time_ids, metadata, compliance
    )

    rating_by_id = {
        row["bot_id"]: row for row in ranking_rows_including_over_time
    }
    slug_by_id = {bot_id: _slug(bot_id) for bot_id in rated_ids}
    rank_by_id = {
        row["bot_id"]: int(row["rank"])
        for row in ranking_rows_including_over_time
    }

    by_bot: dict[str, list[dict]] = defaultdict(list)
    for row in detail_matches:
        a, b = row["bot_a"], row["bot_b"]
        by_bot[a].append(row)
        by_bot[b].append(row)
    details_dir = output_dir / "bots"
    details_dir.mkdir(parents=True, exist_ok=True)
    expected_files = set()
    for ranking in ranking_rows_including_over_time:
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

    maps = sorted({row["map"] for row in benchmark_matches})
    map_catalog = _map_catalog(maps)
    maps_dir = output_dir / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    expected_map_files = set()
    for map_info in map_catalog:
        map_rows = [row for row in benchmark_matches if row["map"] == map_info["name"]]
        _, map_ranking_rows = _benchmark(
            map_rows, within_time_ids, metadata, compliance
        )
        _, map_ranking_rows_including_over_time = _benchmark(
            map_rows, rated_ids, metadata, compliance
        )
        filename = f"{map_info['slug']}.json"
        expected_map_files.add(filename)
        (maps_dir / filename).write_text(
            json.dumps(
                {
                    "map": map_info,
                    "rankings": map_ranking_rows,
                    "rankings_including_over_time": map_ranking_rows_including_over_time,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        )
    for path in maps_dir.glob("*.json"):
        if path.name not in expected_map_files:
            path.unlink()

    index = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_id": run_dir.name,
        "field": {
            "bots": len(within_time_ids),
            "matches": len(within_time_matches),
            "maps": len(maps),
            "games_per_pair": 2 * len(maps),
        },
        "field_including_over_time": {
            "bots": len(rated_ids),
            "matches": len(all_matches),
            "maps": len(maps),
            "games_per_pair": 2 * len(maps),
        },
        "maps": maps,
        "map_catalog": map_catalog,
        "rankings": ranking_rows,
        "rankings_including_over_time": ranking_rows_including_over_time,
        "duplicates": duplicate_rows,
        "methodology": {
            "primary": "pooled agent vs agent",
            "description": (
                "All maps are pooled into one smoothed head-to-head probability for each bot "
                "pair before mElo and Nash averaging."
            ),
            "nash": (
                "Nash averaging uses the square agent-vs-agent log-odds matrix built from those "
                "pooled probabilities."
            ),
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
