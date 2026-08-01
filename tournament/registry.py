"""The bot registry: every entrant is pinned by name *and* commit.

A bot is not "vanguard" -- it is "vanguard as of 9713344". Ratings are meaningless if the code
behind a name drifts between runs, and on this repo bots genuinely are edited in place while
benchmarks run (x/jon:scratch/arena.py goes as far as MD5-ing bot sources to detect it). Pinning
to a commit makes that impossible by construction.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from tournament.gitutil import REPO_ROOT, path_exists, resolve_commit

REGISTRY_PATH = Path(__file__).resolve().parent / "bots.toml"


@dataclass(frozen=True)
class BotSpec:
    name: str
    commit: str  # full 40-char sha
    path: str  # repo-relative directory containing main.py
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def short(self) -> str:
        return self.commit[:7]

    @property
    def bot_id(self) -> str:
        """Stable key used in every CSV and every staged directory name."""
        return f"{self.name}@{self.short}"


class RegistryError(RuntimeError):
    pass


def load(path: Path | None = None, *, validate: bool = True) -> list[BotSpec]:
    """Read bots.toml, resolving each `commit` to a full sha."""
    path = path or REGISTRY_PATH
    if not path.exists():
        raise RegistryError(
            f"no registry at {path} -- run `python -m tournament discover` to create one"
        )
    with open(path, "rb") as handle:
        data = tomllib.load(handle)

    specs: list[BotSpec] = []
    for entry in data.get("bot", []):
        for key in ("name", "commit", "path"):
            if key not in entry:
                raise RegistryError(f"registry entry missing '{key}': {entry}")
        spec = BotSpec(
            name=entry["name"],
            commit=resolve_commit(entry["commit"]),
            path=entry["path"].rstrip("/"),
            tags=tuple(entry.get("tags", [])),
        )
        if validate and not path_exists(spec.commit, f"{spec.path}/main.py"):
            raise RegistryError(
                f"{spec.bot_id}: no {spec.path}/main.py at commit {spec.short}"
            )
        specs.append(spec)

    seen: dict[str, BotSpec] = {}
    for spec in specs:
        if spec.bot_id in seen:
            raise RegistryError(f"duplicate bot_id {spec.bot_id}")
        seen[spec.bot_id] = spec
    if not specs:
        raise RegistryError(f"registry {path} contains no bots")
    return specs


def select(specs: list[BotSpec], wanted: str | None) -> list[BotSpec]:
    """Filter a roster by a comma-separated list of bot_ids, names, or `tag:<tag>` terms."""
    if not wanted:
        return specs
    terms = [term.strip() for term in wanted.split(",") if term.strip()]
    chosen: list[BotSpec] = []
    for term in terms:
        if term.startswith("tag:"):
            tag = term[4:]
            matches = [spec for spec in specs if tag in spec.tags]
        else:
            matches = [spec for spec in specs if term in (spec.bot_id, spec.name)]
        if not matches:
            raise RegistryError(f"no bot in the registry matches {term!r}")
        for spec in matches:
            if spec not in chosen:
                chosen.append(spec)
    return chosen


def dump(specs: list[BotSpec], path: Path, *, header: str = "") -> None:
    """Write a registry file. Commits are written short for readability; they re-resolve on load."""
    lines: list[str] = []
    if header:
        lines.extend(f"# {line}" if line else "#" for line in header.splitlines())
        lines.append("")
    for spec in specs:
        rel = Path(spec.path)
        lines.append("[[bot]]")
        lines.append(f'name   = "{spec.name}"')
        lines.append(f'commit = "{spec.short}"')
        lines.append(f'path   = "{rel.as_posix()}"')
        if spec.tags:
            tags = ", ".join(f'"{tag}"' for tag in spec.tags)
            lines.append(f"tags   = [{tags}]")
        lines.append("")
    path.write_text("\n".join(lines))


def repo_relative(path: str) -> Path:
    return REPO_ROOT / path
