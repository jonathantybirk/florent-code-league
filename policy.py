"""Opponent selection policy -- the only file you need to touch to change who we play.

`choose_opponents(ctx)` gets a `Context` describing the ladder, the bot about to
be tested and what it has already faced, and returns the teams to challenge this
round. Everything else in the farm is fixed machinery; this is the decision.

Contract, enforced by farm.py:

* return **exactly `ctx.n`** rows taken from `ctx.ladder` (5 -- the rate limit is
  5 unrated matches per 10 minutes and a round spends all of them);
* never return ourselves, a `ladderBanned` team, or the same team twice;
* rows are ladder entries as the API returns them: `teamId`, `teamName`,
  `rating`, `_rank`, plus `ladderBanned`.

Test any change without touching the live ladder:

    python3 farm.py --once --dry-run

which prints the bot under test and the five teams this function chose.


WHY THIS IS A BATCH PROBLEM AND NOT FIVE SEPARATE ONES
------------------------------------------------------
All five matches in a round are chosen at once and fired together, so nothing
learned from the first can inform the third. The next round is a fresh decision
with updated evidence; within a round we are committing to a *set*.

That distinction only earns its keep if the thing being estimated has more than
one parameter. For a single scalar -- "our Elo" -- Fisher information is additive
and independent across trials, so the best set is just the five best singles and
a greedy pick is already optimal. Diversity would be a superstition.

So the model here has two parameters, and the second one is real:

    logit P(we win vs team j)  =  a  +  b * (r_us - r_j) * ln(10)/400

`a` is our level. `b` is how strongly the rating gap actually predicts our
results -- standard Elo assumes b = 1, and a bot is not obliged to obey it. A bot
with b < 1 is FLAT: it does better against strong teams and worse against weak
ones than its rating implies. b > 1 is SWINGY: it farms the bottom and folds at
the top. Two bots with identical Elo and different b have genuinely different
ladder prospects, because the scheduler does not pair uniformly.

And `b` cannot be identified from opponents at a single rating. Two matches at
the same `r_j` give a singular information matrix -- the design must span a range
of ratings or the slope is unknowable. That is where batch diversity stops being
a hunch and becomes arithmetic.


WHAT WE ACTUALLY MINIMISE
-------------------------
Not the uncertainty in `a` and `b` for their own sake, but the uncertainty in the
predictions we care about: how we will do against the teams the scheduler will
actually pair us with. That is kernel-weighted A-optimality,

    cost(S)  =  sum_k  K_k * x_k^T (M_prior + M_S)^-1 x_k

over every team k on the ladder, weighted by the measured probability K_k that a
rated pairing lands there. `M_S` is the Fisher information the candidate set S
would add. We pick the S of size 5 that minimises it, greedily -- each step adds
the team that removes the most remaining variance given everything already in the
basket, which automatically declines a second opponent that duplicates one
already chosen, because it barely moves the inverse.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

# Elo's logistic scale: P(win) = sigmoid(LN10_OVER_400 * (r_us - r_them)).
LN10_OVER_400 = math.log(10.0) / 400.0

# Rating spread used to normalise the slope coordinate, so `a` and `b` sit on
# comparable scales and the 2x2 information matrix stays well conditioned.
SPREAD = 200.0

# Prior precision on the two parameters when the feed gives us nothing. The level
# prior is deliberately weak; the slope prior is stronger because b = 1 is a
# genuinely good guess -- Elo is not arbitrary -- and we only want data to move it
# when the data insists.
PRIOR_LEVEL_SD = 300.0     # Elo points

# How unsure we are that our bots obey standard Elo. THIS CONSTANT DECIDES THE WHOLE
# POLICY, so it is worth being honest about: the batch is only different from picking
# the five best single matches to the extent that `b` is uncertain. Measured on the
# fixtures, from rank 6 --
#
#     slope SD 0.60  -> ranks 13,14,15,16,17   mean p(win) 0.81
#     slope SD 0.25  -> ranks  8, 9,10,11,12   mean p(win) 0.75
#     slope SD 0.05  -> ranks  1, 2, 3, 4, 5   mean p(win) 0.53   (identical to greedy)
#
# At b fixed to 1 the joint objective collapses exactly onto the greedy one, which is
# the correct behaviour and not a degenerate case: with one free parameter, Fisher
# information is additive and the best set really is the five best singles.
#
# Set tight, deliberately, because the errors are asymmetric. Believing b is uncertain
# when it is not spends the round on 80%-win matches worth 0.147 information each
# instead of even ones worth 0.249 -- a 40% loss on every game, every round. Believing
# b = 1 when it is not costs some precision at the edges of the pairing band, which is
# second order. So we assume standard Elo until the data says otherwise, and
# `calibrate_slope.py` on the farm machine is what says otherwise.
PRIOR_SLOPE_SD = 0.15      # multiples of the standard Elo slope

# How fast a rematch stops counting as new evidence. Applied to the time-decayed
# play count, so a team we have not met for days is fresh ground again.
NOVELTY_DECAY = 0.5

# The pairing kernel has FINITE SUPPORT -- it reaches about 11 ranks and is zero
# beyond. That zero is load-bearing, not a rounding detail. An earlier version gave
# out-of-reach teams a small floor so they still counted as prediction targets, and
# the design promptly collapsed onto them: ~90 distant teams at a token weight
# outvoted the ~22 real ones, and since distant teams are exactly what the SLOPE
# parameter governs, A-optimality answered correctly for the question it was asked
# and picked five opponents at p=0.90. Extreme design points have maximum leverage;
# that is a property of the criterion, not a bug in it. The fix is to ask the right
# question -- score variance only where a rated pairing can actually happen.
KERNEL_FLOOR = 0.0

# Shown in the round log, so it is obvious which policy is actually deployed.
NAME = "batch A-optimal: kernel-weighted prediction variance, 2-parameter Elo"


@dataclass
class Context:
    """Everything known when picking opponents."""

    ladder: list[dict]              # every team, ranked, us included
    me: dict | None                 # our own ladder row
    pool: list[dict]                # teams we are willing to play at all
    closest: list[dict]             # the teams nearest us in rating (qualification set)
    n: int                          # how many opponents to return
    bot_id: str                     # the bot about to be tested
    faced_ids: set[str] = field(default_factory=set)          # teams this bot has met
    series_by_team: dict[str, int] = field(default_factory=dict)  # this bot's series counts
    recent_by_team: dict[str, float] = field(default_factory=dict)
    # ^ the same counts decayed on the evidence half-life. A team we played six times
    #   last week is not a team we currently know anything about: they have shipped new
    #   builds since. Novelty is scored on this, falling back to the raw count.
    global_by_team: dict[str, int] = field(default_factory=dict)  # all bots' series counts
    filling_coverage: bool = False  # the live bot is under-covered and must re-qualify
    pairing_kernel: dict[int, float] = field(default_factory=dict)
    # ^ measured P(rated pairing is this many ranks away), from the live feed:
    #   {1: 0.242, 2: 0.201, 3: 0.183, 4: 0.142, 5: 0.109, 6: 0.065, ...} out to ~11.
    bot_elo: float | None = None    # live-feed Elo estimate for the bot under test
    bot_se: float | None = None     # half-width of that estimate, if the feed gives one

    @property
    def our_rank(self) -> int | None:
        return self.me["_rank"] if self.me else None

    @property
    def strength(self) -> float:
        """Best available estimate of how strong the bot under test actually is.

        The live feed's per-build Elo when it has one, because a bot under test is
        often nowhere near the team rating it plays under. Falls back to the team
        rating, which is what the ladder will actually pair on.
        """
        if self.bot_elo is not None:
            return self.bot_elo
        if self.me:
            return float(self.me.get("rating") or 1500.0)
        return 1500.0


# ----------------------------------------------------------------------------
# the model
# ----------------------------------------------------------------------------

def design_row(ctx: Context, row: dict) -> tuple[float, float]:
    """The regressor `x` for one opponent: (level, slope) coordinates."""
    gap = ctx.strength - float(row.get("rating") or 1500.0)
    return 1.0, gap / SPREAD


def win_probability(ctx: Context, row: dict) -> float:
    theirs = float(row.get("rating") or 1500.0)
    return 1.0 / (1.0 + 10.0 ** ((theirs - ctx.strength) / 400.0))


def kernel_weight(ctx: Context, rank: int) -> float:
    """How likely a rated pairing at this rank distance actually is.

    Zero outside the kernel's support, deliberately -- see KERNEL_FLOOR.
    """
    if ctx.our_rank is None or not ctx.pairing_kernel:
        return 1.0
    return max(ctx.pairing_kernel.get(abs(rank - ctx.our_rank), 0.0), KERNEL_FLOOR)


def novelty(ctx: Context, row: dict) -> float:
    played = ctx.recent_by_team.get(
        row["teamId"], float(ctx.series_by_team.get(row["teamId"], 0)))
    return 1.0 / math.sqrt(1.0 + played) ** (2 * NOVELTY_DECAY)


def trial_information(ctx: Context, row: dict) -> float:
    """Fisher information one game against `row` contributes, before the design.

    p(1-p) is the information of a single Bradley-Terry trial: maximal at an even
    match and near zero when the outcome is predictable, because beating a team we
    beat 95% of the time confirms what we already knew. Novelty discounts a
    rematch, which still informs about level but adds little about spread.
    """
    p = win_probability(ctx, row)
    return p * (1.0 - p) * novelty(ctx, row)


# ----------------------------------------------------------------------------
# 2x2 linear algebra, written out so this file needs no dependencies
# ----------------------------------------------------------------------------

def _add_outer(M: list[float], x: tuple[float, float], w: float) -> list[float]:
    """M + w * x x^T, with a symmetric 2x2 stored as [m00, m01, m11]."""
    a, b = x
    return [M[0] + w * a * a, M[1] + w * a * b, M[2] + w * b * b]


def _quad_inv(M: list[float], x: tuple[float, float]) -> float:
    """x^T M^-1 x for a symmetric 2x2, without forming the inverse."""
    m00, m01, m11 = M
    det = m00 * m11 - m01 * m01
    if det <= 1e-12:
        return float("inf")
    a, b = x
    return (m11 * a * a - 2.0 * m01 * a * b + m00 * b * b) / det


def prior_information(ctx: Context) -> list[float]:
    """What we already believe, as a precision matrix.

    The level precision comes from the live feed's interval when it has one, so a
    build with 140 games behind it is not re-measured as though it were new. The
    slope has no published estimate, so it carries a fixed weak prior centred on
    standard Elo.
    """
    level_sd = ctx.bot_se if ctx.bot_se and ctx.bot_se > 1.0 else PRIOR_LEVEL_SD
    return [1.0 / (level_sd / SPREAD) ** 2, 0.0, 1.0 / PRIOR_SLOPE_SD ** 2]


def pairing_targets(ctx: Context) -> list[dict]:
    """The teams a rated pairing can actually land on -- the kernel's support.

    This is the set whose outcomes we are trying to predict. Everything outside it
    is still a legal opponent (playing them is not forbidden) but is not something
    we are trying to get better at forecasting, so it does not vote on the design.
    """
    return [r for r in ctx.ladder
            if (not ctx.me or r["teamId"] != ctx.me["teamId"])
            and kernel_weight(ctx, r.get("_rank") or 0) > 0.0]


def prediction_cost(ctx: Context, M: list[float], targets: list[dict]) -> float:
    """Kernel-weighted variance of our predicted results across the ladder.

    This is what the round is spent to reduce: not "how well do we know our Elo"
    but "how well can we predict the matches we are actually going to be given".
    """
    total = 0.0
    for t in targets:
        k = kernel_weight(ctx, t.get("_rank") or 0)
        if k <= 0.0:
            continue
        total += k * _quad_inv(M, design_row(ctx, t))
    return total


# ----------------------------------------------------------------------------
# selection
# ----------------------------------------------------------------------------

def choose_opponents(ctx: Context) -> list[dict]:
    """Pick the SET of five whose results together shrink our predicted variance most.

    Greedy over the batch: start from what we already believe, then five times add
    whichever remaining team reduces the kernel-weighted prediction variance most,
    *given everything already in the basket*. That conditioning is what makes this
    a joint choice rather than five independent ones -- once a 1900-rated opponent
    is in the set, a second one barely moves the inverse and loses to a team that
    probes a different part of the curve.

    `filling_coverage` still overrides: when the live bot has fallen below the
    qualification bar, re-qualifying is not an information question.
    """
    rows = [r for r in ctx.pool if not r.get("ladderBanned")]
    if ctx.me:
        rows = [r for r in rows if r["teamId"] != ctx.me["teamId"]]
    if not rows:
        return []

    if ctx.filling_coverage:
        unfaced = [r for r in ctx.closest if r["teamId"] not in ctx.faced_ids]
        return _top_up(unfaced, rows, ctx)

    targets = pairing_targets(ctx)

    # DESIGN REGION. Candidates are restricted to the kernel's support, and this is
    # a modelling decision rather than a statistical one -- unconstrained
    # A-optimality does not want it. With the level already pinned by the feed, all
    # remaining value sits in the slope, and a team 400 Elo below us contributes
    # ~128x more slope information than an even match does, so the criterion
    # rationally spends the whole round on opponents we beat 90% of the time.
    #
    # It is answering the question it was asked. The question is wrong twice over:
    # the two-parameter model is a local approximation and is not credible that far
    # out, and those teams cannot be paired with us anyway, so a better estimate of
    # our results against them buys nothing. Optimal designs for linear models put
    # their mass on the boundary of the design region; the honest move is to set the
    # region to where the model is claimed to hold.
    in_band = [r for r in rows if kernel_weight(ctx, r.get("_rank") or 0) > 0.0]
    if len(in_band) >= ctx.n:
        rows = in_band
    random.shuffle(rows)                       # unbiased tie-breaking

    M = prior_information(ctx)
    chosen: list[dict] = []
    taken: set[str] = set()
    for _ in range(min(ctx.n, len(rows))):
        best, best_cost, best_M = None, float("inf"), None
        for row in rows:
            if row["teamId"] in taken:
                continue
            w = trial_information(ctx, row)
            if w <= 0.0:
                continue
            trial = _add_outer(M, design_row(ctx, row), w)
            cost = prediction_cost(ctx, trial, targets)
            if cost < best_cost:
                best, best_cost, best_M = row, cost, trial
        if best is None:
            break
        chosen.append(best)
        taken.add(best["teamId"])
        M = best_M
    return _top_up(chosen, rows, ctx)


def explain(ctx: Context, limit: int = 8) -> list[str]:
    """Show the batch being assembled, one marginal gain at a time."""
    rows = [r for r in ctx.pool if not r.get("ladderBanned")]
    if ctx.me:
        rows = [r for r in rows if r["teamId"] != ctx.me["teamId"]]
    targets = pairing_targets(ctx)
    in_band = [r for r in rows if kernel_weight(ctx, r.get("_rank") or 0) > 0.0]
    if len(in_band) >= ctx.n:
        rows = in_band                          # same design region as choose_opponents

    M = prior_information(ctx)
    out = [f"prior kernel-weighted prediction variance: {prediction_cost(ctx, M, targets):.4f}"]
    taken: set[str] = set()
    for step in range(ctx.n):
        scored = []
        for row in rows:
            if row["teamId"] in taken:
                continue
            w = trial_information(ctx, row)
            if w <= 0.0:
                continue
            scored.append(
                (prediction_cost(ctx, _add_outer(M, design_row(ctx, row), w), targets), row, w))
        if not scored:
            break
        scored.sort(key=lambda s: s[0])
        cost, row, w = scored[0]
        before = prediction_cost(ctx, M, targets)
        out.append(
            f"  pick {step + 1}: {row['teamName'][:24]:<24} #{row.get('_rank', '?'):<4} "
            f"r={float(row.get('rating') or 0):7.1f} p={win_probability(ctx, row):.2f} "
            f"info={w:.3f}  var {before:.4f} -> {cost:.4f}  (-{before - cost:.4f})")
        if len(scored) > 1:
            out.append(f"           runner-up {scored[1][1]['teamName'][:20]:<20} "
                       f"would leave {scored[1][0]:.4f}")
        M = _add_outer(M, design_row(ctx, row), w)
        taken.add(row["teamId"])
    return out[: 2 * limit + 1]


def _top_up(chosen: list[dict], rows: list[dict], ctx: Context) -> list[dict]:
    """Fill to ctx.n from the most individually informative teams, then trim.

    Only reached when the primary rule returns too few -- the `filling_coverage`
    path, or a pool smaller than n. Keeps the contract either way.
    """
    seen = {r["teamId"] for r in chosen}
    spare = sorted(rows, key=lambda r: -trial_information(ctx, r))
    for row in spare:
        if len(chosen) >= ctx.n:
            break
        if row["teamId"] not in seen:
            chosen.append(row)
            seen.add(row["teamId"])
    return chosen[: ctx.n]
