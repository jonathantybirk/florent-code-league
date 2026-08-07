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
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


# Shown in the round log, so it is obvious which policy is actually deployed.
# Change it when you change the policy.
NAME = "infogain: kernel-weighted Fisher information per unrated match"

# How hard to prefer an opponent this bot has never met over one it has played.
# A rematch still carries information about our bot's Elo, so this decays as
# 1/sqrt(1+n) rather than forbidding repeats: at n=0 the weight is 1.00, at n=1
# 0.71, at n=4 0.45. Coverage is a strong preference, not a rule.
NOVELTY_DECAY = 0.5

# Weight given to a rank distance the measured pairing kernel does not cover.
# The kernel reaches ~11 ranks; beyond that a rated pairing is close to
# impossible, so results there tell us almost nothing about our rated Elo -- but
# not literally nothing, because the ladder reshuffles.
KERNEL_FLOOR = 0.002


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
    #   This is the empirical answer to "who do we actually get paired against".
    bot_elo: float | None = None    # live-feed Elo estimate for the bot under test
    bot_se: float | None = None     # half-width of that estimate, if the feed gives one

    @property
    def our_rank(self) -> int | None:
        return self.me["_rank"] if self.me else None

    @property
    def strength(self) -> float:
        """Best available estimate of how strong the bot under test actually is.

        The live feed's per-build Elo when it has one, because a bot under test is
        often nowhere near the team rating it is playing under. Falls back to the
        team rating, which is what the ladder will actually pair on.
        """
        if self.bot_elo is not None:
            return self.bot_elo
        if self.me:
            return float(self.me.get("rating") or 1500.0)
        return 1500.0


def _expected_score(ours: float, theirs: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((theirs - ours) / 400.0))


def _kernel_weight(ctx: Context, rank: int) -> float:
    """How likely a rated pairing at this rank distance actually is."""
    if ctx.our_rank is None:
        return 1.0
    d = abs(rank - ctx.our_rank)
    if not ctx.pairing_kernel:
        return 1.0
    return max(ctx.pairing_kernel.get(d, 0.0), KERNEL_FLOOR)


def information(ctx: Context, row: dict) -> float:
    """Expected Fisher information about our bot's Elo from one game against `row`.

    Three factors, and each is doing real work:

    1. **p(1-p)** -- the Fisher information of a single Bradley-Terry trial. It is
       maximised at p = 0.5 and collapses towards zero as the match becomes
       predictable. Beating a team we beat 95% of the time tells us almost
       nothing we did not already know; the games that move an estimate are the
       ones we might lose.

    2. **The pairing kernel** -- we do not care about our Elo in the abstract, we
       care about our Elo *against the teams the scheduler will actually pair us
       with*. The feed measured that distribution over 12k pairings, so an
       opponent 1 rank away is worth ~0.242 and one 9 ranks away ~0.006. Without
       this the policy would happily spend the whole budget learning about teams
       we will never meet.

    3. **Novelty** -- a rematch still informs, but a first meeting also tells us
       something about matchup spread rather than just level. Decays as
       1/sqrt(1+n) so coverage is preferred without repeats being banned -- and n
       is itself time-decayed, so a team we have not met for days counts as fresh
       ground again, because by then they are fielding a different bot.
    """
    theirs = float(row.get("rating") or 1500.0)
    p = _expected_score(ctx.strength, theirs)
    fisher = p * (1.0 - p)
    kernel = _kernel_weight(ctx, row.get("_rank") or 0)
    played = ctx.recent_by_team.get(
        row["teamId"], float(ctx.series_by_team.get(row["teamId"], 0)))
    novelty = 1.0 / math.sqrt(1.0 + played) ** (2 * NOVELTY_DECAY)
    return fisher * kernel * novelty


def choose_opponents(ctx: Context) -> list[dict]:
    """Spend the round on the five matches that most reduce uncertainty.

    The farm's budget is 5 unrated matches per 10 minutes and its job is no longer
    to find our best bot -- the internal tournament already ranks those far more
    cheaply than live matches can. What live matches uniquely buy is knowledge of
    how our builds perform against *the actual ladder*, and that knowledge is
    worth most where it is currently least certain.

    So opponents are scored by expected Fisher information about the bot under
    test, weighted by how likely the scheduler is to pair us with them for real.
    An evenly-matched neighbour scores highest; a team we would beat or lose to
    95% of the time scores near zero however convenient it is to play.

    `filling_coverage` still overrides everything: when the live bot has fallen
    below the qualification bar, re-qualifying is not an information question.
    """
    rows = [r for r in ctx.pool if not r.get("ladderBanned")]
    if ctx.me:
        rows = [r for r in rows if r["teamId"] != ctx.me["teamId"]]

    if ctx.filling_coverage:
        unfaced = [r for r in ctx.closest if r["teamId"] not in ctx.faced_ids]
        return _top_up(unfaced, rows, ctx)

    random.shuffle(rows)                      # break exact ties without bias
    ranked = sorted(rows, key=lambda r: -information(ctx, r))
    return _top_up(ranked[: ctx.n], rows, ctx)


def explain(ctx: Context, limit: int = 8) -> list[str]:
    """Human-readable scoring, for `--dry-run` and for arguing with the policy."""
    rows = [r for r in ctx.pool if not r.get("ladderBanned")]
    if ctx.me:
        rows = [r for r in rows if r["teamId"] != ctx.me["teamId"]]
    out = []
    for r in sorted(rows, key=lambda r: -information(ctx, r))[:limit]:
        theirs = float(r.get("rating") or 1500.0)
        p = _expected_score(ctx.strength, theirs)
        out.append(
            f"{r['teamName'][:28]:<28} #{r.get('_rank', '?'):<4} "
            f"r={theirs:7.1f} p(win)={p:.2f} fisher={p * (1 - p):.3f} "
            f"kernel={_kernel_weight(ctx, r.get('_rank') or 0):.3f} "
            f"played={ctx.recent_by_team.get(r['teamId'], float(ctx.series_by_team.get(r['teamId'], 0))):.1f} "
            f"-> {information(ctx, r):.5f}"
        )
    return out


def _top_up(chosen: list[dict], rows: list[dict], ctx: Context) -> list[dict]:
    """Fill to ctx.n from the most informative remaining teams, then trim.

    Keeps the contract even when the primary rule returns too few -- which happens
    on the `filling_coverage` path, where the unfaced set can be smaller than n.
    """
    seen = {r["teamId"] for r in chosen}
    spare = sorted(rows, key=lambda r: -information(ctx, r))
    for row in spare:
        if len(chosen) >= ctx.n:
            break
        if row["teamId"] not in seen:
            chosen.append(row)
            seen.add(row["teamId"])
    return chosen[: ctx.n]
