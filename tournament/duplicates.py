"""Detect bots that are the same player under two names.

This roster is full of them and it is not obvious from the source tree. Three pairs in the
original 34-bot field turned out to play identically, and after Jon's update four entries tied
exactly -- his vanguard commits had changed nothing observable.

Why the framework tracks this rather than leaving it to inspection:

* Duplicates break Elo and the transitive part of mElo. The paper's Example 1: adding one
  redundant copy of an agent moves Elo from (0,0,0) to (-63, 63, 0, 0), "falsely suggesting agent
  B is superior". Ratings silently double-count whatever the duplicate cluster is good at.
* Nash averaging is invariant to them (Theorem 1, P1) -- it splits the equilibrium mass across the
  copies. Seeing 0.5/0.5 in the Nash column is a *symptom* of a duplicate, so naming them turns a
  confusing output into an explanation.
* A duplicate usually means a real mistake: a "new version" that changed nothing, or an archived
  snapshot re-entered under a second name.

Two independent notions, because they disagree in practice:

* **code** -- identical .py content. Cheap, exact, but misses bots that differ only in a debug
  flag or a comment. Hash *only* the .py files: an added BOT_VERSION.toml once made all 34 bots
  look changed.
* **behaviour** -- identical match results against every shared opponent. This is the one that
  matters for ratings, and it catches pairs the code hash does not.
"""

from __future__ import annotations

import csv
import hashlib
import io
import subprocess
import tarfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from tournament.gitutil import REPO_ROOT
from tournament.outcome import score_a as evaluation_score_a
from tournament.registry import BotSpec

# A pair needs to have met this many shared opponents before "identical results" means anything.
MIN_SHARED_OPPONENTS = 3

# Directories this repo uses for work kept for reference rather than actively developed. A bot
# under one of these is a worse name to carry into a report than its live twin.
ARCHIVE_DIRS = frozenset({"versions", "archive", "legacy", "probes", "old"})


@dataclass(frozen=True)
class Group:
    kind: str  # "code" or "behaviour"
    members: tuple[str, ...]
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind}] {', '.join(self.members)} -- {self.detail}"


# --------------------------------------------------------------------------------------------
# Code-level
# --------------------------------------------------------------------------------------------


def code_hash(commit: str, path: str) -> str:
    """SHA of a bot's .py files at a commit, ignoring names, mtimes and non-Python files."""
    result = subprocess.run(
        ["git", "archive", f"{commit}:{path}"], cwd=REPO_ROOT, capture_output=True
    )
    if result.returncode != 0:
        return ""
    digest = hashlib.sha256()
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        for member in sorted(archive.getmembers(), key=lambda m: m.name):
            if member.isfile() and member.name.endswith(".py"):
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                digest.update(member.name.encode())
                digest.update(handle.read())
    return digest.hexdigest()[:12]


def code_groups(specs: list[BotSpec]) -> list[Group]:
    """Bots whose Python is byte-identical."""
    by_hash: dict[str, list[str]] = defaultdict(list)
    for spec in specs:
        digest = code_hash(spec.commit, spec.path)
        if digest:
            by_hash[digest].append(spec.bot_id)
    return [
        Group("code", tuple(sorted(members)), f"identical .py content ({digest})")
        for digest, members in sorted(by_hash.items())
        if len(members) > 1
    ]


# --------------------------------------------------------------------------------------------
# Behavioural
# --------------------------------------------------------------------------------------------


def score_table(rows: list[dict]) -> tuple[list[str], dict[tuple[str, str], tuple[float, int]]]:
    """(bots, {(i, j): (points i scored vs j, games played)}), both orders folded together."""
    table: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0])
    for row in rows:
        if row.get("status") != "ok" or not row.get("winner"):
            continue
        a, b, score = row["bot_a"], row["bot_b"], evaluation_score_a(row)
        table[(a, b)][0] += score
        table[(a, b)][1] += 1
        table[(b, a)][0] += 1.0 - score
        table[(b, a)][1] += 1
    bots = sorted({key[0] for key in table})
    return bots, {key: (value[0], int(value[1])) for key, value in table.items()}


def behaviour_groups(rows: list[dict], tolerance: float = 0.0) -> list[Group]:
    """Bots with the same results against every shared opponent.

    `tolerance` is the largest win-rate difference still counted as identical, so 0.0 finds exact
    twins and e.g. 0.05 finds "seem to be identical".

    Two conditions, both necessary:

    1. the same results against every shared opponent, and
    2. an even head-to-head against each other.

    (2) is not decoration. The pair's own result has to be excluded from (1) -- identical bots beat
    each other exactly half the time, so including it would prevent any match -- but excluding it
    alone would also flag two bots that differ *only* in that one of them beats the other, which
    are plainly not redundant. It matches the paper's Definition 3, where the appended duplicate
    column is the original's and the diagonal entry is 0: a true duplicate ties with its original.
    Two identical deterministic bots here split 21/42, each winning every map as player A.
    """
    bots, table = score_table(rows)
    equivalent: dict[str, set[str]] = defaultdict(set)

    for i, left in enumerate(bots):
        for right in bots[i + 1 :]:
            shared = [
                other
                for other in bots
                if other not in (left, right)
                and table.get((left, other), (0, 0))[1] > 0
                and table.get((right, other), (0, 0))[1] > 0
            ]
            if len(shared) < MIN_SHARED_OPPONENTS:
                continue
            head_points, head_games = table.get((left, right), (0.0, 0))
            if head_games and abs(head_points / head_games - 0.5) > tolerance:
                continue
            worst = 0.0
            for other in shared:
                lw, ln = table[(left, other)]
                rw, rn = table[(right, other)]
                worst = max(worst, abs(lw / ln - rw / rn))
            if worst <= tolerance:
                equivalent[left].add(right)
                equivalent[right].add(left)

    groups: list[Group] = []
    for members in _components(bots, equivalent):
        first, second = members[0], members[1]
        points, games = table.get((first, second), (0.0, 0))
        head = f"{points:.0f}/{games} head to head" if games else "never met"
        shared = sum(
            1
            for other in bots
            if other not in members and table.get((first, other), (0, 0))[1] > 0
        )
        detail = (
            f"same results vs all {shared} shared opponents"
            + (f" (within {tolerance:.2f})" if tolerance else "")
            + f"; {head}"
        )
        groups.append(Group("behaviour", tuple(members), detail))
    return groups


def _components(bots: list[str], adjacency: dict[str, set[str]]) -> list[list[str]]:
    """Connected components, so a three-way duplicate is reported once, not as three pairs."""
    seen: set[str] = set()
    found: list[list[str]] = []
    for bot in bots:
        if bot in seen or not adjacency.get(bot):
            continue
        stack, component = [bot], []
        seen.add(bot)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbour in adjacency.get(current, ()):
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        if len(component) > 1:
            found.append(sorted(component))
    return sorted(found)


# --------------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------------


def detect(
    rows: list[dict], specs: list[BotSpec] | None = None, tolerance: float = 0.0
) -> list[Group]:
    groups = behaviour_groups(rows, tolerance)
    if specs:
        groups += code_groups(specs)
    return groups


def representative(members: tuple[str, ...], specs: dict[str, BotSpec]) -> str:
    """Which member of a duplicate group to keep when pruning a roster.

    All members play identically, so this is purely about which name you would rather see in the
    results. In order: the newest commit (the version someone is actually working on), then a live
    path over an archived one, then the shallower path, then the name so the pick is stable across
    runs. Path depth alone cannot decide -- `bots/jon/fair/vanguard` and
    `bots/jon/versions/vanguard_1e88ae8` are the same depth -- hence ARCHIVE_DIRS.
    """
    def key(bot_id: str) -> tuple:
        spec = specs.get(bot_id)
        if spec is None:
            return ("", False, 0, bot_id)
        parts = Path(spec.path).parts
        live = not (ARCHIVE_DIRS & set(parts))
        return (spec.commit, live, -len(parts), bot_id)

    return max(members, key=key)


def prune(
    roster: list[BotSpec], groups: list[Group]
) -> tuple[list[BotSpec], list[tuple[str, str]]]:
    """Drop all but one member of each duplicate group.

    Playing a challenger against every copy of the same bot buys no information and costs a full
    map sweep per copy. Returns the pruned roster and the (dropped, kept) pairs, so the caller can
    say what it removed rather than silently shrinking the field.
    """
    specs = {spec.bot_id: spec for spec in roster}
    dropped: list[tuple[str, str]] = []
    remove: set[str] = set()
    for group in groups:
        present = tuple(m for m in group.members if m in specs)
        if len(present) < 2:
            continue
        keep = representative(present, specs)
        for member in present:
            if member != keep and member not in remove:
                remove.add(member)
                dropped.append((member, keep))
    return [spec for spec in roster if spec.bot_id not in remove], dropped


def write_csv(groups: list[Group], path: Path) -> None:
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["kind", "size", "members", "detail"])
        for group in groups:
            writer.writerow([group.kind, len(group.members), " ".join(group.members), group.detail])


def render(groups: list[Group]) -> str:
    if not groups:
        return "no duplicate bots detected"
    behaviour = [g for g in groups if g.kind == "behaviour"]
    code = [g for g in groups if g.kind == "code"]
    lines: list[str] = []
    if behaviour:
        lines.append(f"{len(behaviour)} group(s) of bots that PLAY identically:")
        for group in behaviour:
            lines.append(f"  {', '.join(group.members)}")
            lines.append(f"    {group.detail}")
    if code:
        lines.append(f"{len(code)} group(s) with byte-identical Python:")
        for group in code:
            lines.append(f"  {', '.join(group.members)}  ({group.detail})")
    lines.append(
        "Duplicates inflate Elo and the transitive part of mElo (the paper's Example 1); "
        "Nash averaging splits its equilibrium mass across them instead."
    )
    return "\n".join(lines)
