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

import random
from dataclasses import dataclass, field


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
    global_by_team: dict[str, int] = field(default_factory=dict)  # all bots' series counts
    filling_coverage: bool = False  # the live bot is under-covered and must re-qualify
    pairing_kernel: dict[int, float] = field(default_factory=dict)
    # ^ measured P(rated pairing is this many ranks away), from the live feed:
    #   {1: 0.242, 2: 0.201, 3: 0.183, 4: 0.142, 5: 0.109, 6: 0.065, ...} out to ~11.
    #   This is the empirical answer to "who do we actually get paired against".

    @property
    def our_rank(self) -> int | None:
        return self.me["_rank"] if self.me else None


def choose_opponents(ctx: Context) -> list[dict]:
    """Default policy: the top of the ladder, our own neighbourhood, and some spread.

    Two from the top 5, two from within +-5 ranks of us, one from the wider pool.
    Inside each band the team *this bot* has faced least goes first, so a bot
    under test spreads over the field instead of re-fighting the same few.

    When `filling_coverage` is set the live bot has fallen below the
    qualification bar, so the whole round goes to close opponents it has not met.
    """
    rows = [r for r in ctx.pool if not r.get("ladderBanned")]
    if ctx.me:
        rows = [r for r in rows if r["teamId"] != ctx.me["teamId"]]

    if ctx.filling_coverage:
        unfaced = [r for r in ctx.closest if r["teamId"] not in ctx.faced_ids]
        return _top_up(unfaced, rows, ctx)

    def band(predicate) -> list[dict]:
        band_rows = [r for r in rows if predicate(r["_rank"])]
        random.shuffle(band_rows)  # break ties between equally-sampled teams
        return sorted(band_rows, key=lambda r: (ctx.series_by_team.get(r["teamId"], 0),
                                                ctx.global_by_team.get(r["teamId"], 0)))

    top = band(lambda rank: rank <= 5)
    near = band(lambda rank: ctx.our_rank is not None and abs(rank - ctx.our_rank) <= 5)
    wide = band(lambda _: True)

    chosen: list[dict] = []
    seen: set[str] = set()
    for pool, count in ((top, 2), (near, 2), (wide, 1)):
        taken = 0
        for row in pool:
            if taken >= count:
                break
            if row["teamId"] in seen:
                continue
            chosen.append(row)
            seen.add(row["teamId"])
            taken += 1
    return _top_up(chosen, rows, ctx)


def _top_up(chosen: list[dict], rows: list[dict], ctx: Context) -> list[dict]:
    """Fill to ctx.n from the least-played teams, then trim. Keeps the contract."""
    seen = {r["teamId"] for r in chosen}
    spare = sorted(rows, key=lambda r: (ctx.series_by_team.get(r["teamId"], 0),
                                        ctx.global_by_team.get(r["teamId"], 0)))
    for row in spare:
        if len(chosen) >= ctx.n:
            break
        if row["teamId"] not in seen:
            chosen.append(row)
            seen.add(row["teamId"])
    return chosen[: ctx.n]
