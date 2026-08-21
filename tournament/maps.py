"""Map-set selection.

The official pool and Jon's synthetic corpora are kept apart on disk -- official maps sit bare in
maps/, generated ones under maps/generated/{,representative/,stress/} -- so a map set is just a
choice of which of those trees to glob.

The held-out pool is the exception: it lives outside maps/ entirely, in tournament/custom_maps/,
because that directory is gitignored. Keeping it off the maps/ tree means neither `official` nor
`generated` can pick it up by accident, and a developer globbing maps/ never trips over it.

The *official* pools cannot be told apart by path, because they overlap: every replacement so far
has retained some of its predecessor's maps. So each era is written out by name below, a map may
belong to several, and combining pools always means the union -- never a partition. Globbing maps/
would silently merge the eras, which is exactly the mistake the named lists exist to prevent.

Each official pool is named for the date Florent released it, because that is the only property
that stays true: "current" and "new" both went stale within a fortnight, and a rating labelled
with a moving name cannot be read two months later. The pre-2026-08-06 pool keeps the name
`legacy` -- it predates our records and we do not know its release date, and inventing one to fit
the scheme would be a worse lie than an honest label.
"""

from __future__ import annotations

from pathlib import Path

from tournament.gitutil import REPO_ROOT

MAPS_ROOT = REPO_ROOT / "maps"
GENERATED_ROOT = MAPS_ROOT / "generated"
SECRET_ROOT = REPO_ROOT / "tournament" / "custom_maps"

# Labels for held-out maps carry this prefix so a map label alone is enough to tell the pools
# apart -- match CSVs and the website both classify on the label, never on a path.
SECRET_PREFIX = "secret/"

# The competition pool as served by `fcode maps list`, per era. `fcode maps sync` only ever serves
# the *current* pool, so a stale CURRENT_POOL is the one thing here that can go wrong silently:
# runs keep playing the old fifteen and the omission is invisible. Compare `fcode maps list`
# against POOL_20260821 whenever the pool is said to have changed, and add a new era rather than
# editing one -- an edited era retroactively redefines every rating published under it.
#
# Retired maps stay downloadable by name from /api/maps/download long after they leave the pool,
# which is how the 2026-08-13 era was reconstructed after nobody recorded it at the time.

# The pool every published rating before 2026-08-06 was computed over. Kept whole, including the
# maps later pools retained: these names define what the historical numbers mean, and dropping the
# overlap to make the pools disjoint would redefine them retroactively.
POOL_LEGACY = (
    "atoll", "aurora", "bridge", "crossfire", "duel", "fjord", "hive", "jackpot", "longship",
    "pinch", "quarry", "runestone", "showdown", "skerry", "sprint", "strait", "string",
    "sweden", "twins", "vase", "vault",
)

# Released 2026-08-06, retaining atoll, hive and jackpot from the legacy pool.
POOL_20260806 = (
    "antler", "archipelago", "atoll", "drumlin", "eider", "fjordgate", "heart", "hive",
    "jackpot", "lighthouse", "meander", "moonrise", "nordkap", "saga", "snowflake",
)

# Released 2026-08-13 between 06:53 and 07:13 UTC, retaining antler, archipelago, drumlin,
# fjordgate and nordkap. Reconstructed on 2026-08-21 from ladder match history -- nobody recorded
# this pool while it was live, so its membership is the saturated union of the maps actually drawn
# in ladder games during the era (80 sampled matches, 400 draws, 70 consecutive samples adding
# nothing), cross-checked by re-deriving POOL_20260806 the same way and getting it exactly.
POOL_20260813 = (
    "antler", "archipelago", "auroraveil", "drakkarfjord", "drumlin", "fjordgate", "frostgate",
    "glacierkeep", "icefloe", "midgard", "nordkap", "ragnarok", "royale", "valkyrie", "yulerune",
)

# Released 2026-08-21 between 07:33 and 08:13 UTC, retaining auroraveil, glacierkeep, icefloe,
# midgard and valkyrie. The live competition pool.
POOL_20260821 = (
    "auroraveil", "bifrost", "fimbulwinter", "glacierkeep", "helheim", "holmgang", "icefloe",
    "jotunheim", "longhouse", "midgard", "paths", "skald", "stavkirke", "valkyrie", "yggdrasil",
)

# Every official era, oldest first. Adding an era means appending to this map and nothing else.
OFFICIAL_POOLS: dict[str, tuple[str, ...]] = {
    "legacy": POOL_LEGACY,
    "official-20260806": POOL_20260806,
    "official-20260813": POOL_20260813,
    "official-20260821": POOL_20260821,
}

# The live pool. Everything that used to say "official" means this.
CURRENT_POOL = "official-20260821"

# Pool identifiers, in the order the website offers them.
POOLS = (*OFFICIAL_POOLS, "secret")

# Back-compatible aliases. Ratings published before 2026-08-21 were computed under the names
# `official` and `legacy`; `official` moved with the pool and so cannot be trusted to mean any
# particular set of maps, which is why it now resolves to the current era and nothing reads it
# except old command lines.
CURRENT_OFFICIAL = POOL_20260821
LEGACY_OFFICIAL = POOL_LEGACY

# The fast subset x/jon uses for iteration (scratch/gauntlet.py:SCREEN).
SCREEN = ("atoll", "aurora", "duel", "pinch", "quarry", "twins")


def _named(names: tuple[str, ...]) -> list[Path]:
    return [MAPS_ROOT / f"{name}.map26" for name in names]


def _union(*groups: list[Path]) -> list[Path]:
    """Deduplicated union, because consecutive official pools share maps."""
    seen: dict[Path, None] = {}
    for group in groups:
        for path in group:
            seen[path] = None
    return sorted(seen)


def _official() -> list[Path]:
    return _named(OFFICIAL_POOLS[CURRENT_POOL])


def _legacy() -> list[Path]:
    return _named(POOL_LEGACY)


def _all_official() -> list[Path]:
    return _union(*(_named(names) for names in OFFICIAL_POOLS.values()))


def _generated() -> list[Path]:
    return sorted(GENERATED_ROOT.rglob("*.map26"))


def _secret() -> list[Path]:
    return sorted(SECRET_ROOT.glob("*.map26"))


def is_secret(map_label: str) -> bool:
    """Whether a map label names a held-out map."""
    return map_label.startswith(SECRET_PREFIX)


def pools_of(map_label: str) -> tuple[str, ...]:
    """Which pools a map label belongs to -- more than one where the pools overlap."""
    if is_secret(map_label):
        return ("secret",)
    return tuple(pool for pool, names in OFFICIAL_POOLS.items() if map_label in names)


def pool_labels(pool: str) -> tuple[str, ...]:
    """The map labels a pool identifier covers."""
    if pool in OFFICIAL_POOLS:
        return OFFICIAL_POOLS[pool]
    if pool == "official":
        return OFFICIAL_POOLS[CURRENT_POOL]
    if pool == "secret":
        return tuple(label(path) for path in _secret())
    raise ValueError(f"unknown map pool {pool!r}")


def resolve(spec: str) -> list[Path]:
    """Return absolute map paths for a map-set name or an explicit comma-separated list."""
    if spec == "official":
        maps = _official()
    elif spec in OFFICIAL_POOLS:
        maps = _named(OFFICIAL_POOLS[spec])
    elif spec == "all_official":
        maps = _all_official()
    elif spec == "generated":
        maps = _generated()
    elif spec == "secret":
        maps = _secret()
    elif spec == "official_secret":
        maps = _official() + _secret()
    elif spec == "all_official_secret":
        maps = _all_official() + _secret()
    elif spec == "all":
        maps = _all_official() + _generated()
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
    """Find a map by bare name, by path relative to maps/, or by full path.

    A `secret/` prefix is required to reach a held-out map by name. Bare names never resolve into
    the held-out pool, so `--maps duel,geode` fails loudly rather than quietly mixing pools.
    """
    candidate = Path(name)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    stem = name[:-6] if name.endswith(".map26") else name
    if stem.startswith(SECRET_PREFIX):
        secret = SECRET_ROOT / f"{stem[len(SECRET_PREFIX):]}.map26"
        if secret.exists():
            return secret
        raise FileNotFoundError(f"no held-out map named {name!r} under {SECRET_ROOT}")
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
    """Human-readable map key: bare stem for official maps, subdir-qualified for the rest."""
    if path.is_relative_to(SECRET_ROOT):
        return f"{SECRET_PREFIX}{path.stem}"
    relative = path.relative_to(MAPS_ROOT)
    if relative.parent == Path("."):
        return relative.stem
    return str(relative.with_suffix("")).replace("\\", "/")


def stage_path(path: Path) -> Path:
    """Where a map file sits inside a run directory's maps/, relative to that maps/."""
    if path.is_relative_to(SECRET_ROOT):
        return Path("secret") / path.name
    return path.relative_to(MAPS_ROOT)
