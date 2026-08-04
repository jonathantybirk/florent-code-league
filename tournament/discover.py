"""Scan a git ref for bot directories and emit registry entries.

Bots live on branches that are never checked out here (x/jon, x/luc, viktor, x/llm-RL), so
discovery reads the tree directly. A directory is a bot if it contains main.py.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from tournament.gitutil import list_files, resolve_commit
from tournament.registry import BotSpec

# Diagnostic instruments, not players. These are single-purpose probes that measure one mechanic
# (x/jon:llm-slop-analysis/jon/probes/README.md) -- several deliberately resign or do nothing, so
# including them would pollute the win matrix with agents nobody intended to rank.
DEFAULT_EXCLUDES = (
    "*/probes/probe_*",
    "*/legacy/probe_*",
    "*/probes/econ_lab",
    "*/probes/exec_plan",
    "*/probes/probe_*",
    # Leaderboard-v2 prune (2026-08-04): these bots were retired from the roster and their v1
    # match data archived under tournament/runs-v1/, so their hashes are no longer in the rated
    # ledger. They still exist on their branches; without these lines discovery would treat every
    # one of them as a brand-new implementation and re-evaluate it. Kept here rather than only in
    # automation.DEFAULT_SOURCES because the installed systemd unit passes --source flags that
    # replace the source list wholesale -- these excludes apply no matter what the unit says.
    "bots/jon/legacy",
    "bots/jon/legacy/*",
    "bots/jon/archive/attack_wave_v1",
    "bots/jon/archive/frontier_v1",
    "bots/jon/archive/frontier_v2",
    "bots/jon/archive/siege_v1",
    "bots/jon/archive/siege_v2",
    "bots/jon/archive/titanium_v1",
    "bots/jon/fair/casemate",
    "bots/green",
    "bots/green/*",
    "bots/hardshell",
    "bots/hardshell/*",
)


def find_bots(ref: str, prefix: str = "bots") -> list[str]:
    """Repo-relative paths of every directory under `prefix` at `ref` holding a main.py."""
    paths = []
    for file in list_files(ref, prefix):
        if Path(file).name == "main.py":
            paths.append(str(Path(file).parent))
    return sorted(set(paths))


def excluded(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def discover(
    ref: str,
    prefix: str = "bots",
    excludes: tuple[str, ...] = DEFAULT_EXCLUDES,
    name_depth: int = 1,
) -> list[BotSpec]:
    """Build BotSpecs for every bot under `prefix` at `ref`.

    `name_depth` controls how many trailing path components form the name: 1 gives "vanguard",
    2 gives "fair-vanguard". Names must be unique within a registry, so bump it if two owners
    have a bot with the same leaf name.
    """
    commit = resolve_commit(ref)
    specs: list[BotSpec] = []
    for path in find_bots(commit, prefix):
        if excluded(path, excludes):
            continue
        parts = Path(path).parts
        name = "-".join(parts[-name_depth:])
        tags = tuple(parts[1:-1])  # drop the leading "bots" and the bot's own directory
        specs.append(BotSpec(name=name, commit=commit, path=path, tags=tags))

    by_name: dict[str, list[BotSpec]] = {}
    for spec in specs:
        by_name.setdefault(spec.name, []).append(spec)
    clashes = {name: found for name, found in by_name.items() if len(found) > 1}
    if clashes:
        detail = "; ".join(
            f"{name}: {', '.join(s.path for s in found)}" for name, found in clashes.items()
        )
        raise ValueError(
            f"ambiguous bot names at --name-depth {name_depth} ({detail}). "
            f"Re-run with --name-depth {name_depth + 1}."
        )
    return specs
