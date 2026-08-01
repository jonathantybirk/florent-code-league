"""Thin git helpers. Bots are read out of history by commit, never checked out."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class GitError(RuntimeError):
    pass


def git(*args: str, cwd: Path | None = None) -> str:
    """Run a git command in the repo and return stdout, raising GitError on failure."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def resolve_commit(ref: str) -> str:
    """Resolve any ref (branch, tag, short sha) to a full commit sha."""
    return git("rev-parse", f"{ref}^{{commit}}").strip()


def list_files(ref: str, prefix: str = "") -> list[str]:
    """Repo-relative paths of every file under `prefix` at `ref`."""
    args = ["ls-tree", "-r", "--name-only", ref]
    if prefix:
        args += ["--", prefix]
    return [line for line in git(*args).splitlines() if line]


def path_exists(ref: str, path: str) -> bool:
    try:
        git("cat-file", "-e", f"{ref}:{path}")
        return True
    except GitError:
        return False


def extract(ref: str, path: str, dest: Path) -> None:
    """Extract the directory `path` at `ref` so its *contents* land directly in `dest`.

    `git archive <ref>:<path>` roots the archive at that subtree, which is what makes a bot
    directory extractable without its enclosing bots/<owner>/... prefix.
    """
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.Popen(
        ["git", "archive", f"{ref}:{path}"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    untar = subprocess.Popen(["tar", "-x", "-C", str(dest)], stdin=archive.stdout)
    assert archive.stdout is not None
    archive.stdout.close()
    untar.communicate()
    _, err = archive.communicate()
    if archive.returncode != 0 or untar.returncode != 0:
        raise GitError(f"extracting {ref}:{path} failed: {err.decode().strip()}")
