"""Can this bot's code be imported at all?

Staging copies exactly one bot directory, so a bot that reaches for a sibling module never gets
it. strategist_learned@2a19238 is the case that prompted this: its own docstring says it "reuses
bots/strategist's state/strategies/utils/features modules unchanged", but only main.py and
policy.py are in its tree, so every one of its 4,830 matches died on `No module named 'features'`.

That is not a bot that plays badly, it is a bot that cannot start, and nothing noticed. Compliance
probes measure turn time and so never run either. The run could never complete, and because the
automation evaluates one run at a time, three later bots deferred behind work that was guaranteed
to fail.

A verdict is final for the code it was made about. Identity is the code hash, so any fix is new
code with a new hash and gets judged fresh -- there is nothing to retry and nothing to reset.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

from tournament.duplicates import code_hash
from tournament.gitutil import REPO_ROOT

CACHE_PATH = REPO_ROOT / "tournament" / "unloadable.json"
TIMEOUT_SECONDS = 60

# Import the bot the way the engine does: its own directory first on sys.path, then `import main`.
# Module-level code runs, which is the point -- a bot that raises on import cannot play.
_PROBE = (
    "import sys; sys.path.insert(0, sys.argv[1]);"
    " import importlib; importlib.import_module('main')"
)


def _load_cache() -> dict[str, dict]:
    try:
        return json.loads(CACHE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: dict[str, dict]) -> None:
    try:
        CACHE_PATH.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")
    except OSError:
        pass


@lru_cache(maxsize=4096)
def _probe(commit: str, path: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="fcode-loadcheck-") as tmp:
        archive = subprocess.run(
            ["git", "archive", f"{commit}:{path}"], cwd=REPO_ROOT, capture_output=True
        )
        if archive.returncode != 0:
            return False, f"cannot read {path} at {commit[:7]}"
        target = Path(tmp)
        extract = subprocess.run(
            ["tar", "-x", "-C", str(target)], input=archive.stdout, capture_output=True
        )
        if extract.returncode != 0:
            return False, "staged tree could not be unpacked"
        if not (target / "main.py").exists():
            return False, "no main.py"
        try:
            result = subprocess.run(
                [sys.executable, "-c", _PROBE, str(target)],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                cwd=tmp,
            )
        except subprocess.TimeoutExpired:
            return False, f"import did not finish within {TIMEOUT_SECONDS}s"
    if result.returncode == 0:
        return True, ""
    lines = [line for line in (result.stderr or "").strip().splitlines() if line.strip()]
    return False, lines[-1] if lines else f"import failed with status {result.returncode}"


def verdict(commit: str, path: str, cache: dict[str, dict] | None = None) -> tuple[bool, str]:
    """(loads, reason). Cached on the code hash, so each implementation is judged once."""
    if not commit or not path:
        return True, ""  # Nothing to check; never block on missing metadata.
    digest = code_hash(commit, path)
    if not digest:
        return True, ""
    store = _load_cache() if cache is None else cache
    key = f"{path}@{digest}"
    if key in store:
        record = store[key]
        return bool(record.get("loads", True)), record.get("reason", "")
    loads, reason = _probe(commit, path)
    store[key] = {"loads": loads, "reason": reason}
    if cache is None:
        _save_cache(store)
    return loads, reason


def partition(specs: list) -> tuple[list, list[tuple[object, str]]]:
    """Split BotSpecs into those that import and those that cannot, with their reasons."""
    cache = _load_cache()
    before = len(cache)
    good, bad = [], []
    for spec in specs:
        loads, reason = verdict(spec.commit, spec.path, cache=cache)
        (good if loads else bad).append(spec if loads else (spec, reason))
    if len(cache) != before:
        _save_cache(cache)
    return good, bad


def unloadable_ids(bots: dict[str, dict]) -> set[str]:
    """bot_ids in `bots` ({bot_id: {"commit", "path"}}) whose code cannot be imported."""
    cache = _load_cache()
    before = len(cache)
    broken = {
        bot_id
        for bot_id, info in bots.items()
        if not verdict(info.get("commit", ""), info.get("path", ""), cache=cache)[0]
    }
    if len(cache) != before:
        _save_cache(cache)
    return broken
