"""Read the live feed that `tournament.live_feed` publishes.

The farm must not judge bots on its own challenges alone. The feed already tracks
every match a build has played -- rated ladder games included, and grouped by
code hash so two version numbers holding identical code count as one bot -- and
fits an Elo with confidence bounds over all of it. A build that has been live for
an hour has ~140 games in the feed against the ~25 the farm fired itself.
"""

from __future__ import annotations

import json
from pathlib import Path

LIVE_JSON = Path("/home/Ucals/projects/portfolio/public/botrankings/data/live.json")


def load() -> dict | None:
    try:
        return json.loads(LIVE_JSON.read_text())
    except (OSError, ValueError):
        return None


def build_for_version(live: dict, version: int) -> dict | None:
    """The feed entry covering a submission version (versions sharing code merge)."""
    for bot in live.get("bots", []):
        if version in (bot.get("versions") or []):
            return bot
    return None


def _name_to_team_id(live: dict) -> dict[str, str]:
    return {o["team"]: o["team_id"] for o in live.get("opponents", [])}


def faced_team_ids(live: dict, build: dict) -> set[str]:
    """Every team this build has played, by team id, across all its versions."""
    names = _name_to_team_id(live)
    return {
        names[m["opponent"]]
        for m in live.get("matchups", [])
        if m["key"] == build["key"] and m["opponent"] in names
    }


def elo_estimate(build: dict) -> tuple[float, float] | None:
    """(elo, half-width of the interval), or None while the feed withholds one."""
    est = build.get("estimate")
    if not est:
        return None
    lo, hi = est.get("elo_lo"), est.get("elo_hi")
    half = (hi - lo) / 2 if lo is not None and hi is not None else 0.0
    return est["elo"], half


def games_played(build: dict) -> int:
    return build.get("live_games") or 0
