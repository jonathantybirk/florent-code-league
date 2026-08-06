"""Farm unrated ladder matches for data, one round of five per invocation.

A round is: collect whatever finished since last time, pick a bot to test (UCB
over the candidates the internal leaderboard nominates), pick five opponents
spread across the top of the ladder and our own neighbourhood, fire the five
challenges with that bot active, and put the flagship straight back.

The active submission is only ever off the flagship for the couple of seconds
the five requests take, and never within the window where the ladder scheduler
queues rated matches -- `fcode match unrated` snapshots the active submission at
request time, so nothing is gained by leaving a test bot live.

Usage:
    python farm.py --once        # one round (what the systemd timer runs)
    python farm.py --collect     # only harvest finished matches, fire nothing
    python farm.py --status      # arms, live-feed Elo estimates, qualification
    python farm.py --once --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import arms
import fcodecli as fc
import live as livefeed
import policy

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
STATE_PATH = HERE / "state.json"
SERIES_CSV = HERE / "data" / "series.csv"
GAMES_CSV = HERE / "data" / "games.csv"
PAUSE_FILE = HERE / "PAUSE"
CONFIG_PATH = HERE / "config.json"
LOG_PATH = HERE / "farm.log"

# The ladder scheduler queues rated matches ~2:43 past every ten-minute mark.
# Test bots stay off the active submission for two minutes either side of it.
PAIRING_SECONDS = 163
DANGER_BEFORE, DANGER_AFTER = 120, 120

CHALLENGES_PER_ROUND = 5  # the platform's rate limit is 5 per 10 minutes per account

SERIES_FIELDS = [
    "fired_at", "collected_at", "bot_id", "bot_name", "bot_commit", "version",
    "match_id", "opponent", "opponent_id", "opponent_rank", "opponent_rating",
    "opponent_version", "our_score", "their_score", "our_side",
]
GAMES_FIELDS = [
    "match_id", "bot_id", "opponent", "opponent_rating", "game_number", "map",
    "map_seed", "we_won", "win_condition", "turns",
]

log = logging.getLogger("ladderfarm")


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

def go_offline() -> None:
    """Run every decision against committed fixtures instead of the network.

    So the logic can be developed on a machine with no credentials, no bot repo
    and no CI runs -- which is every machine except the one that hosts the farm.
    Nothing here can fire a challenge: --offline implies --dry-run.
    """
    import json as _json

    ladder = _json.loads((FIXTURES / "ladder.json").read_text())
    feed = _json.loads((FIXTURES / "live.json").read_text())
    fc.ladder = lambda limit=100: ladder                      # type: ignore[assignment]
    fc.active_version = lambda: load_state().get("flagship_version") or 0  # type: ignore
    livefeed.load = lambda: feed                              # type: ignore[assignment]
    arms.newest_ratings_csv = lambda: FIXTURES / "ratings.csv"  # type: ignore[assignment]
    # export_bot shells into the bot repo's git history, which an offline machine
    # does not have; pretend the export succeeded so selection can be exercised
    arms.export_bot = lambda name, commit, dest: dest          # type: ignore[assignment]
    log.info("offline: ladder, live feed and ratings come from fixtures/")


def load_config() -> dict:
    """Tracked config -- editable by anyone who can push to the branch."""
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (OSError, ValueError):
        return {}


def firing_allowed(config: dict) -> tuple[bool, str]:
    """Whether this round may spend rate-limit slots, and why not if it may not.

    The farm eats nearly the whole 5-per-10-minutes account budget, so a human
    who wants to test their own bot needs a way to take it back -- and everyone
    who might need that works from a different machine, so the switch has to be
    something they can push rather than a file on this one.
    """
    if not config.get("enabled", True):
        return False, "config.json has enabled=false"
    until = config.get("yield_until")
    if until:
        try:
            deadline = datetime.fromisoformat(str(until).replace("Z", "+00:00"))
        except ValueError:
            return True, ""
        if datetime.now(timezone.utc) < deadline:
            return False, f"yielding the rate limit until {until}"
    return True, ""


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {
        "flagship_version": None,
        "uploads": {},      # bot_id -> {"version": int, "name": str, "uploaded_at": str}
        "pending": [],      # match records awaiting completion
        "opponent_games": {},
        "promotions": [],
        "rounds": 0,
    }


def save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    tmp.replace(STATE_PATH)


def append_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        if new:
            writer.writeheader()
        writer.writerows(rows)


def read_arm_stats() -> dict[str, arms.ArmStats]:
    """Rebuild per-bot online records from the harvested game log."""
    stats: dict[str, arms.ArmStats] = {}
    if GAMES_CSV.exists():
        for row in csv.DictReader(GAMES_CSV.open()):
            st = stats.setdefault(row["bot_id"], arms.ArmStats(row["bot_id"]))
            st.games.append((float(row["opponent_rating"]), row["we_won"] == "True"))
    if SERIES_CSV.exists():
        for row in csv.DictReader(SERIES_CSV.open()):
            st = stats.setdefault(row["bot_id"], arms.ArmStats(row["bot_id"]))
            st.series += 1
    return stats


# --------------------------------------------------------------------------
# timing safety
# --------------------------------------------------------------------------

def seconds_into_cycle(now: float | None = None) -> int:
    return int((now or time.time()) % 600)


def in_pairing_window(now: float | None = None) -> bool:
    s = seconds_into_cycle(now)
    return PAIRING_SECONDS - DANGER_BEFORE <= s <= PAIRING_SECONDS + DANGER_AFTER


# --------------------------------------------------------------------------
# opponents
# --------------------------------------------------------------------------

POOL_DEPTH = 25  # everyone we are willing to sample

# Qualification to be the live bot: enough of the opponents nearest us in rating.
# The full ladder is not worth waiting for -- what decides our rated results is
# the teams we actually get paired against, and those are the close ones.
CLOSEST_K = 10
QUALIFY_MIN = 7


def sampling_pool(ladder_rows: list[dict]) -> list[dict]:
    """The teams the farm draws from: the top of the ladder plus our neighbourhood."""
    our_rank = next((r["_rank"] for r in ladder_rows if r["teamId"] == fc.TEAM_ID), None)
    return [
        r for r in ladder_rows
        if r["teamId"] != fc.TEAM_ID
        and not r.get("ladderBanned")
        and (r["_rank"] <= POOL_DEPTH
             or (our_rank is not None and abs(r["_rank"] - our_rank) <= 5))
    ]


def closest_opponents(ladder_rows: list[dict], k: int = CLOSEST_K) -> list[dict]:
    """The k teams nearest to us in rating -- who our rated results actually turn on."""
    ours = next((r["rating"] for r in ladder_rows if r["teamId"] == fc.TEAM_ID), None)
    if ours is None:
        return []
    others = [r for r in ladder_rows if r["teamId"] != fc.TEAM_ID and not r.get("ladderBanned")]
    return sorted(others, key=lambda r: abs(r["rating"] - ours))[:k]


def qualification(bot_id: str, closest: list[dict], state: dict | None = None,
                  live: dict | None = None) -> tuple[int, bool]:
    """(how many of the closest opponents this build has faced, is that enough).

    Counts every match the build has played, not only the ones the farm fired:
    the flagship accumulates rated ladder games constantly, and identical code
    uploaded under two version numbers is one bot. Falls back to the farm's own
    log only when the feed has nothing for it.
    """
    faced_ids = set()
    version = (state or {}).get("uploads", {}).get(bot_id, {}).get("version")
    if live and version is not None:
        build = livefeed.build_for_version(live, version)
        if build is not None:
            faced_ids = livefeed.faced_team_ids(live, build)
    if not faced_ids:
        faced_ids = {t for t, n in per_bot_opponent_counts().get(bot_id, {}).items() if n > 0}
    seen = sum(1 for r in closest if r["teamId"] in faced_ids)
    return seen, seen >= QUALIFY_MIN


def per_bot_opponent_counts() -> dict[str, dict[str, int]]:
    """bot_id -> {opponent_team_id: series played}, from the harvested log."""
    counts: dict[str, dict[str, int]] = {}
    if not SERIES_CSV.exists():
        return counts
    for row in csv.DictReader(SERIES_CSV.open()):
        counts.setdefault(row["bot_id"], {})
        counts[row["bot_id"]][row["opponent_id"]] = (
            counts[row["bot_id"]].get(row["opponent_id"], 0) + 1
        )
    return counts


def queue_bot(state: dict, bot_id: str, rounds: int) -> None:
    """Force the next `rounds` rounds to test `bot_id`, ahead of UCB selection.

    For trying a specific build on demand -- something a collaborator handed us,
    or a bot the internal leaderboard has not nominated. Queued entries live in
    state.json, which is gitignored, so a deploy never clears them.
    """
    queue = state.setdefault("queue", [])
    for entry in queue:
        if entry["bot_id"] == bot_id:
            entry["rounds_left"] += rounds
            return
    queue.append({"bot_id": bot_id, "rounds_left": rounds,
                  "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})


def take_queued(state: dict) -> str | None:
    """Next queued bot, consuming one round of its allowance."""
    queue = state.get("queue") or []
    while queue:
        entry = queue[0]
        if entry["rounds_left"] <= 0:
            queue.pop(0)
            continue
        entry["rounds_left"] -= 1
        if entry["rounds_left"] <= 0:
            queue.pop(0)
        return entry["bot_id"]
    return None


def validated_opponents(chosen, ctx) -> list[dict]:
    """Enforce the policy contract before anything is fired at a real team.

    `policy.py` is meant to be edited by other people, so its output is treated
    as untrusted: drop anything that is not a real opponent row, deduplicate,
    never challenge ourselves, and cap at the rate limit. A policy returning too
    few simply fires fewer challenges -- better than a round that misfires.
    """
    seen: set[str] = set()
    clean: list[dict] = []
    known = {r["teamId"]: r for r in ctx.ladder}
    for row in chosen or []:
        if not isinstance(row, dict) or "teamId" not in row:
            log.error("policy returned a non-opponent %r, dropping", row)
            continue
        team_id = row["teamId"]
        if team_id == fc.TEAM_ID:
            log.error("policy returned our own team, dropping")
            continue
        if team_id in seen or team_id not in known:
            continue
        if known[team_id].get("ladderBanned"):
            log.error("policy returned ladder-banned %s, dropping", row.get("teamName"))
            continue
        seen.add(team_id)
        clean.append(known[team_id])
    if len(clean) != len(chosen or []):
        log.warning("policy returned %d opponents, %d usable", len(chosen or []), len(clean))
    return clean[: ctx.n]


# --------------------------------------------------------------------------
# collection
# --------------------------------------------------------------------------

def collect(state: dict) -> int:
    """Harvest finished series into the CSVs. Returns how many were collected."""
    still_pending, series_rows, game_rows = [], [], []
    for rec in state.get("pending", []):
        try:
            info = fc.match_info(rec["match_id"])
        except fc.FcodeError as exc:
            log.warning("match %s: %s", rec["match_id"][:8], exc)
            still_pending.append(rec)
            continue
        match = info["match"]
        if match["status"] != "complete":
            age = time.time() - rec.get("fired_ts", time.time())
            if age > 3600:
                log.error("match %s stuck in %s after an hour, dropping",
                          rec["match_id"][:8], match["status"])
            else:
                still_pending.append(rec)
            continue

        we_are_a = match["teamAId"] == fc.TEAM_ID
        our_score = match["scoreA"] if we_are_a else match["scoreB"]
        their_score = match["scoreB"] if we_are_a else match["scoreA"]
        our_side = "a" if we_are_a else "b"
        series_rows.append({
            "fired_at": rec["fired_at"],
            "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bot_id": rec["bot_id"],
            "bot_name": rec["bot_name"],
            "bot_commit": rec["bot_commit"],
            "version": rec["version"],
            "match_id": rec["match_id"],
            "opponent": rec["opponent"],
            "opponent_id": rec["opponent_id"],
            "opponent_rank": rec["opponent_rank"],
            "opponent_rating": rec["opponent_rating"],
            "opponent_version": match["teamBVersion"] if we_are_a else match["teamAVersion"],
            "our_score": our_score,
            "their_score": their_score,
            "our_side": our_side,
        })
        for game in info.get("games", []):
            game_rows.append({
                "match_id": rec["match_id"],
                "bot_id": rec["bot_id"],
                "opponent": rec["opponent"],
                "opponent_rating": rec["opponent_rating"],
                "game_number": game["gameNumber"],
                "map": game["mapName"],
                "map_seed": game["mapSeed"],
                "we_won": game["winnerSide"] == our_side,
                "win_condition": game["winCondition"],
                "turns": game["turnsPlayed"],
            })
        counts = state.setdefault("opponent_games", {})
        counts[rec["opponent_id"]] = counts.get(rec["opponent_id"], 0) + 1

    append_csv(SERIES_CSV, SERIES_FIELDS, series_rows)
    append_csv(GAMES_CSV, GAMES_FIELDS, game_rows)
    state["pending"] = still_pending
    if series_rows:
        log.info("collected %d series (%d games)", len(series_rows), len(game_rows))
    return len(series_rows)


# --------------------------------------------------------------------------
# flagship
# --------------------------------------------------------------------------

def restore_flagship(state: dict, attempts: int = 4) -> bool:
    target = state.get("flagship_version")
    if target is None:
        return True
    for attempt in range(attempts):
        try:
            fc.activate(target)
            if fc.active_version() == target:
                return True
        except fc.FcodeError as exc:
            log.warning("restore attempt %d failed: %s", attempt + 1, exc)
        time.sleep(2)
    log.error("COULD NOT RESTORE FLAGSHIP v%s -- a test bot may be live", target)
    return False


def missing_coverage(bot_id: str, pool: list[dict]) -> list[str]:
    """Pool teams this bot has never faced."""
    faced = per_bot_opponent_counts().get(bot_id, {})
    return [r["teamName"] for r in pool if faced.get(r["teamId"], 0) == 0]


def build_elo(state: dict, live: dict | None, bot_id: str):
    """(elo, half-width, games) for a bot, straight from the live feed."""
    version = state.get("uploads", {}).get(bot_id, {}).get("version")
    if not live or version is None:
        return None
    build = livefeed.build_for_version(live, version)
    if build is None:
        return None
    est = livefeed.elo_estimate(build)
    if est is None:
        return None
    return est[0], est[1], livefeed.games_played(build)


def best_challenger(state: dict, stats: dict[str, arms.ArmStats], team_rating: float,
                    closest: list[dict] | None, min_games: int = 25,
                    live: dict | None = None):
    """The qualified bot with the highest expected Elo, if it beats the incumbent.

    Estimates come from the live feed, which fits them over every match a build
    has played -- rated ladder games included -- rather than over the handful of
    series this farm happened to fire.

    Returns (bot_id, elo, half_width, incumbent_id, incumbent_elo); bot_id is
    None when no qualified bot has a higher expected Elo than the incumbent.
    """
    flagship = state.get("flagship_version")
    versions = {info["version"]: bot_id for bot_id, info in state.get("uploads", {}).items()}
    incumbent_id = versions.get(flagship)
    incumbent = build_elo(state, live, incumbent_id) if incumbent_id else None
    incumbent_elo = incumbent[0] if incumbent else team_rating

    best_id, best_est, best_half = None, -1e9, None
    for bot_id in state.get("uploads", {}):
        if bot_id == incumbent_id:
            continue
        rated = build_elo(state, live, bot_id)
        if rated is None:
            continue
        est, half, games = rated
        if games < min_games:
            continue
        if closest:
            seen, ok = qualification(bot_id, closest, state, live)
            if not ok:
                log.info("%s not qualified: faced %d/%d of the closest %d (need %d)",
                         bot_id, seen, len(closest), CLOSEST_K, QUALIFY_MIN)
                continue
        if est > best_est:
            best_id, best_est, best_half = bot_id, est, half

    if best_id is None or best_est <= incumbent_elo:
        return None, None, None, incumbent_id, incumbent_elo
    return best_id, best_est, best_half, incumbent_id, incumbent_elo


def maybe_promote(state: dict, stats: dict[str, arms.ArmStats], team_rating: float,
                  closest: list[dict] | None = None,
                  min_games: int = 25, dry_run: bool = False) -> None:
    """Make the highest expected-Elo bot the live one.

    Two guards:

    * the challenger must be **qualified**: it has faced at least `QUALIFY_MIN`
      of the `CLOSEST_K` opponents nearest us in rating. Opponents upgrade
      constantly and upgrades almost always make them stronger, so a bot scored
      on a lopsided slice of the field is being compared against a different --
      usually easier -- field than its rivals were. Facing most of our own
      neighbourhood is what makes two estimates commensurable.
    * it needs `min_games` games behind the estimate.

    Given those, the comparison is on expected Elo: highest estimate is live.
    """
    best_id, best_est, best_se, incumbent_id, incumbent_elo = best_challenger(
        state, stats, team_rating, closest, min_games, live=livefeed.load()
    )
    flagship = state.get("flagship_version")
    if best_id is None:
        return
    new_version = state["uploads"][best_id]["version"]
    log.warning("PROMOTING %s (v%s): elo %.0f +-%.0f beats incumbent %.0f",
                best_id, new_version, best_est, best_se, incumbent_elo)
    if dry_run:
        return
    state["flagship_version"] = new_version
    state.setdefault("promotions", []).append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bot_id": best_id,
        "version": new_version,
        "elo": round(best_est, 1),
        "se": round(best_se, 1),
        "incumbent_elo": round(incumbent_elo, 1),
        "previous_version": flagship,
    })
    restore_flagship(state)


# --------------------------------------------------------------------------
# a round
# --------------------------------------------------------------------------

def ensure_uploaded(state: dict, cand: dict, dry_run: bool) -> int | None:
    """Upload a candidate if we have not already, returning its submission version."""
    known = state.setdefault("uploads", {})
    if cand["bot_id"] in known:
        return known[cand["bot_id"]]["version"]
    export_dir = HERE / "exports" / cand["bot_id"].replace("/", "_").replace("@", "_")
    if arms.export_bot(cand["name"], cand["commit"], export_dir) is None:
        log.error("cannot export %s from git, skipping", cand["bot_id"])
        return None
    name = f"{cand['name']} {cand['commit']} (farm)"
    if dry_run:
        log.info("[dry-run] would upload %s", cand["bot_id"])
        return -1  # keeps the rest of the round exercisable without uploading
    version = fc.submit(export_dir, name)
    known[cand["bot_id"]] = {
        "version": version,
        "name": name,
        "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reasons": cand["reasons"],
        "run": cand["run"],
    }
    log.info("uploaded %s as v%d (%s)", cand["bot_id"], version, cand["reasons"])
    # submit auto-activates; put the flagship back immediately
    restore_flagship(state)
    return version


def run_round(dry_run: bool = False) -> None:
    state = load_state()

    if PAUSE_FILE.exists() and not dry_run:
        log.info("PAUSE file present, doing nothing")
        return

    collect(state)

    config = load_config()
    for spec in (config.get("test_next") or []) if not dry_run else []:
        # "name@commit" or "name@commit:rounds" -- pushed by whoever wants it tested
        bot, _, rounds = str(spec).partition(":")
        if bot not in [e["bot_id"] for e in state.get("queue", [])] and \
                bot not in (state.get("test_next_done") or []):
            queue_bot(state, bot, int(rounds or 1))
            state.setdefault("test_next_done", []).append(bot)
            log.info("queued %s from config.json", bot)

    allowed, why_not = firing_allowed(config)
    if not allowed and not dry_run:
        log.info("not firing: %s", why_not)
        save_state(state)
        return

    # Checked before anything that changes the active submission -- `fcode submit`
    # auto-activates, so an upload inside the pairing window is as dangerous as a
    # challenge. Collection above is read-only and safe either way.
    if not dry_run and in_pairing_window():
        log.warning("%ds into the cycle is inside the pairing window, skipping this round",
                    seconds_into_cycle())
        save_state(state)
        return

    if state.get("flagship_version") is None:
        state["flagship_version"] = fc.active_version()
        log.info("adopting currently active v%s as the flagship", state["flagship_version"])

    ladder_rows = fc.ladder(100)
    team_rating = next(
        (r["rating"] for r in ladder_rows if r["teamId"] == fc.TEAM_ID), 1800.0
    )

    candidates = arms.leaderboard_candidates()
    if not candidates:
        log.error("no candidates from the internal leaderboard, nothing to test")
        save_state(state)
        return

    stats = read_arm_stats()
    eligible: list[dict] = []
    for cand in candidates:
        version = ensure_uploaded(state, cand, dry_run)
        if version is not None:
            eligible.append(cand)
    if not eligible:
        log.error("no candidate could be uploaded")
        save_state(state)
        return

    by_id = {c["bot_id"]: c for c in eligible}
    for bot_id in by_id:
        stats.setdefault(bot_id, arms.ArmStats(bot_id))
    bot_id, why = arms.ucb_select(stats, list(by_id))

    queued = take_queued(state) if not dry_run else (state.get("queue") or [{}])[0].get("bot_id")
    if queued:
        name, _, commit = queued.partition("@")
        if queued not in state.get("uploads", {}):
            export_dir = HERE / "exports" / queued.replace("@", "_")
            if arms.export_bot(name, commit, export_dir) is None:
                log.error("queued %s cannot be exported from git, skipping it", queued)
                queued = None
            elif not dry_run:
                version = fc.submit(export_dir, f"{name} {commit} (queued)")
                state.setdefault("uploads", {})[queued] = {
                    "version": version,
                    "name": f"{name} {commit} (queued)",
                    "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "reasons": "queued by hand",
                    "run": "manual",
                }
                log.info("uploaded queued %s as v%d", queued, version)
                restore_flagship(state)
    if queued:
        bot_id = queued
        remaining = next((e["rounds_left"] for e in state.get("queue", [])
                          if e["bot_id"] == queued), 0)
        why = f"queued by hand ({remaining} further round(s) after this one)"

    # An unqualified flagship stays live -- it is still the best bot we can
    # defend -- but it becomes the bot under test, so it fills in the closest
    # opponents it has not faced. The exception is a qualified challenger that
    # already beats it, which the decision pass will have promoted; in that case
    # normal UCB selection stands.
    filling_coverage = False
    closest = closest_opponents(ladder_rows)
    incumbent_id = {info["version"]: b for b, info in state.get("uploads", {}).items()}.get(
        state.get("flagship_version"))
    feed = livefeed.load()
    if closest and incumbent_id:
        seen, ok = qualification(incumbent_id, closest, state, feed)
        challenger = best_challenger(state, stats, team_rating, closest, live=feed)[0]
        if not ok and challenger is None and not queued:
            filling_coverage = True
            if bot_id != incumbent_id:
                bot_id = incumbent_id
            why = (f"flagship unqualified ({seen}/{len(closest)} of the closest "
                   f"{CLOSEST_K}), filling its own coverage")

    cand = by_id.get(bot_id) or {
        "name": incumbent_id.split("@")[0] if incumbent_id else bot_id.split("@")[0],
        "commit": bot_id.split("@")[-1],
    }
    version = state.get("uploads", {}).get(bot_id, {}).get("version", -1)
    build = livefeed.build_for_version(feed, version) if feed else None
    faced_ids = livefeed.faced_team_ids(feed, build) if build else {
        t for t, n in per_bot_opponent_counts().get(bot_id, {}).items() if n > 0
    }
    ctx = policy.Context(
        ladder=ladder_rows,
        me=next((r for r in ladder_rows if r["teamId"] == fc.TEAM_ID), None),
        pool=sampling_pool(ladder_rows),
        closest=closest,
        n=CHALLENGES_PER_ROUND,
        bot_id=bot_id,
        faced_ids=faced_ids,
        series_by_team=per_bot_opponent_counts().get(bot_id, {}),
        global_by_team=state.get("opponent_games", {}),
        filling_coverage=filling_coverage,
        pairing_kernel={int(k): v for k, v in
                        ((feed or {}).get("model", {}).get("pairing_kernel", {}) or {}).items()},
    )
    opponents = validated_opponents(policy.choose_opponents(ctx), ctx)

    log.info("round %d: testing %s (v%d) -- %s", state.get("rounds", 0) + 1, bot_id, version, why)
    log.info("opponents: %s", ", ".join(f"{o['teamName']}(#{o['_rank']})" for o in opponents))

    if dry_run:
        log.info("[dry-run] would fire %d challenges", len(opponents))
        save_state(state)
        return

    if in_pairing_window():  # uploads may have taken us into it
        log.warning("%ds into the cycle is inside the pairing window, not firing",
                    seconds_into_cycle())
        save_state(state)
        return

    fired = 0
    try:
        fc.activate(version)
        for opp in opponents:
            try:
                match_id = fc.unrated(opp["teamId"])
            except fc.RateLimited:
                log.warning("rate limited after %d challenges (5/10min is shared with "
                            "hand-run tests and other agents)", fired)
                break
            except fc.FcodeError as exc:
                log.error("challenge vs %s failed: %s", opp["teamName"], exc)
                continue
            fired += 1
            state.setdefault("pending", []).append({
                "match_id": match_id,
                "fired_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "fired_ts": time.time(),
                "bot_id": bot_id,
                "bot_name": cand["name"],
                "bot_commit": cand["commit"],
                "version": version,
                "opponent": opp["teamName"],
                "opponent_id": opp["teamId"],
                "opponent_rank": opp["_rank"],
                "opponent_rating": round(opp["rating"], 1),
            })
    finally:
        if queued and fired == 0:
            # a round that fired nothing (rate limit, API trouble) must not spend
            # a hand-queued build's allowance
            queue_bot(state, queued, 1)
            log.info("refunded a queued round to %s: nothing was fired", queued)
        restored = restore_flagship(state)
        state["rounds"] = state.get("rounds", 0) + 1
        save_state(state)

    log.info("fired %d challenges with %s; flagship v%s %s",
             fired, bot_id, state["flagship_version"], "restored" if restored else "NOT RESTORED")


def run_decision(dry_run: bool = False) -> None:
    """Collect, re-estimate, and decide which bot should be live.

    Scheduled at :X2:30, thirteen seconds ahead of the ladder scheduler's pairing
    tick, so a promotion is already in place for the rated series that tick
    queues. Unlike a firing round this deliberately runs inside the pairing
    window, which is safe precisely because the only submission it can ever
    activate is a flagship -- the bot we want playing rated games anyway.
    """
    state = load_state()
    if PAUSE_FILE.exists() and not dry_run:
        log.info("PAUSE file present, no decision")
        return

    collect(state)
    save_state(state)

    if state.get("flagship_version") is None:
        state["flagship_version"] = fc.active_version()

    ladder_rows = fc.ladder(100)
    team_rating = next((r["rating"] for r in ladder_rows if r["teamId"] == fc.TEAM_ID), 1800.0)
    maybe_promote(state, read_arm_stats(), team_rating,
                  closest=closest_opponents(ladder_rows), dry_run=dry_run)

    # A hand-run test or another agent may have left something else active.
    if fc.active_version() != state["flagship_version"] and not dry_run:
        log.warning("active is v%s but flagship is v%s -- restoring",
                    fc.active_version(), state["flagship_version"])
        restore_flagship(state)
    save_state(state)


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def print_status() -> None:
    state = load_state()
    ladder_rows = fc.ladder(100)
    team_rating = next((r["rating"] for r in ladder_rows if r["teamId"] == fc.TEAM_ID), 1800.0)
    feed = livefeed.load()
    closest = closest_opponents(ladder_rows)

    stamp = feed.get("generated_at", "?") if feed else "FEED MISSING"
    print(f"flagship: v{state.get('flagship_version')}   rounds: {state.get('rounds', 0)}   "
          f"pending: {len(state.get('pending', []))}   team rating: {team_rating:.0f}")
    print(f"estimates from the live feed, generated {stamp}")
    print(f"\n{'bot':<34}{'ver':>5}{'games':>7}{'elo':>8}{'+-':>6}{'closest':>9}{'live?':>7}")
    for bot_id, info in sorted(state.get("uploads", {}).items()):
        seen, ok = qualification(bot_id, closest, state, feed)
        cover = f"{seen}/{len(closest)}"
        live_mark = "LIVE" if info["version"] == state.get("flagship_version") else (
            "ok" if ok else "-")
        rated = build_elo(state, feed, bot_id)
        if rated is None:
            build = livefeed.build_for_version(feed, info["version"]) if feed else None
            why = (build or {}).get("estimate_blocked") or "no feed entry"
            print(f"{bot_id:<34}{info['version']:>5}{livefeed.games_played(build or {}):>7}"
                  f"{why:>14}{cover:>9}{live_mark:>7}")
            continue
        est, half, games = rated
        print(f"{bot_id:<34}{info['version']:>5}{games:>7}{est:>8.0f}{half:>6.0f}"
              f"{cover:>9}{live_mark:>7}")

    queue = state.get("queue") or []
    if queue:
        print("\nqueued by hand (tested before UCB selection):")
        for entry in queue:
            print(f"  {entry['bot_id']:<34}{entry['rounds_left']} round(s) left")

    print(f"\n(qualified = faced {QUALIFY_MIN} of the {CLOSEST_K} opponents closest to us in "
          f"rating;\n among qualified bots the highest expected Elo goes live)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="fire one round of challenges")
    parser.add_argument("--decide", action="store_true",
                        help="collect, re-estimate and promote (runs at :X2:30)")
    parser.add_argument("--collect", action="store_true", help="only harvest finished matches")
    parser.add_argument("--status", action="store_true", help="show arms and estimates")
    parser.add_argument("--dry-run", action="store_true", help="decide but do not upload or fire")
    parser.add_argument("--offline", action="store_true",
                        help="decide against fixtures/ -- no credentials needed, implies --dry-run")
    parser.add_argument("--test-next", metavar="NAME@COMMIT",
                        help="queue a specific build to be tested ahead of UCB selection")
    parser.add_argument("--rounds", type=int, default=1,
                        help="how many rounds --test-next should get (5 matches each)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
    )

    if args.offline:
        args.dry_run = True
        go_offline()

    if args.test_next:
        state = load_state()
        queue_bot(state, args.test_next, args.rounds)
        save_state(state)
        print(f"queued {args.test_next} for {args.rounds} round(s) "
              f"({args.rounds * CHALLENGES_PER_ROUND} matches)")
        for entry in state.get("queue", []):
            print(f"  {entry['bot_id']:<34}{entry['rounds_left']} round(s) left")
    elif args.status:
        print_status()
    elif args.decide:
        run_decision(dry_run=args.dry_run)
    elif args.collect:
        state = load_state()
        collect(state)
        save_state(state)
    elif args.once:
        run_round(dry_run=args.dry_run)
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
