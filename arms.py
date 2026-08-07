"""Which bot to test next, and how good we currently think each one is.

The candidate set is deliberately small and mutually exclusive, in three tiers:

  1. the whole **Nash core** -- the bots a Nash-averaging ladder actually samples,
     which is the set that matters if opponents adapt;
  2. the **top three by mElo** among bots not already in the core;
  3. the **single highest offline win rate** among bots in neither tier.

At most seven arms. The tiers are exclusive on purpose: a bot in the Nash core
does not also consume one of the mElo slots, so the set spans three genuinely
different notions of "good" instead of three views of the same two bots.

Selection between them is NOT a search for the best bot. The internal tournament
already ranks our builds over thousands of games far more cheaply than live
matches can, so spending a 5-per-10-minute live budget re-deciding that is waste.
What live matches uniquely buy is knowledge of how a build performs against the
*actual ladder*, and that is worth most where it is currently least certain. So
the arm with the widest confidence interval is tested next: total uncertainty is
the sum of per-bot variances, and the myopic move that shrinks it fastest is to
sample the least certain bot.

Bot strength is reported as an Elo estimate rather than a raw win rate, because
the farm deliberately faces opponents of different strengths and a win rate is
meaningless without knowing who it was against.
"""

from __future__ import annotations

import csv
import math
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Absolute, because the farm no longer lives inside the tournament checkout: it
# deploys from its own branch and must still find the CI runs and the git history
# the bots are extracted from. Override per machine with the env vars.
RUNS_DIR = Path(os.environ.get(
    "LADDERFARM_RUNS", "/home/Ucals/projects/florent-code-league-ci/tournament/runs"))
BOT_REPO = Path(os.environ.get(
    "LADDERFARM_BOT_REPO", "/home/Ucals/projects/florent-code-league-llm-rl"))

LN10_OVER_400 = math.log(10) / 400.0


# --------------------------------------------------------------------------
# internal leaderboard
# --------------------------------------------------------------------------

# Which internal leaderboard nominates candidates. The `auto-*` runs the CI
# evaluator produces are on a different (older) map set, and one of them finishing
# would otherwise win on mtime and quietly become the source. Set to "" to just
# take the newest run of any kind.
LEADERBOARD_PREFIX = "v3-"


def newest_ratings_csv() -> Path | None:
    by_mtime = sorted(
        RUNS_DIR.glob("*/ratings.csv"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    preferred = [p for p in by_mtime if p.parent.name.startswith(LEADERBOARD_PREFIX)]
    return (preferred or by_mtime or [None])[0]


def leaderboard_candidates(top_n: int = 3) -> list[dict]:
    """The Nash core, plus the best `top_n` by mElo outside it, plus one on win rate.

    Exclusive tiers, evaluated in order, so a bot is nominated by exactly one
    reason and the set spans three different definitions of strength rather than
    listing the same bots three times.
    """
    path = newest_ratings_csv()
    if path is None:
        return []
    rows = list(csv.DictReader(path.open()))

    def entry(row, reason):
        return {
            "bot_id": row["bot_id"],
            "name": row["name"],
            "commit": row["commit"],
            "melo_rank": int(row["rank"]),
            "melo_elo": float(row["melo_r_elo"]),
            "nash_rank": int(row["nash_rank"]),
            "nash_prob": float(row["nash_prob"]),
            "offline_win_rate": float(row["win_rate"]),
            "reasons": reason,
            "run": path.parent.name,
        }

    picked = {}

    # Tier 1 -- the Nash core, however large it is.
    for row in rows:
        if float(row["nash_prob"]) > 0:
            picked[row["bot_id"]] = entry(row, "nash_core=%.3f" % float(row["nash_prob"]))

    # Tier 2 -- the best by mElo that the core did not already claim.
    rest = [r for r in rows if r["bot_id"] not in picked]
    rest.sort(key=lambda r: -float(r["melo_r_elo"]))
    for row in rest[:top_n]:
        picked[row["bot_id"]] = entry(row, "melo#%d" % int(row["rank"]))

    # Tier 3 -- one more on raw offline win rate, from whatever is left.
    rest = [r for r in rows if r["bot_id"] not in picked]
    if rest:
        best = max(rest, key=lambda r: float(r["win_rate"]))
        picked[best["bot_id"]] = entry(best, "win_rate=%.3f" % float(best["win_rate"]))

    return list(picked.values())


def resolve_source_path(name: str, commit: str) -> str | None:
    """Find `bots/<owner>/<name>` inside the given commit, across every branch."""
    try:
        listing = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", commit],
            cwd=BOT_REPO,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.SubprocessError:
        return None
    if listing.returncode != 0:
        return None
    for line in listing.stdout.splitlines():
        if line.endswith(f"/{name}/main.py") and line.startswith("bots/"):
            return line[: -len("/main.py")]
    return None


def export_bot(name: str, commit: str, dest: Path) -> Path | None:
    """Extract a bot out of git into `dest` without touching any working tree."""
    source = resolve_source_path(name, commit)
    if source is None:
        return None
    dest.mkdir(parents=True, exist_ok=True)
    depth = len(Path(source).parts)
    archive = subprocess.run(
        ["git", "archive", commit, source], cwd=BOT_REPO, capture_output=True, timeout=120
    )
    if archive.returncode != 0:
        return None
    untar = subprocess.run(
        ["tar", "-x", "-C", str(dest), f"--strip-components={depth}"],
        input=archive.stdout,
        capture_output=True,
        timeout=120,
    )
    if untar.returncode != 0 or not (dest / "main.py").exists():
        return None
    return dest


# --------------------------------------------------------------------------
# strength estimation
# --------------------------------------------------------------------------

@dataclass
class ArmStats:
    """Online record of one bot, one entry per *game* played."""

    bot_id: str
    games: list[tuple[float, bool]] = field(default_factory=list)  # (opponent_rating, we_won)
    series: int = 0

    @property
    def n_games(self) -> int:
        return len(self.games)

    @property
    def wins(self) -> int:
        return sum(1 for _, won in self.games if won)

    @property
    def win_rate(self) -> float:
        return self.wins / self.n_games if self.games else 0.0

    def elo(self, prior_rating: float, prior_weight: float = 2.0) -> tuple[float, float]:
        """Maximum-likelihood Elo against the opponents actually faced.

        Returns (estimate, standard error). A weak prior of `prior_weight`
        pseudo-games split at `prior_rating` keeps the estimate finite when a bot
        has swept or been swept, which five-game samples do routinely.
        """
        obs = list(self.games)
        obs += [(prior_rating, True)] * 1 * int(prior_weight / 2)
        obs += [(prior_rating, False)] * 1 * int(prior_weight / 2)
        if not obs:
            return prior_rating, 400.0

        def score(r: float) -> float:
            return sum(
                (1.0 if won else 0.0) - 1.0 / (1.0 + 10 ** ((opp - r) / 400.0))
                for opp, won in obs
            )

        lo, hi = prior_rating - 1200.0, prior_rating + 1200.0
        for _ in range(60):
            mid = (lo + hi) / 2
            if score(mid) > 0:
                lo = mid
            else:
                hi = mid
        est = (lo + hi) / 2
        info = sum(
            (p := 1.0 / (1.0 + 10 ** ((opp - est) / 400.0))) * (1 - p) for opp, _ in obs
        )
        se = (1.0 / LN10_OVER_400) / math.sqrt(max(info, 1e-9))
        return est, se


def ucb_select(
    stats: dict[str, ArmStats], candidates: list[str], c: float = 0.6
) -> tuple[str, str]:
    """UCB1 over game win rate. Returns (bot_id, why)."""
    unplayed = [b for b in candidates if stats.get(b) is None or stats[b].n_games == 0]
    if unplayed:
        return unplayed[0], "never tested online"

    total = sum(stats[b].n_games for b in candidates)
    best, best_score, detail = None, -1e9, ""
    for bot_id in candidates:
        st = stats[bot_id]
        bonus = c * math.sqrt(2 * math.log(max(total, 2)) / st.n_games)
        score = st.win_rate + bonus
        if score > best_score:
            best, best_score, detail = (
                bot_id,
                score,
                f"ucb={score:.3f} (win_rate={st.win_rate:.3f} + bonus={bonus:.3f}, n={st.n_games})",
            )
    return best, detail


def uncertainty_select(stats, candidates, team_rating=1500.0):
    """Test the arm we know least about. Returns (bot_id, why).

    Total uncertainty over the candidate set is the sum of per-bot variances, so
    the myopic choice that shrinks it fastest is the bot with the widest standard
    error -- uncertainty sampling, and here it is also the honest objective: we
    are trying to characterise the set, not crown a member of it.

    Untested bots come first because their standard error is unbounded, not merely
    large. Beyond that this converges naturally on broad coverage: every series
    narrows one bot's interval, which promotes the next widest, so the budget
    spreads across the set instead of pouring into the incumbent.
    """
    unplayed = [b for b in candidates if stats.get(b) is None or stats[b].n_games == 0]
    if unplayed:
        return unplayed[0], "never tested online (unbounded uncertainty)"

    best, best_se, detail = None, -1.0, ""
    for bot_id in candidates:
        st = stats[bot_id]
        est, se = st.elo(team_rating)
        if se > best_se:
            best, best_se, detail = (
                bot_id, se,
                "widest interval: elo=%.0f +-%.0f over n=%d" % (est, se, st.n_games))
    return best, detail
