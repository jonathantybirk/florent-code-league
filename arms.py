"""Which bot to test next, and how good we currently think each one is.

Candidate bots ("arms") come from the newest finished CI tournament run: anything
that reaches the top of the internal leaderboard on any of the three metrics we
trust -- mElo rank, Nash core membership, or Nash-average rank -- is worth
spending live challenges on. Selection between them is UCB1 over the online game
win rate, so a promising newcomer gets tried without abandoning the incumbent.

Bot strength is reported as an Elo estimate rather than a raw win rate, because
the farm deliberately faces opponents of different strengths and a win rate is
meaningless without knowing who it was against.
"""

from __future__ import annotations

import csv
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"
BOT_REPO = Path("/home/Ucals/projects/florent-code-league-llm-rl")

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
    """Bots in the top `top_n` of mElo or Nash average, plus the whole Nash core."""
    path = newest_ratings_csv()
    if path is None:
        return []
    rows = list(csv.DictReader(path.open()))
    picked: dict[str, dict] = {}
    for row in rows:
        melo_rank = int(row["rank"])
        nash_rank = int(row["nash_rank"])
        nash_prob = float(row["nash_prob"])
        reasons = []
        if melo_rank <= top_n:
            reasons.append(f"melo#{melo_rank}")
        if nash_rank <= top_n:
            reasons.append(f"nash_avg#{nash_rank}")
        if nash_prob > 0:
            reasons.append(f"nash_core={nash_prob:.3f}")
        if not reasons:
            continue
        picked[row["bot_id"]] = {
            "bot_id": row["bot_id"],
            "name": row["name"],
            "commit": row["commit"],
            "melo_rank": melo_rank,
            "melo_elo": float(row["melo_r_elo"]),
            "nash_rank": nash_rank,
            "nash_prob": nash_prob,
            "offline_win_rate": float(row["win_rate"]),
            "reasons": ",".join(reasons),
            "run": path.parent.name,
        }
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
