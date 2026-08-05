"""Build the live ladder feed consumed by lucasrgpedersen.com/botrankings/live.

This is a different animal from `site_data.py`. That module publishes the *offline* tournament --
our own bots played against each other on our own maps, scored with mElo and Nash. This one
publishes the *online* ladder: the real platform, real opponents, real Elo.

Three things make the online ladder worth its own feed:

- The platform pairs teams every ten minutes and nobody sees the schedule. Reconstructing what we
  actually played, and against which build of the opponent, is only possible from the match log.
- Opponents ship new bots constantly -- Pivot used nine versions in twelve hours -- so a raw win
  rate silently compares our versions against different opposition. Everything here is broken out
  by the opponent's exact submission version.
- Our own versions get swapped in and out within minutes, so most of them have single-digit
  samples. Every estimate therefore carries an interval, and versions that cannot support an
  estimate say so rather than showing a number.

The rating model is not a guess. `tournament/README.md` records the derivation; briefly, the
platform runs plain Elo with K=32 over a five-game series scored as (games won / 5), and that
reproduces all 12255 observed rating deltas to the last decimal place. Because the model is exact,
a version's equilibrium rating is exactly its Elo-scale strength: the fixed point of the update is
the rating at which expected score equals Elo-expected score, which happens only at the true
strength, independent of who it gets paired against. So the projection is one maximum-likelihood
parameter per version, not a simulation of the ladder.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE = REPO_ROOT.parent / "portfolio"
DEFAULT_CACHE = REPO_ROOT / "tournament" / "live-cache.jsonl"

# The platform's rating rule, verified against every rated match since Aug 1 (zero residual).
K_FACTOR = 32
SERIES_GAMES = 5

# Matchmaking, reverse-engineered from 12237 pairings across 662 scheduler ticks. Teams are sorted
# by rating, cut into consecutive groups, and paired uniformly at random inside each group. Group
# size 8 fits the observed rank-distance distribution to a total-variation distance of 0.033; the
# rare pairings out to rank distance 11 come from how the final short group is absorbed.
SCHEDULER_PERIOD_MINUTES = 10
PAIRING_GROUP_SIZE = 8

# A version needs enough games before a strength estimate means anything. Below this we publish the
# raw record and an explicit null rather than an interval nobody should read.
MIN_GAMES_FOR_ESTIMATE = 25
BOOTSTRAP_RESAMPLES = 400

# "Currently in use" for an opponent build. One scheduler period is too tight -- a team that drew a
# different pairing simply would not appear -- and a whole day is long enough to include two bots
# ago. An hour is about six scheduler ticks.
ACTIVE_WINDOW_MINUTES = 60


def _api():
    """Import lazily so the module can be imported (and tested) without credentials present."""
    from fcode.api import api_get

    return api_get


def _fetch_page(api_get, params: dict[str, str]) -> tuple[list[dict], str | None]:
    data = api_get("/api/matches", params)
    return data.get("matches", []) or [], data.get("nextCursor")


def _fetch_until(api_get, params: dict[str, str], stop_ids: set[str], max_pages: int) -> list[dict]:
    """Page backwards through the match log, stopping at the first already-known match.

    The log is append-only and ordered by completion, so a match we have seen means every older
    page is already cached. `max_pages` bounds a cold start; a warm run costs one page.
    """
    out: list[dict] = []
    cursor: str | None = None
    for _ in range(max_pages):
        page_params = dict(params)
        if cursor:
            page_params["cursor"] = cursor
        page, cursor = _fetch_page(api_get, page_params)
        if not page:
            break
        for match in page:
            if match["id"] in stop_ids:
                return out
            out.append(match)
        if not cursor or len(page) < int(params.get("limit", "100")):
            break
    return out


def _load_cache(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _save_cache(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    tmp.replace(path)


def _parse(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _orient(match: dict, team_id: str) -> dict:
    """Rewrite a match from our team's point of view; A/B is just which slot the API used."""
    a = match["teamAId"] == team_id
    return {
        "id": match["id"],
        "t": match["completedAt"],
        "created": match["createdAt"],
        "kind": match["triggeredBy"],
        "ver": match["teamAVersion"] if a else match["teamBVersion"],
        "opp_id": match["teamBId"] if a else match["teamAId"],
        "opp": match["teamBName"] if a else match["teamAName"],
        "opp_ver": match["teamBVersion"] if a else match["teamAVersion"],
        "opp_rating": match["ratingBBefore"] if a else match["ratingABefore"],
        "our_rating": match["ratingABefore"] if a else match["ratingBBefore"],
        "gf": match["scoreA"] if a else match["scoreB"],
        "ga": match["scoreB"] if a else match["scoreA"],
        "win": match["winnerId"] == team_id,
        "delta": match["eloDeltaA"] if a else match["eloDeltaB"],
    }


# --------------------------------------------------------------------------------------------
# Strength estimation
# --------------------------------------------------------------------------------------------


def _expected(our_strength: float, opponent_rating: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((opponent_rating - our_strength) / 400.0))


def _fit_strength(games: list[tuple[float, int, int]]) -> float | None:
    """Maximum-likelihood Elo-scale strength from (opponent_rating, wins, losses) rows.

    One parameter, log-likelihood strictly concave in it, so bisection on the score function is
    both sufficient and immune to the step-size problems Newton has when a version has swept or
    been swept. Returns None when the record is all wins or all losses, where the MLE runs off to
    infinity and any finite number we printed would be an artefact of where we truncated.
    """
    total_wins = sum(w for _, w, _ in games)
    total_losses = sum(loss for _, _, loss in games)
    if total_wins == 0 or total_losses == 0:
        return None

    def score(strength: float) -> float:
        # d/dS of the log-likelihood, up to the positive constant ln(10)/400.
        return sum(w - (w + loss) * _expected(strength, r) for r, w, loss in games)

    low, high = 0.0, 4000.0
    for _ in range(60):
        mid = (low + high) / 2.0
        if score(mid) > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _bootstrap_strength(matches: list[dict], resamples: int, seed: int) -> list[float]:
    """Cluster bootstrap over matches, not games.

    Games inside one series share a map and an opponent build, so they are nowhere near
    independent. Resampling whole series keeps that correlation intact; resampling games would
    shrink the interval by roughly the square root of the series length and lie about it.
    """
    rng = random.Random(seed)
    n = len(matches)
    draws: list[float] = []
    for _ in range(resamples):
        picked = [matches[rng.randrange(n)] for _ in range(n)]
        rows = defaultdict(lambda: [0, 0])
        for match in picked:
            cell = rows[round(match["opp_rating"], 3)]
            cell[0] += match["gf"]
            cell[1] += match["ga"]
        fit = _fit_strength([(r, w, loss) for r, (w, loss) in rows.items()])
        if fit is not None:
            draws.append(fit)
    return sorted(draws)


def _interval(draws: list[float], lo: float = 0.05, hi: float = 0.95) -> tuple[float, float] | None:
    if len(draws) < 20:
        return None
    return draws[int(lo * len(draws))], draws[min(len(draws) - 1, int(hi * len(draws)))]


def _field_score(strength: float, ratings: list[float]) -> float:
    """Expected share of games won against a field, averaged over its members."""
    if not ratings:
        return float("nan")
    return sum(_expected(strength, r) for r in ratings) / len(ratings)


def _pairing_neighbourhood(rating: float, field: list[float]) -> list[float]:
    """The opponents a team at `rating` would actually be scheduled against.

    Pairing is inside a group of `PAIRING_GROUP_SIZE` consecutive teams in rating order, so the
    reachable set is the neighbours within one group width -- not the whole ladder. Modelling it
    as the nearest `PAIRING_GROUP_SIZE - 1` is the right average over where in its group a team
    happens to sit.
    """
    if not field:
        return []
    return sorted(field, key=lambda r: abs(r - rating))[: PAIRING_GROUP_SIZE - 1]


# --------------------------------------------------------------------------------------------
# Feed assembly
# --------------------------------------------------------------------------------------------


def build(site_repo: Path, cache_path: Path = DEFAULT_CACHE, cold_pages: int = 40) -> dict:
    api_get = _api()
    from fcode.auth import load_credentials

    creds = load_credentials()
    if not creds or not creds.get("team"):
        raise RuntimeError("not authenticated, or the stored credentials carry no team")
    team = creds["team"]
    team_id = team["id"]

    cached = _load_cache(cache_path)
    known = {row["id"] for row in cached}
    fresh = _fetch_until(
        api_get, {"teamIds": team_id, "limit": "100"}, known, max_pages=cold_pages
    )
    allrows = fresh + cached
    if fresh:
        _save_cache(cache_path, allrows)

    ours = [_orient(m, team_id) for m in allrows if m.get("status") == "complete"]
    ours.sort(key=lambda r: r["t"], reverse=True)

    # The global feed, for what opponents are running right now. Only the last hour is needed, and
    # the ladder produces roughly 200 matches an hour, so three pages is ample headroom.
    recent_global, cursor = [], None
    horizon = (datetime.now(UTC) - timedelta(minutes=ACTIVE_WINDOW_MINUTES)).isoformat()
    for _ in range(4):
        params = {"limit": "100"}
        if cursor:
            params["cursor"] = cursor
        page, cursor = _fetch_page(api_get, params)
        if not page:
            break
        recent_global.extend(page)
        if page[-1]["completedAt"] < horizon or not cursor:
            break
    recent_global = [m for m in recent_global if m["completedAt"] >= horizon]

    ladder = api_get("/api/ladder") or []
    if isinstance(ladder, dict):
        ladder = ladder.get("teams", []) or []
    rank_of = {t["teamId"]: i + 1 for i, t in enumerate(ladder)}
    rating_of = {t["teamId"]: t["rating"] for t in ladder}
    name_of = {t["teamId"]: t["teamName"] for t in ladder}
    us_rating = rating_of.get(team_id)

    try:
        submissions = (api_get("/api/submissions") or {}).get("submissions", []) or []
    except Exception:
        submissions = []
    sub_meta = {
        int(s["version"]): {
            "name": s.get("name") or None,
            "by": (s.get("uploadedBy") or {}).get("name")
            if isinstance(s.get("uploadedBy"), dict)
            else s.get("uploadedBy"),
            "uploaded": s.get("createdAt") or s.get("uploadedAt"),
            "active": bool(s.get("isActive") or s.get("active")),
        }
        for s in submissions
        if str(s.get("version", "")).isdigit()
    }

    # ---- what opponents are running right now -------------------------------------------------
    seen_versions: dict[str, Counter] = defaultdict(Counter)
    latest_version: dict[str, tuple[str, int]] = {}
    for m in recent_global:
        for side in ("A", "B"):
            tid = m[f"team{side}Id"]
            if tid == team_id:
                continue
            ver = m[f"team{side}Version"]
            seen_versions[tid][ver] += 1
            if tid not in latest_version or m["completedAt"] > latest_version[tid][0]:
                latest_version[tid] = (m["completedAt"], ver)

    opponents = []
    for tid, counts in seen_versions.items():
        opponents.append(
            {
                "team_id": tid,
                "team": name_of.get(tid, "unknown"),
                "rating": rating_of.get(tid),
                "rank": rank_of.get(tid),
                "current_version": latest_version[tid][1],
                "last_seen": latest_version[tid][0],
                "versions_last_hour": [
                    {"version": v, "matches": c} for v, c in sorted(counts.items(), reverse=True)
                ],
                "matches_last_hour": sum(counts.values()),
            }
        )
    opponents.sort(key=lambda o: (-(o["rating"] or 0)))

    # ---- our versions -------------------------------------------------------------------------
    by_version: dict[int, list[dict]] = defaultdict(list)
    for row in ours:
        by_version[row["ver"]].append(row)

    active_ratings = [o["rating"] for o in opponents if o["rating"] is not None]
    neighbourhood = _pairing_neighbourhood(us_rating, active_ratings) if us_rating else []

    versions = []
    for ver in sorted(by_version, reverse=True):
        rows = by_version[ver]
        wins = sum(1 for r in rows if r["win"])
        gf = sum(r["gf"] for r in rows)
        ga = sum(r["ga"] for r in rows)
        rated = [r for r in rows if r["kind"] == "ladder"]
        meta = sub_meta.get(ver, {})

        cells = defaultdict(lambda: [0, 0])
        for r in rows:
            cell = cells[round(r["opp_rating"], 3)]
            cell[0] += r["gf"]
            cell[1] += r["ga"]
        strength = _fit_strength([(r, w, loss) for r, (w, loss) in cells.items()])

        estimate = None
        if strength is not None and gf + ga >= MIN_GAMES_FOR_ESTIMATE:
            draws = _bootstrap_strength(rows, BOOTSTRAP_RESAMPLES, seed=1000 + ver)
            span = _interval(draws)
            vs_field = _field_score(strength, active_ratings)
            vs_near = _field_score(strength, neighbourhood) if neighbourhood else None
            estimate = {
                "elo": strength,
                "elo_lo": span[0] if span else None,
                "elo_hi": span[1] if span else None,
                "vs_active_field": vs_field,
                "vs_active_field_lo": _field_score(span[0], active_ratings) if span else None,
                "vs_active_field_hi": _field_score(span[1], active_ratings) if span else None,
                "vs_pairing_group": vs_near,
                "vs_pairing_group_lo": (
                    _field_score(span[0], neighbourhood) if span and neighbourhood else None
                ),
                "vs_pairing_group_hi": (
                    _field_score(span[1], neighbourhood) if span and neighbourhood else None
                ),
            }

        versions.append(
            {
                "version": ver,
                "name": meta.get("name"),
                "by": meta.get("by"),
                "uploaded": meta.get("uploaded"),
                "is_active": meta.get("active", False),
                "matches": len(rows),
                "wins": wins,
                "losses": len(rows) - wins,
                "games_for": gf,
                "games_against": ga,
                "rated": len(rated),
                "unrated": len(rows) - len(rated),
                "net_elo": sum(r["delta"] or 0.0 for r in rated),
                "avg_opp_rating": (
                    sum(r["opp_rating"] for r in rows) / len(rows) if rows else None
                ),
                "first_seen": min(r["t"] for r in rows),
                "last_seen": max(r["t"] for r in rows),
                "estimate": estimate,
                "estimate_blocked": (
                    None
                    if estimate
                    else ("swept" if strength is None else "insufficient-games")
                ),
            }
        )

    # ---- our versions against each opponent build ---------------------------------------------
    matchups: dict[tuple[int, str, int], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for row in ours:
        cell = matchups[(row["ver"], row["opp"], row["opp_ver"])]
        cell[0] += 1 if row["win"] else 0
        cell[1] += 0 if row["win"] else 1
        cell[2] += row["gf"]
        cell[3] += row["ga"]
    matchup_rows = [
        {
            "version": ver,
            "opponent": opp,
            "opponent_version": oppver,
            "wins": w,
            "losses": loss,
            "games_for": gf,
            "games_against": ga,
        }
        for (ver, opp, oppver), (w, loss, gf, ga) in sorted(matchups.items())
    ]

    current_builds = {(o["team"], o["current_version"]) for o in opponents}
    for row in matchup_rows:
        row["opponent_build_current"] = (row["opponent"], row["opponent_version"]) in current_builds

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "team": {
            "id": team_id,
            "name": team.get("name") or name_of.get(team_id),
            "rating": us_rating,
            "rank": rank_of.get(team_id),
            "ladder_size": len(ladder),
        },
        "model": {
            "k_factor": K_FACTOR,
            "series_games": SERIES_GAMES,
            "scheduler_period_minutes": SCHEDULER_PERIOD_MINUTES,
            "pairing_group_size": PAIRING_GROUP_SIZE,
            "active_window_minutes": ACTIVE_WINDOW_MINUTES,
            "min_games_for_estimate": MIN_GAMES_FOR_ESTIMATE,
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "matches_in_history": len(ours),
        },
        "versions": versions,
        "opponents": opponents,
        "matchups": matchup_rows,
        "recent": ours[:200],
    }


def write(feed: dict, site_repo: Path) -> Path:
    """Write the feed into `public/`, and mirror it into `dist/` when a build already exists.

    Astro copies `public/` verbatim, so the mirror is what lets a feed refresh reach production
    through `wrangler deploy` alone -- no `astro build`, which is far too slow to run on the feed's
    cadence.
    """
    target = site_repo / "public" / "botrankings" / "data" / "live.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(feed, separators=(",", ":"), default=str)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(payload)
    tmp.replace(target)

    mirror = site_repo / "dist" / "botrankings" / "data" / "live.json"
    if mirror.parent.parent.parent.exists():
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_text(payload)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site-repo", type=Path, default=DEFAULT_SITE)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--cold-pages", type=int, default=40)
    parser.add_argument("--deploy", action="store_true", help="publish to Cloudflare when changed")
    parser.add_argument("--print", dest="show", action="store_true", help="summarise to stdout")
    args = parser.parse_args(argv)

    started = time.monotonic()
    feed = build(args.site_repo, args.cache, args.cold_pages)
    target = write(feed, args.site_repo)
    elapsed = time.monotonic() - started
    print(
        f"live feed: {len(feed['versions'])} versions, {len(feed['opponents'])} active opponents, "
        f"{feed['model']['matches_in_history']} matches, {elapsed:.1f}s -> {target}"
    )

    if args.show:
        for v in feed["versions"]:
            est = v["estimate"]
            shown = (
                f"Elo {est['elo']:.0f} [{est['elo_lo']:.0f}, {est['elo_hi']:.0f}]"
                if est and est["elo_lo"] is not None
                else f"-- ({v['estimate_blocked']})"
            )
            print(
                f"  v{v['version']:<3} {v['games_for']:>4}-{v['games_against']:<4} games   {shown}"
            )

    if args.deploy:
        from tournament.automation import deploy_assets

        # No `astro build`: `write` already mirrored the feed into `dist/`, and rebuilding the
        # whole site every five minutes costs minutes we do not have.
        deploy_assets(args.site_repo, reason="live feed", build=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
