"""Deterministic arena harness for the Florent Code League 2026 (team AutistimusPrime).

This package is the team's arbiter. Every strategy decision should be settled by
`arena.score.compare`, never by eyeballing a single match.

Layout
------
    arena.worker   one-shot subprocess worker; runs matches in-process, emits JSONL
    arena.runner   fans workers out over physical cores, enforces timeouts, parses JSONL
    arena.score    antisymmetric mirrored scorer -- the headline `compare()` API
    arena.strict   pre-submission gate (static audit + crash sweep)
    arena.zoo      reference opponents + promotion gate

Engine facts this package is built on (docs/ground-truth.md):
  * the engine is deterministic; --seed only moves the coinflip tiebreak (G26)
  * Team A wins ~58-60% of identical-bot mirrors, so scoring MUST be mirrored (G27)
  * bot print() lands in the .replay26, engine tracebacks land on stdout/stderr (G29)
  * an uncaught exception permanently deletes the unit (G23)
  * a stray __pycache__ silently makes a bot inert (G30)
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache as _lru_cache
from pathlib import Path

__all__ = [
    "REPO_ROOT",
    "MAPS_DIR",
    "BOTS_DIR",
    "ZOO_DIR",
    "ARENA_DIR",
    "ALL_MAPS",
    "ALL_15",
    "engine_root",
    "resolve_bot",
    "resolve_map",
    "bot_name",
    "bot_dir",
    "physical_cores",
    "site_packages_dir",
]

ARENA_DIR = Path(__file__).resolve().parent
REPO_ROOT = ARENA_DIR.parent
MAPS_DIR = REPO_ROOT / "maps"
BOTS_DIR = REPO_ROOT / "bots"
ZOO_DIR = BOTS_DIR / "zoo"


def _discover_maps() -> tuple[str, ...]:
    if not MAPS_DIR.is_dir():
        return ()
    return tuple(sorted(p.stem for p in MAPS_DIR.glob("*.map26")))


#: Every shipped map, sorted. The competition ships 15.
ALL_MAPS: tuple[str, ...] = _discover_maps()

#: Alias used by score.compare's default argument, spelled the way the team talks.
ALL_15: tuple[str, ...] = ALL_MAPS


def engine_root() -> str:
    """The `engine_root` argument `run_game` wants: the directory holding fcode/."""
    import fcode

    return str(Path(fcode.__file__).resolve().parent)


def site_packages_dir() -> str | None:
    """Directory that must be on PYTHONPATH for a bot sub-interpreter to `import fcode`.

    The bot's sub-interpreter resolves imports from PYTHONPATH / site-packages, NOT
    from the parent process's runtime sys.path, so the runner has to pass this
    through the worker environment explicitly.
    """
    try:
        import fcode
    except ImportError:
        return None
    return str(Path(fcode.__file__).resolve().parent.parent)


def resolve_bot(spec: str | os.PathLike[str]) -> Path:
    """Resolve a bot spec to the absolute path of its main.py.

    Accepts an explicit main.py path, a directory holding main.py, or a bare name
    looked up under bots/ and bots/zoo/.
    """
    p = Path(spec)
    candidates: list[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.extend([Path.cwd() / p, REPO_ROOT / p, BOTS_DIR / p, ZOO_DIR / p])

    for c in candidates:
        if c.is_file() and c.suffix == ".py":
            return c.resolve()
        if c.is_dir():
            main_py = c / "main.py"
            if main_py.is_file():
                return main_py.resolve()
    raise FileNotFoundError(
        f"bot not found: {spec!r} (looked in {', '.join(str(c) for c in candidates)})"
    )


def resolve_map(spec: str | os.PathLike[str]) -> Path:
    """Resolve a map spec (bare stem, filename, or path) to an absolute .map26 path."""
    p = Path(spec)
    for c in (p, MAPS_DIR / p.name, MAPS_DIR / (p.name + ".map26"), Path(str(p) + ".map26")):
        if c.is_file():
            return c.resolve()
    raise FileNotFoundError(f"map not found: {spec!r}")


def bot_dir(main_py: str | os.PathLike[str]) -> Path:
    """The directory that is shipped for a bot, given its main.py."""
    return Path(main_py).resolve().parent


def bot_name(main_py: str | os.PathLike[str]) -> str:
    """Human-readable name of a bot: its directory name (or file stem)."""
    p = Path(main_py).resolve()
    return p.parent.name if p.name == "main.py" else p.stem


@_lru_cache(maxsize=1)
def physical_cores() -> int:
    """Best-effort physical (not logical) core count.

    Hyperthread siblings share an execution port, and run_game is a tight
    CPU-bound interpreter loop, so oversubscribing past physical cores buys
    almost nothing and costs scheduling jitter.
    """
    n = _physical_cores_platform()
    if n:
        return max(1, n)
    logical = os.cpu_count() or 2
    return max(1, logical // 2)


def _physical_cores_platform() -> int | None:
    if sys.platform == "win32":
        try:
            import subprocess

            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_Processor | "
                    "Measure-Object -Property NumberOfCores -Sum).Sum",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            return int(out.stdout.strip())
        except Exception:
            return None
    try:
        text = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    cores: set[tuple[str, str]] = set()
    phys = core = ""
    for line in text.splitlines():
        if line.startswith("physical id"):
            phys = line.split(":", 1)[1].strip()
        elif line.startswith("core id"):
            core = line.split(":", 1)[1].strip()
            cores.add((phys, core))
    return len(cores) or None
