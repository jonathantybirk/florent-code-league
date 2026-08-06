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
from itertools import combinations
from pathlib import Path

from maps.generated.generate_maps import read_map
from tournament import plan as planning
from tournament import ages as ages_module
from tournament import maps as map_pools_module
from tournament import registry
from tournament.fairness import is_unfair
from tournament import report
from tournament.maps import is_secret
from tournament.maps import resolve as resolve_map
from tournament.outcome import score_a as evaluation_score_a
from tournament.rating import evaluate


POOL_LABELS = {
    "official": "New official maps",
    "legacy": "Old official maps",
    "secret": "Secret maps",
}


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


def _historical_duplicate_groups(run_dir: Path) -> list[tuple[str, ...]]:
    """Every duplicate group any run has ever recorded, current run included."""
    paths = set(planning.RUNS_ROOT.glob("*/duplicates.csv"))
    own = run_dir / "duplicates.csv"
    if own.exists():
        paths.add(own)
    groups: list[tuple[str, ...]] = []
    for path in sorted(paths):
        try:
            rows = _read(path)
        except OSError:
            continue
        for row in rows:
            members = (row.get("members") or "").split()
            if len(members) > 1:
                groups.append(tuple(members))
    return groups


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
                "first_published": info.get("first_published"),
                "slug": _slug(bot_id),
                "tags": tags,
                "unfair": is_unfair(tags, info.get("commit", ""), info.get("path", "")),
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


def _expected_elo(output_dir: Path) -> dict[str, dict]:
    """Online-ladder Elo projections, keyed by the same `name@commit` the rankings use.

    Produced by the live feed, which resolves each platform submission back to a repo commit by
    hashing its source. Only bots that have been submitted and have played a rated game with a
    split record get one, so this covers a handful of the field and nothing else -- an absent
    entry means "never measured", never "measured as average".

    Deliberately not pool-scoped: this number comes from the public ladder, not from any map pool
    on this page, and it does not change when the map checkboxes do.
    """
    path = output_dir / "live.json"
    if not path.exists():
        return {}
    try:
        feed = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    found: dict[str, dict] = {}
    for bot in feed.get("bots", []):
        estimate = bot.get("estimate")
        canonical = bot.get("canonical")
        if not estimate or not canonical or estimate.get("elo") is None:
            continue
        found[canonical] = {
            "elo": round(estimate["elo"], 1),
            "lo": round(estimate["elo_lo"], 1) if estimate.get("elo_lo") is not None else None,
            "hi": round(estimate["elo_hi"], 1) if estimate.get("elo_hi") is not None else None,
            "rated_games": bot.get("rated", 0),
            "versions": bot.get("versions", []),
            "active": bool(bot.get("is_active")),
        }
    return found


def _attach_expected_elo(rows: list[dict], lookup: dict[str, dict]) -> None:
    for row in rows:
        row["expected_elo"] = lookup.get(row["bot_id"])


def _map_catalog(map_names: list[str]) -> list[dict]:
    """Catalog entries for the website.

    Held-out maps publish their name and dimensions and nothing else. Terrain and core placement
    are exactly what the pool is protecting, and this bundle is served as a public static file --
    so the fields are emitted empty rather than filtered client-side.
    """
    result = []
    for name in map_names:
        [map_path] = resolve_map(name)
        game_map = read_map(map_path)
        secret = is_secret(name)
        result.append(
            {
                "name": name,
                "slug": name.replace("/", "--"),
                "secret": secret,
                "width": game_map.width,
                "height": game_map.height,
                "terrain": [] if secret else game_map.rows,
                "cores": []
                if secret
                else [
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
    duplicate_rows = []
    duplicate_path = run_dir / "duplicates.csv"
    if duplicate_path.exists():
        duplicate_rows = _read(duplicate_path)
    # A pinned sha only says when the branch moved, so every row also carries the date its code
    # was first published. Duplicate groups collapse to the oldest member: the survivor stands
    # for the whole group, and dating it by its own commit would make a re-run of old work look
    # new. Carried on the metadata so it reaches map-scoped rows too, which show commits as well.
    # Groups come from every run that ever recorded one, not just this one. A behavioural
    # duplicate's original is usually the member that got pruned, so it is absent from the
    # current field and from the current duplicates.csv -- and its date is the one worth having.
    # `metadata` spans all historical manifests, so those bots can still be dated.
    ages = ages_module.apply_duplicate_groups(
        ages_module.resolve(metadata), _historical_duplicate_groups(run_dir)
    )
    for bot_id, record in ages.items():
        if bot_id in metadata:
            metadata[bot_id] = {**metadata[bot_id], "first_published": record}
    compliance = _compliance(run_dir)
    within_time_ids = {
        bot_id
        for bot_id in rated_ids
        if compliance.get(bot_id, {}).get("status", "unknown") != "exceeded"
    }
    # Same predicate that decides the row's `unfair` badge: a tag-only test would leave the
    # atlas-importing bots inside the fair field while the page marks them unfair.
    fair_ids = {
        bot_id
        for bot_id in rated_ids
        if not is_unfair(
            metadata.get(bot_id, {}).get("tags", []),
            metadata.get(bot_id, {}).get("commit", ""),
            metadata.get(bot_id, {}).get("path", ""),
        )
    }
    # Leaderboard v2: strategies that exceeded the 10 ms turn limit are excluded from every
    # published field and from the detail documents. Their raw match rows stay in the run CSVs
    # on x/tournament for anyone who wants them.
    benchmark_matches = [
        row
        for row in benchmark_matches
        if row["bot_a"] in within_time_ids and row["bot_b"] in within_time_ids
    ]
    detail_matches = [row for row in benchmark_matches if row.get("kind") == "rating"]
    # The fairness switch on the page narrows the field, and a rating is only meaningful against
    # the field it was computed over. Filtering a larger field's numbers client-side would show,
    # say, a fair bot's mElo earned partly against unfair opponents that are no longer on screen.
    # So each combination is evaluated separately here.
    fields = {
        "": within_time_ids,
        "_fair": within_time_ids & fair_ids,
    }
    # A map pool is the second thing a rating is relative to, and for the same reason as the
    # field: Nash averaging asks "unexploitable against which opponents, on which maps". Pooling
    # the held-out maps into the official numbers would silently redefine every published rating,
    # so each pool is evaluated separately and the page picks one.
    #
    # There are three pools now, and the two official ones overlap: atoll, hive and jackpot are in
    # both. Selecting several pools therefore means their union, deduplicated -- a map played once
    # is one map, however many pools claim it -- so the combinations are built from label sets
    # rather than by concatenating pools.
    map_labels = sorted({row["map"] for row in benchmark_matches})
    covered: dict[str, list[str]] = {pool: [] for pool in map_pools_module.POOLS}
    orphans = []
    for name in map_labels:
        owners = map_pools_module.pools_of(name)
        if not owners:
            orphans.append(name)
        for pool in owners:
            covered[pool].append(name)
    if orphans:
        # A map nobody claims would vanish from every published pool while still sitting in the
        # match CSVs, which is the kind of gap that reads as a rating change months later.
        print(
            f"  warning: {len(orphans)} played map(s) belong to no pool and are excluded from "
            f"every published rating: {', '.join(orphans)}"
        )
    available = [pool for pool in map_pools_module.POOLS if covered[pool]]
    if not available:
        raise RuntimeError("no played map belongs to a known pool; refusing to publish")

    # The headline ladder moves to the current competition pool only once that pool has actually
    # been played end to end. Until then it stays on whichever pool has the most evidence, because
    # publishing "rank 1 of 144" off the three maps the new pool happens to share with the old one
    # would look like a full rating and be nothing of the kind.
    # Never the held-out pool, however complete it is: those ratings are earned on terrain chosen
    # to be unlike the competition's, and making them the headline would misdescribe the ladder.
    candidates = [pool for pool in available if pool != "secret"] or available
    complete = [
        pool for pool in candidates
        if len(covered[pool]) == len(map_pools_module.pool_labels(pool))
    ]
    primary = complete[0] if complete else max(candidates, key=lambda p: len(covered[p]))

    def _pool_key(parts: tuple[str, ...]) -> str:
        return "_" + "_".join(parts)

    pools: dict[str, list[str]] = {"": sorted(covered[primary])}
    pool_parts: dict[str, tuple[str, ...]] = {"": (primary,)}
    for size in range(1, len(available) + 1):
        for parts in combinations(available, size):
            union = sorted({name for pool in parts for name in covered[pool]})
            pools[_pool_key(parts)] = union
            pool_parts[_pool_key(parts)] = parts

    # Per-map ratings come first: a bot's Nash-core map count is an aggregate over them, so the
    # pooled rows cannot be finished until every map has been solved.
    map_catalog = _map_catalog(map_labels)
    map_rankings_by_name: dict[str, dict[str, list[dict]]] = {}
    core_maps: dict[str, dict[str, set[str]]] = {suffix: {} for suffix in fields}
    for map_info in map_catalog:
        map_rows = [row for row in benchmark_matches if row["map"] == map_info["name"]]
        per_field = {
            suffix: _benchmark(map_rows, ids, metadata, compliance)[1]
            for suffix, ids in fields.items()
        }
        map_rankings_by_name[map_info["name"]] = per_field
        for suffix, rows in per_field.items():
            core_maps[suffix][map_info["name"]] = {
                row["bot_id"] for row in rows if row["nash_prob"] > 0
            }

    # finalise() refuses to publish an incomplete matrix, because an unplayed pair enters A as 0
    # and is then indistinguishable from a measured draw. The same has to hold per pool: a pool
    # whose field never finished playing would otherwise publish imputed draws as results. Bots
    # with no matches in the pool at all are simply absent from it, which is honest; the failure
    # this guards is a bot that played some of the pool's opponents but not all of them.
    incomplete: dict[str, list[tuple[str, str]]] = {}
    for pool_suffix, pool_labels in pools.items():
        pool_set = set(pool_labels)
        pool_rows = [row for row in benchmark_matches if row["map"] in pool_set]
        present = sorted({row["bot_a"] for row in pool_rows} | {row["bot_b"] for row in pool_rows})
        played = {frozenset((row["bot_a"], row["bot_b"])) for row in pool_rows}
        gaps = [
            (left, right)
            for index, left in enumerate(present)
            for right in present[index + 1:]
            if frozenset((left, right)) not in played
        ]
        if gaps:
            incomplete[pool_suffix] = gaps
    for pool_suffix, gaps in incomplete.items():
        print(
            f"  skipping map pool {pool_suffix or 'standard'!r}: {len(gaps)} pair(s) among its "
            f"own entrants have never played, so its ratings would be imputed"
        )
        for left, right in gaps[:5]:
            print(f"    {left}  vs  {right}")
        pools.pop(pool_suffix)
        pool_parts.pop(pool_suffix, None)
    if "" not in pools:
        raise RuntimeError("the primary map pool is incomplete; refusing to publish")

    # Seven selectable combinations over three pools, and several of them coincide while the
    # current pool is only partly played -- `official + legacy` is the same set of maps as
    # `legacy` until the twelve new maps have been run, and the primary pool's "" key is by
    # construction a second name for one of them. Nash averaging over 144 bots is the expensive
    # part of this build, so identical label sets are solved once, and only the first key of each
    # set carries its rankings into the bundle: publishing four byte-identical 144-row tables
    # tripled index.json for nothing.
    canonical: dict[frozenset[str], str] = {}
    aliases: dict[str, str] = {}
    for pool_suffix, pool_labels in pools.items():
        signature = frozenset(pool_labels)
        if signature in canonical:
            aliases[pool_suffix] = canonical[signature]
        else:
            canonical[signature] = pool_suffix
    benchmarks: dict[str, tuple[list[dict], list[dict]]] = {}
    solved: dict[tuple[frozenset[str], str], tuple[list[dict], list[dict]]] = {}
    for pool_suffix, pool_labels in pools.items():
        pool_set = frozenset(pool_labels)
        pool_matches = [row for row in benchmark_matches if row["map"] in pool_set]
        for field_suffix, ids in fields.items():
            cached = solved.get((pool_set, field_suffix))
            if cached is None:
                matches, rows = _benchmark(pool_matches, ids, metadata, compliance)
                for row in rows:
                    # Counted within the selected pool, against the same field: "core on 7 of
                    # these 22 maps" only means anything if both halves describe the table being
                    # read.
                    row["nash_core_maps"] = sum(
                        row["bot_id"] in core_maps[field_suffix][name] for name in pool_labels
                    )
                    row["pool_maps"] = len(pool_labels)
                cached = (matches, rows)
                solved[(pool_set, field_suffix)] = cached
            benchmarks[f"{pool_suffix}{field_suffix}"] = cached

    # Stamped on every table, pooled and per-map alike, because it is a property of the bot rather
    # than of the field or the pool it is being read next to.
    expected_elo = _expected_elo(output_dir)
    for _, rows in benchmarks.values():
        _attach_expected_elo(rows, expected_elo)
    for per_field in map_rankings_by_name.values():
        for rows in per_field.values():
            _attach_expected_elo(rows, expected_elo)

    within_time_matches, ranking_rows = benchmarks[""]

    rating_by_id = {row["bot_id"]: row for row in ranking_rows}
    rank_by_id = {row["bot_id"]: int(row["rank"]) for row in ranking_rows}

    by_bot: dict[str, list[dict]] = defaultdict(list)
    for row in detail_matches:
        a, b = row["bot_a"], row["bot_b"]
        by_bot[a].append(row)
        by_bot[b].append(row)
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

    maps_dir = output_dir / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    expected_map_files = set()
    for map_info in map_catalog:
        map_rankings = {
            f"rankings{suffix}": rows
            for suffix, rows in map_rankings_by_name[map_info["name"]].items()
        }
        filename = f"{map_info['slug']}.json"
        expected_map_files.add(filename)
        (maps_dir / filename).write_text(
            json.dumps(
                {
                    "map": map_info,
                    **map_rankings,
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
        # Bumped when the roster or engine changes enough that ratings across the boundary are
        # not comparable. v2 = 2026-08-04: fcode 2.3.4 turret balance patch, 21 bots retired,
        # over-time strategies dropped from every published field. v3 = 2026-08-06: the map pool
        # was replaced, and the field cut from 144 to those that earned a place (see
        # tournament/retired.json for the rule and the list).
        "leaderboard_version": 3,
        **{
            f"field{pool_suffix}{field_suffix}": {
                "bots": len(benchmarks[f"{pool_suffix}{field_suffix}"][1]),
                "matches": len(benchmarks[f"{pool_suffix}{field_suffix}"][0]),
                "maps": len(pool_labels),
                "games_per_pair": 2 * len(pool_labels),
            }
            for pool_suffix, pool_labels in pools.items()
            for field_suffix in fields
        },
        "maps": map_labels,
        "map_catalog": map_catalog,
        # Every pool the bundle can actually answer for, plus which of the three components each
        # one unions. The page builds its key from the checkboxes and looks it up here, so a pool
        # that got dropped as incomplete simply cannot be selected.
        "map_pools": [
            {
                "id": pool_suffix,
                "label": " + ".join(POOL_LABELS[part] for part in pool_parts[pool_suffix]),
                "components": list(pool_parts[pool_suffix]),
                "secret": "secret" in pool_parts[pool_suffix],
                "maps": pool_labels,
                # Present when this selection covers exactly the same maps as another, and so
                # reads its rankings rather than carrying its own copy.
                **({"alias_of": aliases[pool_suffix]} if pool_suffix in aliases else {}),
            }
            for pool_suffix, pool_labels in pools.items()
            if pool_suffix != ""
        ],
        "pool_aliases": aliases,
        # Which combination the headline numbers are computed over, and which the page should
        # start on. Not always the current competition pool: see the `primary` choice above.
        "default_pool": _pool_key((primary,)),
        "pool_coverage": {
            pool: {
                "played": len(covered[pool]),
                # The held-out pool is defined by what is on disk, and the machine building this
                # bundle need not hold it -- in which case the matches themselves are the only
                # evidence of how big it is.
                "defined": max(
                    len(map_pools_module.pool_labels(pool)), len(covered[pool])
                ),
                "label": POOL_LABELS[pool],
            }
            for pool in map_pools_module.POOLS
        },
        **{
            f"rankings{suffix}": benchmark[1]
            for suffix, benchmark in benchmarks.items()
            if suffix.removesuffix("_fair") not in aliases
        },
        "duplicates": duplicate_rows,
        "methodology": {
            "primary": "pooled agent vs agent",
            "description": (
                "All maps in the selected pool are pooled into one smoothed head-to-head "
                "probability for each bot pair before mElo and Nash averaging."
            ),
            "nash": (
                "Nash averaging uses the square agent-vs-agent log-odds matrix built from those "
                "pooled probabilities."
            ),
            "sides": "Every pair plays every map in the pool twice, swapping Gold and Silver.",
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
