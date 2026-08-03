"""When a bot's implementation was first published.

A bot_id is `name@<branch-tip-sha>`, so the pinned sha says when the *branch* moved, not when the
code was written: an untouched bot is re-minted under a new id every time anybody pushes to its
branch. Reading that sha as an age is therefore wrong, often by days.

The honest answer is the earliest commit at which this exact implementation existed. Identity is
duplicates.code_hash -- the .py content, ignoring file names, mtimes and everything non-Python --
so a bot that was merely re-tagged, moved, or shipped alongside a new BOT_VERSION.toml keeps the
age it was born with.

The search only walks commits that touched the bot's own directory, which is a handful each, but
it does read a git archive per candidate. Results are content-addressed, so they are cached on
disk and never recomputed: an implementation's first publication cannot change.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from tournament.duplicates import code_hash
from tournament.gitutil import REPO_ROOT

CACHE_PATH = REPO_ROOT / "tournament" / "first-published.json"


@lru_cache(maxsize=8192)
def _hash_at(commit: str, path: str) -> str:
    return code_hash(commit, path)


def _touching_commits(commit: str, path: str) -> list[tuple[str, str]]:
    """(sha, committer ISO date) for commits reachable from `commit` that touched `path`, oldest
    first. Walking from the bot's own commit rather than from HEAD matters: this checkout sits on
    the harness branch, where the bot branches' history is not reachable at all."""
    result = subprocess.run(
        ["git", "log", "--reverse", "--format=%H %cI", commit, "--", path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    found = []
    for line in result.stdout.splitlines():
        sha, _, date = line.partition(" ")
        if sha and date:
            found.append((sha, date))
    return found


def _load_cache() -> dict[str, dict]:
    try:
        return json.loads(CACHE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict[str, dict]) -> None:
    try:
        CACHE_PATH.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")
    except OSError:
        pass  # A cache that cannot be written is a slow build, not a broken one.


def first_published(commit: str, path: str, cache: dict[str, dict] | None = None) -> dict | None:
    """The earliest commit carrying this bot's exact Python, as {"commit", "date"}.

    Returns None when the bot cannot be read at `commit` -- a path that has since been deleted,
    or a commit this checkout does not have.
    """
    if not commit or not path:
        return None
    target = _hash_at(commit, path)
    if not target:
        return None
    key = f"{path}@{target}"
    store = _load_cache() if cache is None else cache
    if key in store:
        return store[key]

    answer = None
    for sha, date in _touching_commits(commit, path):
        if _hash_at(sha, path) == target:
            answer = {"commit": sha[:7], "date": date}
            break
    if answer is None:
        # The pinned commit itself always carries the code, even if the log walk came back empty
        # (a shallow clone, or a path that only ever existed in one commit).
        answer = {"commit": commit[:7], "date": _commit_date(commit)}
    store[key] = answer
    if cache is None:
        _save_cache(store)
    return answer


def _commit_date(commit: str) -> str:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%cI", commit],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def resolve(specs: dict[str, dict]) -> dict[str, dict]:
    """First-publication record for every bot_id in `specs` ({bot_id: {"commit", "path", ...}})."""
    cache = _load_cache()
    before = len(cache)
    ages: dict[str, dict] = {}
    for bot_id, info in specs.items():
        found = first_published(info.get("commit", ""), info.get("path", ""), cache=cache)
        if found:
            ages[bot_id] = found
    if len(cache) != before:
        _save_cache(cache)
    return ages


def _instant(date: str) -> datetime:
    """Absolute ordering for a git date.

    Committer dates carry the committer's own offset, and this repo really does mix them (+08:00
    and +02:00 both appear), so comparing the ISO strings lexically picks the wrong member of a
    group. An unparseable date sorts last rather than aborting the build.
    """
    try:
        return datetime.fromisoformat(date)
    except ValueError:
        return datetime.max.replace(tzinfo=UTC)


def apply_duplicate_groups(
    ages: dict[str, dict], groups: list[tuple[str, ...]]
) -> dict[str, dict]:
    """Give every member of a duplicate group the oldest age in that group.

    Behavioural duplicates are the reason this is not automatic. Byte-identical code already
    shares an age, because identity here *is* the code hash -- but two implementations judged the
    same player by their results can have different source, and pruning keeps only one of them.
    The survivor stands for the whole group, so it should carry the group's earliest date rather
    than its own.

    Groups are merged transitively before the minimum is taken. They are collected across every
    run that ever recorded them, and the same implementations get regrouped run after run under
    re-minted ids, so {a, b} from one run and {b, c} from another are one group of three. Taking
    each group's minimum independently would give c a date that a already disproved.

    A member that has no date is skipped, not fatal, but a member that is no longer in the rated
    field still counts: the original of a behavioural duplicate is usually the one that got
    pruned, and its date is exactly the one worth keeping.
    """
    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[left_root] = right_root

    for members in groups:
        for member in members[1:]:
            union(members[0], member)

    oldest_by_root: dict[str, dict] = {}
    for bot_id in parent:
        record = ages.get(bot_id)
        if not record or not record.get("date"):
            continue
        root = find(bot_id)
        current = oldest_by_root.get(root)
        if current is None or _instant(record["date"]) < _instant(current["date"]):
            oldest_by_root[root] = record

    resolved = dict(ages)
    for bot_id in list(resolved):
        if bot_id in parent:
            oldest = oldest_by_root.get(find(bot_id))
            if oldest:
                resolved[bot_id] = oldest
    return resolved
