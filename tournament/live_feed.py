"""Build the live ladder feed consumed by lucasrgpedersen.com/botrankings/live.

This is a different animal from `site_data.py`. That module publishes the *offline* tournament --
our own bots played against each other on our own maps, scored with mElo and Nash. This one
publishes the *online* ladder: the real platform, real opponents, real Elo.

Three things make the online ladder worth its own feed:

- The platform pairs teams every ten minutes and nobody sees the schedule, or the rule behind it.
  Reconstructing what we played, and against which build of the opponent, needs the match log.
- Opponents ship new bots constantly -- Pivot used nine versions in twelve hours -- so a raw win
  rate silently compares our versions against different opposition. Everything here is broken out
  by the opponent's exact submission version.
- Our own versions get swapped in and out within minutes, so most of them have single-digit
  samples. Every estimate therefore carries an interval, and versions that cannot support an
  estimate say so rather than showing a number.

The rating model is not a guess. `tournament/README.md` records the derivation; briefly, the
platform runs plain Elo with K=32 over a five-game series scored as (games won / 5), and that
reproduces all 12255 observed rating deltas to the last decimal place.

Given that, a bot's equilibrium rating would be exactly its Elo-scale strength, whoever it played,
*if* a single number described it -- at R = strength every term of the drift vanishes regardless of
the opponent weights. It very nearly does, but not quite: per-opponent results are about 1.5x more
variable than binomial, so specific matchups matter a little beyond rating. Once that is true, who
you are drawn against decides where you settle, and a bot can sit below its apparent strength
purely because the ladder keeps handing it an opponent it cannot beat.

So the projection solves the fixed point rather than asserting it: per-opponent records, shrunk
toward the Elo prediction by as much as the measured overdispersion warrants, weighted by the
pairing kernel. With no overdispersion it collapses back to the one-parameter answer. In practice
it moves projections by -10 to +40 Elo, inside their intervals but not negligible.
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

from tournament import identity

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE = REPO_ROOT.parent / "portfolio"
DEFAULT_CACHE = REPO_ROOT / "tournament" / "live-cache.jsonl"

# The platform's rating rule, verified against every rated match since Aug 1 (zero residual).
K_FACTOR = 32
SERIES_GAMES = 5

SCHEDULER_PERIOD_MINUTES = 10

# How far apart, in ladder rank, the scheduler actually pairs teams. Measured over 12211 pairings
# across 649 ticks between 1 and 5 August; P(|rank offset| = d), symmetric in sign.
#
# This replaces a "blocks of eight" model that was wrong. Blocks predict that pairs never cross a
# block boundary, and 34% of real pairs do -- no block size gets that below 15%. The giveaway was
# there in the first measurement and I explained it away: blocks of eight cannot produce a rank
# distance above 7, and the data goes to 11. We were paired against a team eight places below us.
#
# So this makes no claim about the algorithm, which is not observable. It is just the distribution
# the ladder is seen to produce, and it is stable as the field grows: splitting the sample by tick
# size (under 30 teams, 30-45, 46+) moves no bin by more than about 2 points.
PAIRING_KERNEL: dict[int, float] = {
    1: 0.2420, 2: 0.2009, 3: 0.1829, 4: 0.1418, 5: 0.1091, 6: 0.0654,
    7: 0.0364, 8: 0.0138, 9: 0.0057, 10: 0.0020, 11: 0.0001,
}
PAIRING_KERNEL_PAIRS = 12211

# A bot needs enough games before a strength estimate means anything. Below this we publish the
# raw record and an explicit null rather than an interval nobody should read. The threshold bites
# much harder than it looks: only *rated* games against builds still in use count towards it,
# which for most bots is a small fraction of what they played.
MIN_GAMES_FOR_ESTIMATE = 25
BOOTSTRAP_RESAMPLES = 400

# "Currently in use" for an opponent build. One scheduler period is too tight -- a team that drew a
# different pairing simply would not appear -- and a whole day is long enough to include two bots
# ago. An hour is about six scheduler ticks.
ACTIVE_WINDOW_MINUTES = 60

# Results are not comparable across a balance patch, and the match API exposes no engine version,
# so the boundary has to be a timestamp. fcode 2.3.4 rewrote the Gunner (25 HP was 40, 20 Ti was
# 10, 7 damage was 10, 4 ammo per shot was 2) and the Sentinel (40 HP was 30, 2-round reload was
# 3); see the note at the top of tournament/README.md. Games either side of it describe different
# games, so everything here is restricted to the current era rather than pooled across it.
#
# Two caveats worth knowing. This instant is when *we* bumped the dependency, which is a proxy for
# when the platform switched, not a record of it -- matches within an hour or so of the boundary
# may be attributed to the wrong era. And it is deliberately not moved to the 2.3.6 bump (Aug 5
# 14:42Z): 2.3.4 is documented as a balance pass, 2.3.6 is not known to change mechanics, and
# moving it there would discard another two thirds of the evidence for no stated reason. If 2.3.6
# or a later release does change balance, add it here.
MECHANICS_EPOCH = "2026-08-04T15:06:00+00:00"
MECHANICS_EPOCH_LABEL = "fcode 2.3.4 turret patch"


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


def _pre_epoch_counts(rows: list[dict], epoch: str) -> dict[int, int]:
    """How many matches each submission played *before* the balance patch.

    Not used in any statistic -- it exists so a bot whose whole career predates the patch can say
    "24 matches, all pre-patch" instead of appearing to have never played at all.
    """
    counts: dict[int, int] = defaultdict(int)
    for row in rows:
        if row["t"] < epoch:
            counts[row["ver"]] += 1
    return dict(counts)


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


def _pairing_weights(rating: float, field: list[float]) -> list[tuple[float, float]]:
    """(opponent rating, probability) for the teams a team at `rating` is likely to be drawn against.

    Applies `PAIRING_KERNEL` to the ladder's rank ordering: each rank offset d carries its measured
    weight, split evenly between the team d places above and d places below.

    The split stops being even near the ends of the table, which matters here because we sit around
    fourth. A team at rank 2 has only one opponent at offset 3 above it and plenty below, so the
    missing side's weight goes to the side that exists rather than silently shrinking the total --
    otherwise the top of the ladder looks like it plays a weaker field than it does.
    """
    if not field:
        return []
    # Tag ourselves rather than locating our rating by value: a tie with a real team would
    # otherwise return that team's slot.
    pool = sorted([(r, False) for r in field] + [(rating, True)], key=lambda e: -e[0])
    index = next(i for i, (_, is_us) in enumerate(pool) if is_us)

    weights: list[tuple[float, float]] = []
    for offset, probability in PAIRING_KERNEL.items():
        above, below = index - offset, index + offset
        reachable = [i for i in (above, below) if 0 <= i < len(pool) and i != index]
        if not reachable:
            continue
        for i in reachable:
            weights.append((pool[i][0], probability / len(reachable)))
    return weights


def _overdispersion(cells: list[tuple[float, int, int]], strength: float) -> float:
    """Ratio of observed to binomial variance in per-opponent results. 1.0 means pure Elo.

    Above 1 means specific opponents matter beyond their rating -- a counter we keep losing to, a
    style we happen to beat. Measured at 1.48 pooled across our bots, so the effect is real but
    modest; it is what sets how far per-opponent records are trusted over the Elo prediction.
    """
    usable = [(r, w, loss) for r, w, loss in cells if w + loss >= 5]
    if len(usable) < 4:
        return 1.0
    chi = 0.0
    for rating, wins, losses in usable:
        n = wins + losses
        p = _expected(strength, rating)
        if 0.0 < p < 1.0:
            chi += (wins - n * p) ** 2 / (n * p * (1.0 - p))
    return chi / max(1, len(usable) - 1)


def _equilibrium(
    current: list[tuple[float, int, int]], strength: float, field: list[float]
) -> float:
    """The rating at which this bot stops drifting, given who it will actually be drawn against.

    The one-parameter answer -- equilibrium equals Elo-scale strength, whoever you play -- is only
    true if a single number really does describe the bot. It does not, quite: per-opponent results
    are about 1.5x more variable than binomial, so specific matchups matter beyond rating. Once
    that is admitted, *who you are paired against decides where you settle*, and the pairing kernel
    stops being decoration for the headline number.

    So solve the fixed point instead of asserting it. Expected score against each likely opponent
    comes from our record against that opponent, shrunk toward the Elo prediction by an amount the
    measured overdispersion implies -- no overdispersion shrinks all the way back to the
    one-parameter answer, which is the right degenerate case. Opponents we have never played
    contribute the Elo prediction, since we know nothing else about them.

    Published as a sensitivity, not as the headline. Validated against the rating each bot actually
    held during its unbroken ladder stints, this is out by 28 Elo on average where the plain
    one-parameter fit is out by 6 -- at ~13 games per opponent the overdispersion driving it is
    mostly sampling noise. Right idea, not enough data to estimate it.
    """
    dispersion = _overdispersion(current, strength)
    # Pseudo-games of pull toward the Elo prediction. Excess variance of zero means infinite pull
    # (trust rating only); heavy excess means trust the head-to-head record.
    excess = max(dispersion - 1.0, 0.0)
    pull = 6.0 / excess if excess > 1e-6 else float("inf")

    observed: dict[float, float] = {}
    if pull != float("inf"):
        for opponent, wins, losses in current:
            played = wins + losses
            if played:
                prior = _expected(strength, opponent)
                observed[opponent] = (wins + pull * prior) / (played + pull)

    def drift(candidate: float) -> float:
        weights = _pairing_weights(candidate, field)
        total = sum(w for _, w in weights)
        if not total:
            return 0.0
        return sum(
            w * (observed.get(r, _expected(strength, r)) - _expected(candidate, r))
            for r, w in weights
        ) / total

    if not field:
        return strength
    low, high = 600.0, 3200.0
    for _ in range(80):
        mid = (low + high) / 2.0
        if drift(mid) > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _pairing_score(strength: float, rating: float, field: list[float]) -> float | None:
    """Expected share of games won against the opponents the scheduler is likely to draw."""
    weights = _pairing_weights(rating, field)
    total = sum(w for _, w in weights)
    if not total:
        return None
    return sum(w * _expected(strength, r) for r, w in weights) / total


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

    every = [_orient(m, team_id) for m in allrows if m.get("status") == "complete"]
    every.sort(key=lambda r: r["t"], reverse=True)
    # Everything downstream sees only the current balance era. Keeping the pre-patch rows around
    # to "add context" is how they end up averaged into something, which is the whole problem.
    ours = [r for r in every if r["t"] >= MECHANICS_EPOCH]
    pre_epoch = _pre_epoch_counts(every, MECHANICS_EPOCH)

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

    # Load-bearing, not decorative: a submission that has not played yet exists only here, and
    # there is a five-minute gap between uploading and the first series completing during which
    # this is the sole evidence the bot is on the ladder at all.
    submissions = api_get("/api/submissions") or {}
    if isinstance(submissions, dict):
        submissions = submissions.get("submissions", []) or []
    sub_meta = {
        int(s["version"]): {
            "name": s.get("name") or None,
            "by": s.get("submittedByName"),
            "uploaded": s.get("uploadedAt"),
            "active": bool(s.get("isActive")),
            "status": s.get("status"),
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

    # ---- which bot each submission version actually is -----------------------------------------
    try:
        identities = identity.resolve(api_get, submissions)
    except Exception as error:  # never let identity resolution take the live feed down
        print(f"identity: resolution unavailable ({error})")
        identities = {}

    def bot_key(version: int) -> str:
        """Group submissions by what they *are*. Unresolved ones stay separate, not merged."""
        found = identities.get(version)
        return found["code_hash"] if found else f"v{version}"

    active_ratings = [o["rating"] for o in opponents if o["rating"] is not None]
    # The pairing group is evaluated at *our team's* current rating, because that is the slot a
    # newly activated bot inherits -- it does not start at its own strength.
    current_builds = {(o["team"], o["current_version"]) for o in opponents}
    current_rating = {
        (o["team"], o["current_version"]): o["rating"] for o in opponents if o["rating"] is not None
    }

    # ---- pool by code, not by upload slot ------------------------------------------------------
    # A submission version is a slot; the same bot can occupy several. v26 and v27 are byte
    # identical, as are v9 and v16, and splitting their records would halve the evidence for no
    # reason. Anything that never matched a git tree keeps its own row rather than being pooled
    # with other unknowns, since "we could not identify it" is not a claim that two are the same.
    by_bot: dict[str, list[dict]] = defaultdict(list)
    for row in ours:
        by_bot[bot_key(row["ver"])].append(row)
    versions_of: dict[str, set[int]] = defaultdict(set)
    for ver in sub_meta:
        versions_of[bot_key(ver)].add(ver)
    for row in ours:
        versions_of[bot_key(row["ver"])].add(row["ver"])

    bots = []
    for key in versions_of:
        rows = by_bot.get(key, [])
        vers = sorted(versions_of[key])
        metas = [sub_meta[v] for v in vers if v in sub_meta]
        found = next((identities[v] for v in vers if v in identities), None)

        wins = sum(1 for r in rows if r["win"])
        gf = sum(r["gf"] for r in rows)
        ga = sum(r["ga"] for r in rows)
        rated = [r for r in rows if r["kind"] == "ladder"]

        # The projection sees only rated games against builds still on the ladder.
        #
        # Two filters, two reasons. Retired builds are excluded because an opponent who has shipped
        # twice since is a different bot. Unrated games are excluded because *we* choose those
        # opponents, and we choose weak ones -- they average 88 Elo below us, against 4 on the
        # ladder -- which would be harmless if Elo's curve were calibrated, and it is not. Across
        # every match on the platform, a 100-point favourite scores 66.6% where the logistic
        # predicts 62.2%, and a 200-point favourite 78.9% against 74.6%. The real curve is steeper
        # than the 400-point scale, so games against weak opponents overperform the model and the
        # fit reads that as enormous strength.
        #
        # That is not a small effect. It put steward_hardened_reinforced@f61245f at 1917 when its
        # rated-only fit is 1878 and the rating it actually held all night averaged 1873, peaking
        # at 1897 -- an "expected" rating it never once reached, which is what gave the bias away.
        live_rows = [
            r
            for r in rows
            if r["kind"] == "ladder" and (r["opp"], r["opp_ver"]) in current_builds
        ]
        cells = defaultdict(lambda: [0, 0])
        for r in live_rows:
            cell = cells[round(r["opp_rating"], 3)]
            cell[0] += r["gf"]
            cell[1] += r["ga"]
        live_games = sum(r["gf"] + r["ga"] for r in live_rows)
        cell_rows = [(r, w, loss) for r, (w, loss) in cells.items()]
        strength = _fit_strength(cell_rows)
        # Fitting theta uses each opponent's rating *at the time we played them*, which is right.
        # Projecting forward needs the same records against their rating *now*, because that is
        # what the pairing kernel returns -- keying the projection on historical ratings meant the
        # lookup never matched and the matchup term silently did nothing.
        current_cells_map: dict[float, list[int]] = defaultdict(lambda: [0, 0])
        for r in live_rows:
            rating_now = current_rating.get((r["opp"], r["opp_ver"]))
            if rating_now is None:
                continue
            slot = current_cells_map[rating_now]
            slot[0] += r["gf"]
            slot[1] += r["ga"]
        current_cells = [(r, w, loss) for r, (w, loss) in current_cells_map.items()]

        estimate = None
        if strength is not None and live_games >= MIN_GAMES_FOR_ESTIMATE:
            draws = _bootstrap_strength(
                live_rows, BOOTSTRAP_RESAMPLES, seed=abs(hash(key)) % 100000
            )
            span = _interval(draws)
            # The headline is the single-parameter fit, not the matchup-aware fixed point.
            #
            # The fixed point is better theory -- a bot really can be held below its strength by an
            # opponent it cannot beat and keeps drawing -- but it is worse practice here, and the
            # only ground truth available says so. Checked against the rating each bot actually
            # held during its unbroken stints, single theta is out by 6 Elo on average and the
            # fixed point by 28, because it missed f61245f by 42. At ~13 games per opponent the
            # overdispersion driving it is mostly sampling noise, and trusting it hands the
            # projection to whichever opponent we happened to run hot against.
            #
            # Published as a sensitivity instead, with dispersion as a warning that a bot's results
            # are lumpy. Revisit if cells ever get big enough to estimate a real variance component.
            estimate = {
                "elo": strength,
                "elo_if_matchups_persist": _equilibrium(current_cells, strength, active_ratings),
                "matchup_dispersion": _overdispersion(current_cells, strength),
                "elo_lo": span[0] if span else None,
                "elo_hi": span[1] if span else None,
                "vs_active_field": _field_score(strength, active_ratings),
                "vs_active_field_lo": _field_score(span[0], active_ratings) if span else None,
                "vs_active_field_hi": _field_score(span[1], active_ratings) if span else None,
                "vs_pairing_group": _pairing_score(strength, us_rating, active_ratings),
                "vs_pairing_group_lo": (
                    _pairing_score(span[0], us_rating, active_ratings) if span else None
                ),
                "vs_pairing_group_hi": (
                    _pairing_score(span[1], us_rating, active_ratings) if span else None
                ),
            }

        uploads = [m["uploaded"] for m in metas if m.get("uploaded")]
        names = [m["name"] for m in metas if m.get("name")]
        bots.append(
            {
                "key": key,
                "versions": vers,
                "canonical": (found or {}).get("canonical"),
                "code_hash": (found or {}).get("code_hash"),
                "path": (found or {}).get("path"),
                "commit": (found or {}).get("commit"),
                "in_git": bool((found or {}).get("in_git")),
                "claimed": (found or {}).get("claimed"),
                "aliases": (found or {}).get("aliases") or [],
                "variant": (found or {}).get("variant"),
                "labels": names,
                "by": next((m["by"] for m in metas if m.get("by")), None),
                "uploaded": min(uploads) if uploads else None,
                "last_uploaded": max(uploads) if uploads else None,
                "is_active": any(m.get("active") for m in metas),
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
                "first_seen": min((r["t"] for r in rows), default=None),
                "last_seen": max((r["t"] for r in rows), default=None),
                "pre_epoch_matches": sum(pre_epoch.get(v, 0) for v in vers),
                "live_games": live_games,
                "live_builds": len({(r["opp"], r["opp_ver"]) for r in live_rows}),
                "estimate": estimate,
                # Distinguishing these matters: "never played" and "played, but only against bots
                # nobody runs any more" and "played current bots and won or lost every single
                # game" are three different reasons for a blank, and only the last is about the
                # bot being unmeasurably good or bad.
                "estimate_blocked": (
                    None
                    if estimate
                    else "pre-patch-only"
                    if not rows and any(pre_epoch.get(v) for v in vers)
                    else "no-matches"
                    if not rows
                    else "no-current-games"
                    if live_games == 0
                    else "swept"
                    if strength is None
                    else "few-current-games"
                ),
            }
        )
    # Chronological: by first upload, falling back to first match for anything the submissions
    # endpoint no longer lists.
    bots.sort(key=lambda b: (b["uploaded"] or b["first_seen"] or "", min(b["versions"])))

    # ---- each bot against each opponent build --------------------------------------------------
    matchups: dict[tuple[str, str, int], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for row in ours:
        cell = matchups[(bot_key(row["ver"]), row["opp"], row["opp_ver"])]
        cell[0] += 1 if row["win"] else 0
        cell[1] += 0 if row["win"] else 1
        cell[2] += row["gf"]
        cell[3] += row["ga"]
    matchup_rows = [
        {
            "key": key,
            "opponent": opp,
            "opponent_version": oppver,
            "wins": w,
            "losses": loss,
            "games_for": gf,
            "games_against": ga,
            "opponent_build_current": (opp, oppver) in current_builds,
        }
        for (key, opp, oppver), (w, loss, gf, ga) in sorted(matchups.items())
    ]

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
            "pairing_kernel": PAIRING_KERNEL,
            "pairing_kernel_pairs": PAIRING_KERNEL_PAIRS,
            "pairing_reach": max(PAIRING_KERNEL),
            "active_window_minutes": ACTIVE_WINDOW_MINUTES,
            "mechanics_epoch": MECHANICS_EPOCH,
            "mechanics_epoch_label": MECHANICS_EPOCH_LABEL,
            "matches_before_epoch": sum(pre_epoch.values()),
            "min_games_for_estimate": MIN_GAMES_FOR_ESTIMATE,
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "matches_in_history": len(ours),
            "matches_all_time": len(every),
        },
        "bots": bots,
        "opponents": opponents,
        "matchups": matchup_rows,
        "recent": [dict(r, key=bot_key(r["ver"])) for r in ours[:200]],
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
        f"live feed: {len(feed['bots'])} bots, {len(feed['opponents'])} active opponents, "
        f"{feed['model']['matches_in_history']} matches, {elapsed:.1f}s -> {target}"
    )

    if args.show:
        for v in feed["bots"]:
            est = v["estimate"]
            shown = (
                f"Elo {est['elo']:.0f} [{est['elo_lo']:.0f}, {est['elo_hi']:.0f}]"
                if est and est["elo_lo"] is not None
                else f"-- ({v['estimate_blocked']})"
            )
            vers = ",".join(f"v{n}" for n in v["versions"])
            print(
                f"  {vers:<10} {v['canonical'] or '(not in git)':<28} "
                f"{v['games_for']:>4}-{v['games_against']:<4} all, {v['live_games']:>4} current   {shown}"
            )

    if args.deploy:
        from tournament.automation import deploy_assets

        # No `astro build`: `write` already mirrored the feed into `dist/`, and rebuilding the
        # whole site every five minutes costs minutes we do not have.
        deploy_assets(args.site_repo, reason="live feed", build=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
