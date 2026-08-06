"""Thin wrappers around the `fcode` CLI.

The CLI lives in the bot repo's uv environment, so every call runs with that
checkout as its working directory regardless of where the farm itself runs.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

BOT_REPO = Path("/home/Ucals/projects/florent-code-league-llm-rl")


class FcodeError(RuntimeError):
    pass


class RateLimited(FcodeError):
    pass


def _run(args: list[str], timeout: int = 120) -> str:
    proc = subprocess.run(
        ["uv", "run", "fcode", *args],
        cwd=BOT_REPO,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = proc.stdout
    if "Rate limit exceeded" in out or "Rate limit exceeded" in proc.stderr:
        raise RateLimited(out.strip() or proc.stderr.strip())
    if proc.returncode != 0:
        raise FcodeError(f"fcode {' '.join(args)} failed: {proc.stderr.strip()[:400]}")
    return out


def _run_json(args: list[str], timeout: int = 120):
    out = _run([*args, "--json"], timeout=timeout)
    # uv prints a VIRTUAL_ENV warning ahead of the payload
    start = min((i for i in (out.find("{"), out.find("[")) if i != -1), default=-1)
    if start == -1:
        raise FcodeError(f"no JSON in output of `fcode {' '.join(args)}`: {out[:200]}")
    return json.loads(out[start:])


def ladder(limit: int = 100) -> list[dict]:
    return _run_json(["ladder", "--limit", str(limit)])


def active_version() -> int:
    """Version number of the currently active submission."""
    out = _run(["status"])
    for line in out.splitlines():
        if "Active bot:" in line:
            return int(line.split("Active bot: v")[1].split()[0].strip())
    raise FcodeError("could not parse active submission from `fcode status`")


def activate(version: int) -> None:
    _run(["submission", "activate", str(version)])


def submit(path: Path, name: str) -> int:
    """Upload a bot directory. Auto-activates, so callers must restore afterwards."""
    out = _run(["submit", str(path), "-n", name], timeout=300)
    marker = "Submitted! Version "
    if marker not in out:
        raise FcodeError(f"unexpected submit output: {out[:300]}")
    return int(out.split(marker)[1].split()[0])


def unrated(opponent_team_id: str) -> str:
    """Challenge a team. Snapshots the active submission at request time."""
    return _run_json(["match", "unrated", opponent_team_id])["matchId"]


def match_info(match_id: str) -> dict:
    return _run_json(["match", "info", match_id])


def my_team_id() -> str:
    for row in ladder(200):
        if row["teamName"] == TEAM_NAME:
            return row["teamId"]
    raise FcodeError(f"team {TEAM_NAME!r} not on the ladder")


TEAM_NAME = "Powered by SmartFridge"
TEAM_ID = "7fd91e77-812c-44da-bce7-457be94d2548"
