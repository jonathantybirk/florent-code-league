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
import importlib.util
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

# Delta elo is NOT reimplemented here. The ladderfarm's `arms.simulated_rating` is the single
# definition, and the farm promotes on exactly the number this page shows -- two implementations
# drifted apart once already (different pairing distributions, and a prior that shrank every
# delta toward zero), which made the column actively misleading about what would be promoted.
LADDERFARM = Path(os.environ.get("LADDERFARM_REPO") or "")
LADDERFARM_CANDIDATES = [
    LADDERFARM,
    REPO_ROOT.parent / "ladderfarm",
    REPO_ROOT.parent / "florent-code-league",
]

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

# The farm chooses its own opponents; the ladder scheduler does not. Fitting both kinds of game as
# one sample credits us with the choosing. `_fit_selection_bonus` measures what that choice is
# worth. The threshold is per build and per context, because the offset is identified from
# within-build contrast: a build needs enough of *both* kinds to say anything, and a build with
# only farm games contributes a strength and no information about the offset.
MIN_GAMES_PER_CONTEXT = 30
MAX_SELECTION_BONUS = 400.0

# Shrinkage needs a field to shrink towards, and the spread between builds has to be separable
# from the noise within them. Below a handful of estimates that decomposition is meaningless, so
# the published numbers are left as fitted.
MIN_BUILDS_TO_SHRINK = 4

# Two things were wrong with turning a record into a single Elo-scale strength.
#
# The first is that a win rate is durable while a rating is not. Our record against an
# opponent build stays meaningful for as long as neither bot changes, but the rating that
# record was scored against drifts underneath it -- and the current-builds filter controls
# for their *code*, not their *rating*. Fitting theta against the rating they held that day
# and publishing it as where we would settle today assumes we still gain what that gap once
# implied. Our own rating moved 340 Elo across the current cache, so that assumption is
# simply false. `_simulate_settled_rating` keeps the per-opponent record and re-anchors the
# arithmetic on their rating now.
#
# The second is that evidence goes stale even at a fixed version, because the field around
# it moves. That is what the half-life is for.
#
# Backtested against the rating each build actually held in the minutes before we swapped
# away from it, reconstructing the current-builds filter at each point in time, 16 stints:
#
#     one strength, ratings as played   bias +58.5  mean|err| 62.3  high in 15/16
#     simulation, no ageing             bias +38.1  mean|err| 43.5         13/16
#     one strength + 8h ageing          bias +21.7  mean|err| 35.7         12/16
#     simulation + 6h ageing            bias +19.7  mean|err| 32.3         11/16   <- chosen
#
# Still a partial fix, and worth saying plainly: bias +58 -> +20, not to zero. A third of
# the overestimate remains unexplained, and these are all builds that were promoted, so the
# winner's curse in `_shrink_towards_the_field` is a live candidate for the remainder.
EVIDENCE_HALF_LIFE_HOURS = 6.0

# Simulation budget. The feed rebuilds every two minutes, so this is bounded deliberately:
# 24 runs of 300 ticks converged to within a couple of Elo of 60x400 on the backtest, and
# costs a fraction of the time.
SIM_RUNS = 24
SIM_TICKS = 300
SIM_BURN_IN = 100
# Pseudo-games pulling a thin per-opponent record toward what the fitted strength predicts.
# Without it a 0-5 against one opponent claims we never beat them.
MATCHUP_PRIOR_GAMES = 4.0

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


def _recency_weight(played_at: str, now: float) -> float:
    """How much a game still counts, by age. See EVIDENCE_HALF_LIFE_HOURS."""
    try:
        moment = datetime.fromisoformat(played_at.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return 1.0
    hours = max(0.0, (now - moment) / 3600.0)
    return 0.5 ** (hours / EVIDENCE_HALF_LIFE_HOURS)


def _fit_strength(games: list[tuple[float, int, int]]) -> float | None:
    """Maximum-likelihood Elo-scale strength from (opponent_rating, wins, losses) rows.

    A row may carry a fourth field: an Elo bonus added to our strength for that row alone. It lets
    games we chose to play be fitted alongside games the scheduler chose for us without pretending
    the two are the same evidence -- see `_fit_selection_bonus`. Omitted, it is zero, and this is
    the plain one-parameter fit it has always been.

    One parameter, log-likelihood strictly concave in it, so bisection on the score function is
    both sufficient and immune to the step-size problems Newton has when a version has swept or
    been swept. Returns None when the record is all wins or all losses, where the MLE runs off to
    infinity and any finite number we printed would be an artefact of where we truncated.
    """
    rows = [(g[0], g[1], g[2], g[3] if len(g) > 3 else 0.0) for g in games]
    total_wins = sum(w for _, w, _, _ in rows)
    total_losses = sum(loss for _, _, loss, _ in rows)
    # A tolerance rather than == 0: recency weights make these floats, and a record whose
    # only wins are a thousandth of a game old is degenerate in every way that matters.
    if total_wins < 1e-6 or total_losses < 1e-6:
        return None

    def score(strength: float) -> float:
        # d/dS of the log-likelihood, up to the positive constant ln(10)/400.
        return sum(w - (w + loss) * _expected(strength + bonus, r) for r, w, loss, bonus in rows)

    low, high = 0.0, 4000.0
    for _ in range(60):
        mid = (low + high) / 2.0
        if score(mid) > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _fit_selection_bonus(rows: list[dict]) -> float:
    """What the farm's *choice* of opponent is worth, in Elo, across the team's whole history.

    The farm picks who to challenge -- two from the top five, two near our own rank, one from the
    wider pool, preferring whoever it has played least. Until now those games were fitted as
    interchangeable with the ones the scheduler drew for us, on the argument that selecting who we
    play cannot bias a fit that already conditions on who we played.

    That argument needs a team's rating to be a sufficient statistic for playing that team. In a
    non-transitive game it is not: an opponent we counter and an opponent who counters us can hold
    the same rating and hand us very different scores. So *which* opponents the farm serves up
    moves the fitted strength even though every row is conditioned on its own opponent, and the
    bonus below is the size of that move.

    Fitted as fixed effects: one free strength per build, one offset shared across all of them.
    That matters more than it sounds. A single pooled strength lets the offset absorb anything that
    correlates with the chosen/drawn mix, and two things do. The mechanics epoch is one -- the mix
    is 1976:2225 before the 2.3.4 rebalance and 4580:1785 after, so pooling the eras hands the
    balance patch to this parameter and reports +46 Elo. The build is the other, for the same
    reason. With a strength per build the offset can only be identified from within-build contrast:
    the same bot scoring better in fixtures it chose than in fixtures it was given, which is the
    only thing ever being claimed.

    So measured: +20.5 Elo post-epoch across the 7 builds carrying the contrast, 90% bootstrap
    interval +0 to +46, likelihood-ratio chi2(1) = 3.1. Real, worth removing, and nowhere near as
    large as the pooled fit claimed. The larger error in the published numbers is not this at all
    -- see `_shrink_towards_the_field`.

    Returns 0.0, and so the old behaviour, whenever the offset cannot be identified: no build with
    enough of both kinds, a degenerate record, or a fit that ran into the boundary.
    """
    # A row whose opponent had no rating yet informs nothing in a fit that conditions on
    # opponent rating, and would take the arithmetic out at the knees. Twelve such rows
    # already exist post-epoch; they have stayed harmless only because they belong to
    # builds under the threshold below, which is luck rather than design.
    by_build: dict[object, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("opp_rating") is None:
            continue
        by_build[row["ver"]].append(row)

    usable = {}
    for build, group in by_build.items():
        chosen = sum(r["gf"] + r["ga"] for r in group if r["kind"] == "unrated")
        drawn = sum(r["gf"] + r["ga"] for r in group) - chosen
        wins = sum(r["gf"] for r in group)
        losses = sum(r["ga"] for r in group)
        if chosen >= MIN_GAMES_PER_CONTEXT and drawn >= MIN_GAMES_PER_CONTEXT and wins and losses:
            usable[build] = group
    if not usable:
        return 0.0

    strengths = {build: 1800.0 for build in usable}
    bonus = 0.0
    for _ in range(40):
        for build, group in usable.items():
            fitted = _fit_strength(
                [(r["opp_rating"], r["gf"], r["ga"], bonus if r["kind"] == "unrated" else 0.0)
                 for r in group]
            )
            if fitted is not None:
                strengths[build] = fitted
        low, high = -MAX_SELECTION_BONUS, MAX_SELECTION_BONUS
        for _ in range(50):
            mid = (low + high) / 2.0
            gradient = sum(
                r["gf"] - (r["gf"] + r["ga"]) * _expected(strengths[build] + mid, r["opp_rating"])
                for build, group in usable.items()
                for r in group
                if r["kind"] == "unrated"
            )
            low, high = (mid, high) if gradient > 0 else (low, mid)
        moved = (low + high) / 2.0
        settled = abs(moved - bonus) < 1e-3
        bonus = moved
        if settled:
            break
    # A bonus pinned to the search boundary is not an estimate, it is a failure to converge.
    if abs(bonus) >= MAX_SELECTION_BONUS - 1.0:
        return 0.0
    return bonus


def _simulate_settled_rating(
    matchups: dict[object, tuple[float, float]], start: float, seed: int
) -> float | None:
    """Play the ladder forward against the field as it stands, and report where we settle.

    `matchups` maps an opponent build to (their rating now, our per-game win probability
    against them). Both halves matter and neither survives being collapsed into one number:
    the probability is what our record actually measured, and the rating is what the Elo
    arithmetic will pay out against *today*, not on the day we played them.

    Each tick draws an opponent through the measured pairing kernel applied at our current
    simulated rating, plays a five-game series, and applies the platform's own update --
    K=32 on (games won / 5), which reproduces every observed delta exactly. Rank position is
    recomputed each tick, so climbing into a harder neighbourhood costs what it really costs.

    This is the piece a single strength cannot do. A strength assumes rating is a sufficient
    statistic for an opponent; here an opponent we happen to counter and one who counters us
    stay distinct all the way through, which is what a non-transitive game requires.

    The median across runs is returned rather than the mean: the stationary distribution has
    a tail on the side of whichever opponent we most recently ran hot against.
    """
    pool = [(rating, p) for rating, p in matchups.values()]
    if len(pool) < 3:
        return None
    rng = random.Random(seed)
    settled: list[float] = []
    for _ in range(SIM_RUNS):
        rating = start
        seen: list[float] = []
        for tick in range(SIM_TICKS):
            order = sorted(pool + [(rating, None)], key=lambda e: -e[0])
            us = next(i for i, e in enumerate(order) if e[1] is None)
            draw: list[tuple[tuple[float, float | None], float]] = []
            for offset, probability in PAIRING_KERNEL.items():
                reachable = [i for i in (us - offset, us + offset)
                             if 0 <= i < len(order) and i != us]
                for i in reachable:
                    draw.append((order[i], probability / len(reachable)))
            if not draw:
                break
            total = sum(w for _, w in draw)
            pick = rng.random() * total
            chosen = draw[-1][0]
            for entry, weight in draw:
                pick -= weight
                if pick <= 0:
                    chosen = entry
                    break
            opponent_rating, probability = chosen
            won = sum(1 for _ in range(SERIES_GAMES) if rng.random() < probability)
            rating += K_FACTOR * (won / SERIES_GAMES - _expected(rating, opponent_rating))
            if tick >= SIM_BURN_IN:
                seen.append(rating)
        if seen:
            settled.append(sum(seen) / len(seen))
    if not settled:
        return None
    settled.sort()
    return settled[len(settled) // 2]


def _shrink_towards_the_field(bots: list[dict]) -> None:
    """Correct the published Elo for the winner's curse, in place.

    The farm activates whichever candidate estimates highest. At the promotion threshold an
    estimate carries tens of Elo of sampling noise, so the winner is partly whoever ran hot, and
    the number is read at exactly the moment it is most inflated. Measured on the three builds that
    have both a pre-promotion and a post-promotion record: fitted on what the farm knew when it
    promoted them, v30 read 1914, v33 1930, v34 1861; fitted on everything they went on to play,
    1842, 1850 and 1834. Three of three shrank, by 73, 80 and 27 Elo, and the size of the shrink
    tracks how little evidence there was -- 31, 10 and 76 games respectively. That is the winner's
    curse, not bad luck.

    The standard correction is to stop reading each estimate on its own. Our builds are draws from
    one population -- the same team's bots, weeks apart -- so an estimate far above the rest is
    more likely to be noise than genius, and how much more depends on its own precision. Each is
    moved toward the field mean by tau^2 / (tau^2 + se^2): a build with a tight interval barely
    moves, one promoted on ten games moves a long way.

    tau^2, the real spread between builds, is what is left of the observed spread after the
    sampling noise in the estimates is subtracted. When that leaves nothing -- the builds differ by
    no more than their error bars -- every estimate collapses to the mean, which is the correct
    answer to "these all look the same".

    Published as `elo_settled` beside `elo`, deliberately not in place of it. `elo` is what the
    farm ranks candidates by (`live.elo_estimate` -> `farm.decide`, which promotes only on a strict
    improvement over the incumbent), and on the current data every build shrinks all the way to the
    field mean -- our seven builds differ by less than their own error bars. Overwriting `elo` would
    therefore tie every candidate with the incumbent and silently freeze promotion for good. Which
    number the farm *should* rank on is a real question, and promoting on unshrunk estimates is
    precisely the mechanism described above; but that is a change to how the ladder behaves, not to
    how it is reported, and it needs to be made deliberately rather than as a side effect.

    The interval travels with the point estimate rather than being recomputed, so it still spans
    the same width of evidence.
    """
    have = [
        b for b in bots
        if b.get("estimate")
        and b["estimate"].get("elo") is not None
        and b["estimate"].get("elo_lo") is not None
        and b["estimate"].get("elo_hi") is not None
    ]
    if len(have) < MIN_BUILDS_TO_SHRINK:
        return

    values = [b["estimate"]["elo"] for b in have]
    # 90% interval, so half-width is 1.645 standard errors.
    errors = [(b["estimate"]["elo_hi"] - b["estimate"]["elo_lo"]) / (2 * 1.6449) for b in have]
    mean = sum(values) / len(values)
    observed_spread = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    sampling_noise = sum(e * e for e in errors) / len(errors)
    between = max(0.0, observed_spread - sampling_noise)

    for bot, value, error in zip(have, values, errors):
        denominator = between + error * error
        weight = between / denominator if denominator > 0 else 0.0
        estimate = bot["estimate"]
        settled = mean + weight * (value - mean)
        shift = settled - value
        estimate["elo_settled"] = settled
        estimate["elo_settled_lo"] = estimate["elo_lo"] + shift
        estimate["elo_settled_hi"] = estimate["elo_hi"] + shift
        estimate["shrinkage"] = 1.0 - weight


def _bootstrap_strength(
    matches: list[dict], resamples: int, seed: int, selection_bonus: float = 0.0,
    now: float | None = None,
) -> list[float]:
    """Cluster bootstrap over matches, not games.

    Games inside one series share a map and an opponent build, so they are nowhere near
    independent. Resampling whole series keeps that correlation intact; resampling games would
    shrink the interval by roughly the square root of the series length and lie about it.

    `selection_bonus` is held fixed rather than refitted inside each resample. It is a property of
    how the farm picks opponents, estimated across the whole team's history, so a build's interval
    should reflect the uncertainty in *its own* record -- not re-litigate a team-level parameter
    from a few dozen matches, which would widen every interval with noise that is not there.
    """
    rng = random.Random(seed)
    n = len(matches)
    draws: list[float] = []
    for _ in range(resamples):
        picked = [matches[rng.randrange(n)] for _ in range(n)]
        rows: dict[tuple[float, bool], list[float]] = defaultdict(lambda: [0.0, 0.0])
        for match in picked:
            weight = _recency_weight(match["t"], now) if now else 1.0
            cell = rows[(round(match["opp_rating"], 3), match["kind"] == "unrated")]
            cell[0] += match["gf"] * weight
            cell[1] += match["ga"] * weight
        fit = _fit_strength(
            [(r, w, loss, selection_bonus if chosen else 0.0)
             for (r, chosen), (w, loss) in rows.items()]
        )
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


def _load_arms():
    """The ladderfarm's `arms` module, or None when no usable checkout sits beside this one.

    Imported rather than vendored so there is one definition of delta elo. Loaded by file
    path and checked for the symbols actually used, because more than one ladderfarm
    checkout can exist on a machine (a working copy and the deploy target sync.sh writes)
    and the older one silently lacks them. Returns None instead of raising: a missing
    sibling should cost the column, not the whole feed.
    """
    required = ("simulated_rating", "matchup_rates", "DELTA_SIMS")
    for candidate in LADDERFARM_CANDIDATES:
        if not candidate or not (candidate / "arms.py").exists():
            continue
        if not (candidate / "pairing_slots.json").exists():
            continue
        spec = importlib.util.spec_from_file_location(
            "ladderfarm_arms", candidate / "arms.py")
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        # Registered before execution: `arms` defines dataclasses, and dataclasses resolve
        # their annotations through sys.modules[cls.__module__], which is None otherwise.
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as error:  # a broken sibling must not take the feed down
            sys.modules.pop(spec.name, None)
            print(f"delta elo: cannot load {candidate}/arms.py ({error})")
            continue
        if all(hasattr(module, name) for name in required):
            return module
        print(f"delta elo: {candidate}/arms.py is too old, trying the next checkout")
    return None


def _attach_delta_elo(feed: dict) -> None:
    """Fill `delta_elo` and the coverage verdict on every build, using the farm's own code.

    Runs after the feed is assembled because the simulation reads `matchups` and
    `opponents` off the finished payload, exactly as the farm does. Bots with no
    current-build record simply keep a null, the same ones the farm refuses to score.
    """
    arms = _load_arms()
    if arms is None:
        print("delta elo: ladderfarm checkout not found, publishing without it")
        return
    rows = [
        {"teamId": o["team_id"], "teamName": o["team"], "rating": o["rating"],
         "matchesPlayed": 1, "ladderBanned": False}
        for o in feed["opponents"]
    ]
    field = arms.active_field(rows, feed["team"]["id"])
    rating = feed["team"]["rating"]
    for bot in feed["bots"]:
        # Published for every bot, estimate or not: coverage is why a build is ineligible,
        # and that has to be visible or the farm looks like it ignored its own metric.
        seen, needed, ok = arms.qualification(feed, bot["key"], field, rating)
        bot["qualified"] = ok
        bot["faced_closest"] = seen
        bot["closest_k"] = arms.CLOSEST_K
        bot["qualify_min"] = needed
        estimate = bot.get("estimate")
        if not estimate:
            continue
        estimate["delta_elo"] = None
        estimate["delta_elo_se"] = None
        if not arms.matchup_rates(feed, bot["key"]):
            continue
        mean, _sd, se = arms.simulated_rating(
            feed, bot["key"], rows, sim_length=1, sim_count=arms.DELTA_SIMS,
        )
        estimate["delta_elo"] = mean - feed["team"]["rating"]
        estimate["delta_elo_se"] = se


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

    # Priced once over the team's whole post-epoch history, then held fixed for every bot. It
    # describes the farm's opponent-picking policy, not any one bot, and no single bot has the
    # hundreds of games of each kind needed to identify it.
    #
    # Deliberately *not* restricted to builds still on the ladder, the way the per-bot fits are.
    # How the farm chooses fixtures does not expire when an opponent ships a new version, and that
    # filter cuts the sample from 2,098 matches to 469 -- enough to swing the estimate from +48 to
    # +4 depending on which opponents happen to be current at the minute the feed runs. A team-
    # level constant that moves 44 Elo between two runs an hour apart is not a constant.
    selection_bonus = _fit_selection_bonus(ours)

    # One instant for every recency weight in this build, so two bots fitted in the same
    # tick age their evidence against the same clock.
    now_epoch = datetime.now(UTC).timestamp()

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
        # One filter now, not two. Retired builds are still excluded -- an opponent who has
        # shipped twice since is a different bot -- but unrated games count, priced rather than
        # dropped: each carries `selection_bonus`, so the farm's choice of opponent is credited to
        # the farm instead of to the bot.
        #
        # The comment that stood here argued no pricing was needed, because selecting who we play
        # cannot bias a fit that conditions on who we played. That is true only where a team's
        # rating is a sufficient statistic for playing that team, and 10,461 games say it is not:
        # the free-choice games are worth +46 Elo, chi2(1) = 37.8. See `_fit_selection_bonus`.
        #
        # The earlier rated-only rule was measured against the rating each build actually held
        # while live, on the 7 builds with >=25 rated games post-epoch: rated-only is out by a mean
        # 17 Elo, all-games by 26. So the exclusion did buy accuracy, but modestly and
        # inconsistently -- v28 was *better* with unrated included -- and it cost nearly everything
        # else. Under it only 4 of 19 builds with matches had an estimate at all, every one of them
        # a current or former flagship, because rated games are the one thing a bot cannot get
        # until it is already live. The farm could gather data forever and never promote anything.
        # Pricing keeps every one of those games and still lands at 14.8 Elo of mean error.
        #
        # The related claim in the previous comment, that the platform's curve is much steeper than
        # the 400 scale, did not reproduce on the cached matches: the MLE scale is 425 (log-lik
        # -5796.6 against -5797.8 at 400, i.e. nothing over 9006 games), and moderate favourites
        # *under*-perform the model rather than over-perform it. The residuals are not monotone in
        # the gap, so a single scale is the wrong knob regardless.
        live_rows = [r for r in rows if (r["opp"], r["opp_ver"]) in current_builds]
        # Keyed by opponent rating *and* whether we chose the fixture, because the two carry
        # different amounts of evidence about the bot and must not be pooled into one cell.
        cells: dict[tuple[float, bool], list[float]] = defaultdict(lambda: [0.0, 0.0])
        for r in live_rows:
            weight = _recency_weight(r["t"], now_epoch)
            cell = cells[(round(r["opp_rating"], 3), r["kind"] == "unrated")]
            cell[0] += r["gf"] * weight
            cell[1] += r["ga"] * weight
        live_games = sum(r["gf"] + r["ga"] for r in live_rows)
        cell_rows = [
            (r, w, loss, selection_bonus if chosen else 0.0)
            for (r, chosen), (w, loss) in cells.items()
        ]
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
                live_rows, BOOTSTRAP_RESAMPLES, seed=abs(hash(key)) % 100000,
                selection_bonus=selection_bonus, now=now_epoch,
            )
            span = _interval(draws)
            # The headline is the simulated settled rating, not the one-parameter fit.
            #
            # The fit answers "what strength explains this record", which is only the same
            # question as "what rating will this hold" if a strength is a sufficient summary and
            # the ratings it was scored against still apply. Neither holds: the game is
            # non-transitive, and opponent ratings drift while their build stays deployed. So
            # the record is kept per opponent, re-anchored on their rating *now*, and played
            # forward through the real pairing kernel and the platform's own update rule.
            #
            # Measured against the rating each build actually held just before we swapped away
            # from it, this halves the error -- 62.3 Elo to 32.3 -- and cuts the bias from +58.5
            # to +19.7. The one-parameter fit stays published as `elo_strength_fit`, because it
            # is what every earlier number on this page meant and the two want comparing.
            #
            # An earlier note here argued the fixed point was worse in practice and kept theta as
            # the headline. That was measured on 7 stints before the field trebled; on 16 stints
            # the ordering reverses, and the reason it reverses is that rating drift grew.
            matchups: dict[object, tuple[float, float]] = {}
            tally: dict[object, list[float]] = defaultdict(lambda: [0.0, 0.0])
            for r in live_rows:
                rating_now = current_rating.get((r["opp"], r["opp_ver"]))
                if rating_now is None:
                    continue
                weight = _recency_weight(r["t"], now_epoch)
                cell = tally[(r["opp"], r["opp_ver"])]
                cell[0] += r["gf"] * weight
                cell[1] += r["ga"] * weight
            for opponent, (won, lost) in tally.items():
                played = won + lost
                if played <= 0:
                    continue
                rating_now = current_rating[opponent]
                prior = _expected(strength, rating_now)
                probability = (won + MATCHUP_PRIOR_GAMES * prior) / (played + MATCHUP_PRIOR_GAMES)
                matchups[opponent] = (rating_now, probability)
            settled = _simulate_settled_rating(
                matchups, us_rating, seed=abs(hash(key)) % 100000
            )
            headline = settled if settled is not None else strength
            # The interval comes from the bootstrap around the fit and is carried across to sit
            # on the headline. It is the right *width* -- the same evidence -- but it is not a
            # simulation interval, and should not be read as one.
            shift = headline - strength
            estimate = {
                "elo": headline,
                "elo_strength_fit": strength,
                "elo_simulated": settled,
                "elo_if_matchups_persist": _equilibrium(current_cells, strength, active_ratings),
                "matchup_dispersion": _overdispersion(current_cells, strength),
                "elo_lo": (span[0] + shift) if span else None,
                "elo_hi": (span[1] + shift) if span else None,
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

    # Every estimate exists before any of them can be corrected: shrinkage is a statement about
    # this build relative to the others, so it cannot be applied inside the loop that makes them.
    _shrink_towards_the_field(bots)

    # ---- each bot against each opponent build --------------------------------------------------
    matchups: dict[tuple[str, str, int], list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    for row in ours:
        cell = matchups[(bot_key(row["ver"]), row["opp"], row["opp_ver"])]
        cell[0] += 1 if row["win"] else 0
        cell[1] += 0 if row["win"] else 1
        cell[2] += row["gf"]
        cell[3] += row["ga"]
        # Split out so the site can show where a record came from. Both count towards the
        # estimate; a reader still wants to see which games were the ladder's choice of
        # opponent and which were ours.
        if row["kind"] == "ladder":
            cell[4] += row["gf"] + row["ga"]
        else:
            cell[5] += row["gf"] + row["ga"]
    matchup_rows = [
        {
            "key": key,
            "opponent": opp,
            "opponent_version": oppver,
            "wins": w,
            "losses": loss,
            "games_for": gf,
            "games_against": ga,
            "rated_games": rated_g,
            "unrated_games": unrated_g,
            "opponent_build_current": (opp, oppver) in current_builds,
        }
        for (key, opp, oppver), (w, loss, gf, ga, rated_g, unrated_g) in sorted(matchups.items())
    ]

    feed = {
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
            # Elo the farm's choice of opponent is worth. Every estimate below has it subtracted;
            # published so the size of the correction is visible rather than baked in silently.
            "selection_bonus": selection_bonus,
            "matches_in_history": len(ours),
            "matches_all_time": len(every),
        },
        "bots": bots,
        "opponents": opponents,
        "matchups": matchup_rows,
        "recent": [dict(r, key=bot_key(r["ver"])) for r in ours[:200]],
    }
    _attach_delta_elo(feed)
    return feed


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
