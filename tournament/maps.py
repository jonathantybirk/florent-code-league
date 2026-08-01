"""Map-set selection.

The official pool and Jon's synthetic corpora are kept apart on disk -- official maps sit bare in
maps/, generated ones under maps/generated/{,representative/,stress/} -- so a map set is just a
choice of which of those trees to glob.
"""

from __future__ import annotations

from pathlib import Path

from tournament.gitutil import REPO_ROOT

MAPS_ROOT = REPO_ROOT / "maps"
GENERATED_ROOT = MAPS_ROOT / "generated"

# The fast subset x/jon uses for iteration (scratch/gauntlet.py:SCREEN).
SCREEN = ("atoll", "aurora", "duel", "pinch", "quarry", "twins")


def _official() -> list[Path]:
    return sorted(MAPS_ROOT.glob("*.map26"))


def _generated() -> list[Path]:
    return sorted(GENERATED_ROOT.rglob("*.map26"))


def resolve(spec: str) -> list[Path]:
    """Return absolute map paths for a map-set name or an explicit comma-separated list."""
    if spec == "official":
        maps = _official()
    elif spec == "generated":
        maps = _generated()
    elif spec == "all":
        maps = _official() + _generated()
    elif spec == "screen":
        maps = [MAPS_ROOT / f"{name}.map26" for name in SCREEN]
    else:
        maps = []
        for name in (part.strip() for part in spec.split(",")):
            if not name:
                continue
            maps.append(_lookup(name))

    missing = [path for path in maps if not path.exists()]
    if missing:
        raise FileNotFoundError(f"map(s) not found: {', '.join(str(p) for p in missing)}")
    if not maps:
        raise ValueError(f"map set {spec!r} selected no maps")
    return maps


def _lookup(name: str) -> Path:
    """Find a map by bare name, by path relative to maps/, or by full path."""
    candidate = Path(name)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    stem = name[:-6] if name.endswith(".map26") else name
    direct = MAPS_ROOT / f"{stem}.map26"
    if direct.exists():
        return direct
    relative = MAPS_ROOT / f"{stem}.map26"
    if relative.exists():
        return relative
    found = [path for path in MAPS_ROOT.rglob("*.map26") if path.stem == Path(stem).name]
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        raise ValueError(f"map name {name!r} is ambiguous: {', '.join(str(p) for p in found)}")
    raise FileNotFoundError(f"no map named {name!r} under {MAPS_ROOT}")


def label(path: Path) -> str:
    """Human-readable map key: bare stem for official maps, subdir-qualified for generated ones."""
    relative = path.relative_to(MAPS_ROOT)
    if relative.parent == Path("."):
        return relative.stem
    return str(relative.with_suffix("")).replace("\\", "/")
