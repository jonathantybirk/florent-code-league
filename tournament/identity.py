"""Work out which bot each platform submission actually is.

A submission version is a *slot*, not a bot. The same code gets uploaded twice under different
labels (v26 and v27 are byte-identical), and one bot's results end up split across slots for no
reason other than somebody pressing upload again. Treating versions as bots therefore both
double-counts the roster and shreds the sample size of the thing you actually want to measure.

The submission archives carry a `BOT_VERSION.toml` naming a `source_path` and `source_commit`,
and it is **not trustworthy**: v10, v11 and v13 all claim `warden_walk@f3c1fd7` while having three
different code hashes, and only 7 of 27 submissions agree with what the code actually is. The
packaging step evidently copies a stale file. So the toml is kept as a hint and never believed.

What is trustworthy is the code. Hashing a submission's `.py` files exactly the way
`duplicates.code_hash` hashes a git tree makes the two directly comparable, so a submission can be
matched against every bot directory that has ever existed on any branch. That recovers the real
`name@commit` for most of them -- including v16, our most-played submission, which was uploaded
with no name at all and turns out to be `steward@e55aab5`.

A submission that matches nothing was uploaded from a working tree that was never committed. That
is a real answer, not a failure, and is reported as such.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tomllib
import urllib.request
import zipfile
from pathlib import Path

from tournament.duplicates import code_hash
from tournament.gitutil import REPO_ROOT

CACHE_PATH = REPO_ROOT / "tournament" / "live-identity.json"

# Bots live one or two directories deep depending on whose branch they are on.
BOT_GLOBS = ("bots/*/main.py", "bots/*/*/main.py")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout


def _load(path: Path) -> dict:
    if not path.exists():
        return {"code_index": {}, "hashed_pairs": [], "submissions": {}}
    try:
        state = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"code_index": {}, "hashed_pairs": [], "submissions": {}}
    state.setdefault("code_index", {})
    state.setdefault("hashed_pairs", [])
    state.setdefault("submissions", {})
    return state


def _save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, separators=(",", ":")))
    tmp.replace(path)


def _archive_hash(archive: zipfile.ZipFile) -> str:
    """Hash a submission's Python exactly as `duplicates.code_hash` hashes a git tree.

    Both walk the `.py` files in sorted name order and fold in the name then the bytes, and the
    submission zip is flat in the same way `git archive <commit>:<path>` is, so the two digests
    are comparable without any normalisation.
    """
    digest = hashlib.sha256()
    for name in sorted(n for n in archive.namelist() if n.endswith(".py")):
        digest.update(name.encode())
        digest.update(archive.read(name))
    return digest.hexdigest()[:12]


def refresh_code_index(state: dict) -> int:
    """Hash every (bot directory, commit) pair not already indexed. Returns how many were added.

    Keyed by code hash, keeping *every* (path, commit) that produced it rather than one winner.
    Identical trees genuinely appear under several names -- a bot gets copied to a new directory
    before being changed -- and which of those names is the right label depends on the submission,
    so the choice belongs at resolution time, not here. Incremental: the pairs already hashed are
    remembered, so the thousand-archive cold build happens once and later runs cost a `git log`
    per path.
    """
    paths: set[str] = set()
    for glob in BOT_GLOBS:
        for line in _git("log", "--all", "--format=", "--name-only", "--", glob).splitlines():
            line = line.strip()
            if line.endswith("/main.py"):
                paths.add(line[: -len("/main.py")])

    seen = set(tuple(pair) for pair in state["hashed_pairs"])
    index = state["code_index"]
    added = 0
    for path in sorted(paths):
        for line in _git("log", "--all", "--format=%H %cI", "--reverse", "--", path).splitlines():
            if not line.strip():
                continue
            commit, date = line.split()
            if (path, commit) in seen:
                continue
            seen.add((path, commit))
            added += 1
            digest = code_hash(commit, path)
            if not digest:
                continue
            index.setdefault(digest, []).append([path, commit, date])
    for digest, occurrences in index.items():
        occurrences.sort(key=lambda occurrence: occurrence[2])
    state["hashed_pairs"] = [list(pair) for pair in sorted(seen)]
    return added


def _fetch_submission_hash(api_get, submission: dict) -> dict:
    url = api_get("/api/submissions/download", {"submissionId": submission["id"]})["url"]
    with urllib.request.urlopen(url, timeout=60) as response:
        raw = response.read()
    archive = zipfile.ZipFile(io.BytesIO(raw))
    meta = None
    if "BOT_VERSION.toml" in archive.namelist():
        try:
            meta = tomllib.loads(archive.read("BOT_VERSION.toml").decode())
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            meta = None
    return {
        "version": submission["version"],
        "hash": _archive_hash(archive),
        "toml_path": (meta or {}).get("source_path"),
        "toml_commit": (meta or {}).get("source_commit"),
        "variant": (meta or {}).get("variant"),
    }


def resolve(api_get, submissions: list[dict], cache_path: Path = CACHE_PATH) -> dict[int, dict]:
    """Map submission version -> identity. Cached; only new submissions cost anything.

    Submissions are immutable once uploaded, so a resolved one never needs revisiting. The git
    index is only refreshed when something fails to resolve against it, which keeps the steady
    state -- no new uploads since the last run -- entirely free of git and network work.
    """
    state = _load(cache_path)
    known = state["submissions"]
    dirty = False

    for submission in submissions:
        key = submission["id"]
        if key in known:
            continue
        try:
            known[key] = _fetch_submission_hash(api_get, submission)
            dirty = True
        except Exception as error:  # a download failure must not take the whole feed down
            print(f"identity: could not read submission v{submission['version']}: {error}")

    unresolved = [
        entry for entry in known.values() if entry["hash"] not in state["code_index"]
    ]
    if unresolved:
        added = refresh_code_index(state)
        if added:
            dirty = True
            print(f"identity: indexed {added} new (bot, commit) pairs")

    if dirty:
        _save(cache_path, state)

    index = state["code_index"]
    uploaded_at = {s["version"]: s.get("uploadedAt") or "" for s in submissions}
    out: dict[int, dict] = {}
    for entry in known.values():
        version = entry["version"]
        occurrences = index.get(entry["hash"]) or []
        hit = _pick(occurrences, uploaded_at.get(version, ""))
        out[version] = {
            "code_hash": entry["hash"],
            "path": hit[0] if hit else None,
            "commit": hit[1] if hit else None,
            "canonical": f"{hit[0].split('/')[-1]}@{hit[1][:7]}" if hit else None,
            "committed_at": hit[2] if hit else None,
            "in_git": hit is not None,
            "variant": entry.get("variant"),
            # Identical code under other directory names. Worth surfacing rather than hiding: it
            # is the same duplicate detection the offline harness runs, applied to the ladder.
            "aliases": sorted(
                {
                    f"{path.split('/')[-1]}@{commit[:7]}"
                    for path, commit, _ in occurrences
                    if not hit or path != hit[0]
                }
            )[:6],
            # Kept only so a wrong claim is visible rather than silently discarded.
            "claimed": (
                f"{entry['toml_path'].split('/')[-1]}@{entry['toml_commit'][:7]}"
                if entry.get("toml_path") and entry.get("toml_commit")
                else None
            ),
        }
    return out


def _pick(occurrences: list[list[str]], uploaded_at: str) -> list[str] | None:
    """Choose which name for identical code best describes what was uploaded.

    Identical trees show up under several paths because a bot gets copied to a new directory
    before being modified, so "earliest wins" happily attributes a submission to a sibling the
    uploader never touched -- it labelled v21 `vidar_mender` when it was uploaded as `vidar`.
    The tree that was actually packaged is the newest one that existed by upload time, so prefer
    that, and fall back to the earliest only when the upload predates every commit (which means
    the code was uploaded before it was ever pushed).
    """
    if not occurrences:
        return None
    if uploaded_at:
        earlier = [entry for entry in occurrences if entry[2] <= uploaded_at]
        if earlier:
            return earlier[-1]
    return occurrences[0]
