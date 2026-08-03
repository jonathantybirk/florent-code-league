"""Turn Ratings into ratings.csv and a readable table."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from tournament.rating import ELO_PER_LOGIT, Ratings

NASH_DECIMALS = 6

COLUMNS = [
    "rank",
    "bot_id",
    "name",
    "commit",
    "games",
    "wins",
    "draws",
    "losses",
    "win_rate",
    "melo_r",
    "melo_r_elo",
    "melo_fit_r",
    "melo_c_1",
    "melo_c_2",
    "nash_prob",
    "nash_average",
    "nash_rank",
    "rank_delta",
]


def records(ratings: Ratings, meta: dict[str, dict]) -> list[dict]:
    games = ratings.games.sum(axis=1)
    scored = ratings.wins.sum(axis=1)
    draws = ratings.draws.sum(axis=1)
    wins = scored - 0.5 * draws
    losses = games - wins - draws

    order = np.argsort(-ratings.transitive)
    # Nash averages are ordered on a rounded key, then melo_r breaks ties within one score. Bots
    # that share a score share a rank (competition ranking: 1, 1, 1, 4), because "first" here is a
    # property of the score, not of the tiebreak -- every core agent ties at 0 by construction, and
    # numbering them 1..4 would invent an ordering the equilibrium does not assert. melo_r still
    # decides the order they are listed in.
    # Ties are judged at the precision the row actually publishes. A tighter key would split the
    # core on solver noise: every support member is 0 by construction, but the equilibrium solve
    # returns them as 0.0 and -3e-9, which are the same published number and must rank the same.
    nash_key = -np.round(ratings.nash_average, NASH_DECIMALS)
    nash_order = np.lexsort((-ratings.transitive, nash_key))
    nash_rank: dict[int, int] = {}
    for position, index in enumerate(nash_order):
        index = int(index)
        if position and nash_key[index] == nash_key[int(nash_order[position - 1])]:
            nash_rank[index] = nash_rank[int(nash_order[position - 1])]
        else:
            nash_rank[index] = position + 1

    rows = []
    for position, index in enumerate(order, start=1):
        index = int(index)
        bot = ratings.bots[index]
        info = meta.get(bot, {})
        rows.append(
            {
                "rank": position,
                "bot_id": bot,
                "name": info.get("name", bot.split("@")[0]),
                "commit": info.get("commit", "")[:7],
                "games": int(games[index]),
                "wins": int(wins[index]),
                "draws": int(draws[index]),
                "losses": int(losses[index]),
                "win_rate": round(float(scored[index] / games[index]) if games[index] else 0.0, 4),
                "melo_r": round(float(ratings.transitive[index]), 6),
                "melo_r_elo": round(float(ratings.transitive[index] * ELO_PER_LOGIT), 1),
                "melo_fit_r": round(float(ratings.melo_r[index]), 6),
                "melo_c_1": round(float(ratings.melo_c[index, 0]), 6)
                if ratings.melo_c.shape[1] > 0
                else 0.0,
                "melo_c_2": round(float(ratings.melo_c[index, 1]), 6)
                if ratings.melo_c.shape[1] > 1
                else 0.0,
                "nash_prob": round(float(ratings.nash[index]), 6),
                "nash_average": round(float(ratings.nash_average[index]), NASH_DECIMALS),
                "nash_rank": nash_rank[index],
                "rank_delta": position - nash_rank[index],
            }
        )
    return rows


def write_csv(
    ratings: Ratings,
    meta: dict[str, dict],
    path: Path,
) -> list[dict]:
    rows = records(ratings, meta)
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows


def render(ratings: Ratings, rows: list[dict], dropped: int = 0) -> str:
    """A table ranked by the mElo transitive component, with Nash alongside."""
    lines: list[str] = []
    header = (
        f"{'#':>3}  {'bot':<28} {'games':>6} {'win%':>6} "
        f"{'mElo r':>9} {'(Elo)':>8} {'nash p':>8} {'nash avg':>9} {'d':>4}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for row in rows:
        marker = "*" if row["nash_prob"] > 0 else " "
        delta = f"{row['rank_delta']:+d}" if row["rank_delta"] else "."
        lines.append(
            f"{row['rank']:>3}{marker} {row['bot_id']:<28} {row['games']:>6} "
            f"{100 * row['win_rate']:>5.1f}% {row['melo_r']:>9.4f} {row['melo_r_elo']:>8.0f} "
            f"{row['nash_prob']:>8.4f} {row['nash_average']:>9.4f} {delta:>4}"
        )

    support = [row["bot_id"] for row in rows if row["nash_prob"] > 0]
    melo = ratings.fit.get("melo_2k", {})
    elo = ratings.fit.get("elo", {})

    n = len(ratings.bots)
    possible = n * (n - 1) // 2
    played = int((np.triu(ratings.games, 1) > 0).sum())
    coverage = played / possible if possible else 1.0

    lines.append("")
    lines.append("Ranked by melo_r, the transitive component of mElo: r = div(A), A = logit(P).")
    missing = ratings.missing_pairs
    if missing:
        # An unplayed pair contributes A_ij = 0, which reads as "evenly matched" rather than
        # "unknown". That inflates the apparent cycle structure and can park most of the field in
        # the Nash support at equal mass. There is deliberately no coverage threshold below which
        # this is skipped: a single imputed pair can decide the Nash support, so every gap is
        # named. Silence here would be a claim that the matrix is complete.
        lines.append(
            f"  !! INCOMPLETE: {played}/{possible} pairs ({100 * coverage:.2f}%) have played. "
            f"The {len(missing)} unplayed pair(s) below enter A as 0, which is indistinguishable "
            f"from a measured 50/50 record. This ranking is provisional until they are played."
        )
        for left, right in missing[:20]:
            lines.append(f"       unplayed: {left}  vs  {right}")
        if len(missing) > 20:
            lines.append(f"       ... and {len(missing) - 20} more (see the run's ratings.csv)")
    lines.append(
        f"  * = in the support of the maxent Nash equilibrium ('core agents', tied at the top "
        f"with nash_average 0): {', '.join(support) if support else 'none'}"
    )
    lines.append(
        f"  d = mElo rank minus Nash rank. Non-zero means the two methods disagree about a bot; "
        f"positive = Nash rates it higher."
    )
    lines.append(
        f"  intransitivity ||rot(A)||/||A|| = {ratings.intransitivity:.3f}  "
        f"(0 = a pure pecking order, 1 = pure rock-paper-scissors)"
    )
    if melo and elo:
        lines.append(
            f"  fit: mElo_2k({ratings.fit.get('k')}) Frobenius {melo['frobenius']:.4f} / "
            f"log-loss {melo['log_loss']:.4f}   vs   Elo {elo['frobenius']:.4f} / "
            f"{elo['log_loss']:.4f}"
        )
    if dropped:
        lines.append(f"  {dropped} match(es) excluded: status != ok")
    return "\n".join(lines)
