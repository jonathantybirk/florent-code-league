"""Build a self-contained run directory: staged bots, maps, and the match schedule.

A run directory is the unit that gets rsynced to the cluster, so everything a match needs lives
inside it and every path in the schedule is relative to it. That way the exact same command works
locally and inside an LSF array job, with no notion of "the repo" on the far side.

    runs/<tid>/
      schedule.jsonl   one match per line, 1-indexed by `index`
      manifest.json    what was planned and from which commits
      stage/<bot_id>/  bot sources extracted with `git archive`
      maps/            only the maps this tournament uses
      results/         one <match_id>.json per finished match
      logs/            LSF stdout/stderr (remote only)
"""

from __future__ import annotations

import hashlib
import itertools
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from tournament.gitutil import REPO_ROOT
from tournament.maps import MAPS_ROOT, label, resolve
from tournament.registry import BotSpec

RUNS_ROOT = REPO_ROOT / "tournament" / "runs"


@dataclass(frozen=True)
class Match:
    index: int  # 1-based; this is the LSF array index
    match_id: str
    bot_a: str  # bot_id of the player passed first (engine team A)
    bot_b: str
    a_main: str  # path to main.py, relative to the run directory
    b_main: str
    map: str  # map label, e.g. "duel" or "generated/stress/stress-...-rot-10x8"
    map_path: str  # relative to the run directory
    seed: int
    tle: int
    kind: str = "rating"


def match_id(
    bot_a: str, bot_b: str, map_label: str, seed: int, tle: int, kind: str = "rating"
) -> str:
    """Content-addressed match identity, so re-planning is stable and merging is idempotent."""
    key = f"{bot_a}|{bot_b}|{map_label}|{seed}|{tle}"
    if kind != "rating":
        key += f"|{kind}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def run_dir(tid: str) -> Path:
    return RUNS_ROOT / tid


def stage_bots(specs: list[BotSpec], destination: Path) -> dict[str, str]:
    """Extract each bot at its pinned commit. Returns bot_id -> main.py path within `destination`.

    Re-extracts from scratch rather than trusting an existing directory: a stale stage that
    silently disagrees with the registry would corrupt an entire tournament's results.
    """
    from tournament.gitutil import extract

    mains: dict[str, str] = {}
    for spec in specs:
        target = destination / spec.bot_id
        if target.exists():
            shutil.rmtree(target)
        extract(spec.commit, spec.path, target)
        main = target / "main.py"
        if not main.exists():
            raise FileNotFoundError(f"{spec.bot_id}: staged tree has no main.py")
        mains[spec.bot_id] = str(main.relative_to(destination.parent))
    return mains


def stage_maps(map_paths: list[Path], destination: Path) -> dict[str, str]:
    """Copy the selected maps in, preserving the official/generated split. Returns label -> path."""
    staged: dict[str, str] = {}
    for path in map_paths:
        key = label(path)
        target = destination / path.relative_to(MAPS_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        staged[key] = str(target.relative_to(destination.parent))
    return staged


def pairings(
    specs: list[BotSpec], versus: list[BotSpec] | None = None
) -> list[tuple[BotSpec, BotSpec]]:
    """Which unordered pairs to play.

    Without `versus`: a full round robin among `specs`.

    With `versus` (challenger mode): every bot in `specs` plays every bot in `versus`, plus each
    other. This is how a new bot version is added to an existing tournament without re-running
    matches whose result cannot have changed -- the point of pinning entrants by commit.
    """
    if versus is None:
        return list(itertools.combinations(specs, 2))

    seen: set[frozenset[str]] = set()
    pairs: list[tuple[BotSpec, BotSpec]] = []
    for left, right in itertools.chain(
        ((a, b) for a in specs for b in versus),
        itertools.combinations(specs, 2),
    ):
        if left.bot_id == right.bot_id:
            continue  # a bot cannot play itself, and it is already in the roster
        key = frozenset((left.bot_id, right.bot_id))
        if key in seen:
            continue
        seen.add(key)
        pairs.append((left, right))
    return pairs


def build_schedule(
    specs: list[BotSpec],
    map_paths: list[Path],
    seeds: list[int],
    tle: int,
    mains: dict[str, str],
    staged_maps: dict[str, str],
    versus: list[BotSpec] | None = None,
) -> list[Match]:
    """Every selected pair plays every map in BOTH orders, at every seed.

    Playing both orders is what makes first-player advantage cancel in the aggregate win matrix;
    without it the matrix would not be antisymmetric for any reason connected to bot strength.
    """
    matches: list[Match] = []
    index = 0
    for left, right in pairings(specs, versus):
        for path in map_paths:
            key = label(path)
            for seed in seeds:
                for a, b in ((left, right), (right, left)):
                    index += 1
                    matches.append(
                        Match(
                            index=index,
                            match_id=match_id(a.bot_id, b.bot_id, key, seed, tle),
                            bot_a=a.bot_id,
                            bot_b=b.bot_id,
                            a_main=mains[a.bot_id],
                            b_main=mains[b.bot_id],
                            map=key,
                            map_path=staged_maps[key],
                            seed=seed,
                            tle=tle,
                        )
                    )
    return matches


def plan(
    tid: str,
    specs: list[BotSpec],
    map_spec: str = "official",
    seeds: tuple[int, ...] = (1,),
    tle: int = 0,
    versus: list[BotSpec] | None = None,
    compliance_specs: list[BotSpec] | None = None,
) -> tuple[Path, list[Match]]:
    """Materialise a complete run directory and return it with the schedule."""
    if versus is None and len(specs) < 2 and not compliance_specs:
        raise ValueError("a round-robin tournament needs at least two bots")
    if versus is not None and not versus:
        raise ValueError("--vs selected no bots")

    destination = run_dir(tid)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results").mkdir(exist_ok=True)
    (destination / "logs").mkdir(exist_ok=True)

    from tournament import compliance

    map_paths = resolve(map_spec) if specs else []
    compliance_specs = list(specs if compliance_specs is None else compliance_specs)
    compliance_map_paths = resolve(",".join(compliance.MAPS)) if compliance_specs else []
    everyone = list(specs)
    for spec in list(versus or []) + compliance_specs:
        if spec.bot_id not in {s.bot_id for s in everyone}:
            everyone.append(spec)

    mains = stage_bots(everyone, destination / "stage")
    all_map_paths = list(dict.fromkeys(map_paths + compliance_map_paths))
    staged_maps = stage_maps(all_map_paths, destination / "maps")
    matches = build_schedule(
        specs, map_paths, list(seeds), tle, mains, staged_maps, versus=versus
    )
    if compliance_specs:
        compliance_mains = compliance.stage(compliance_specs, destination, mains)
        for spec in compliance_specs:
            for path in compliance_map_paths:
                key = label(path)
                index = len(matches) + 1
                kind = f"compliance-v{compliance.VERSION}"
                matches.append(
                    Match(
                        index=index,
                        match_id=match_id(
                            spec.bot_id,
                            compliance.BASELINE_ID,
                            key,
                            1,
                            compliance.GUARD_TLE_MS,
                            kind=kind,
                        ),
                        bot_a=spec.bot_id,
                        bot_b=compliance.BASELINE_ID,
                        a_main=compliance_mains[spec.bot_id],
                        b_main=compliance_mains[compliance.BASELINE_ID],
                        map=key,
                        map_path=staged_maps[key],
                        seed=1,
                        tle=compliance.GUARD_TLE_MS,
                        kind="compliance",
                    )
                )

    with open(destination / "schedule.jsonl", "w") as handle:
        for match in matches:
            handle.write(json.dumps(asdict(match)) + "\n")

    manifest = {
        "tournament_id": tid,
        "map_set": map_spec,
        "maps": sorted(staged_maps),
        "seeds": list(seeds),
        "tle": tle,
        "matches": len(matches),
        "rating_matches": sum(match.kind == "rating" for match in matches),
        "mode": "challenger" if versus else "round-robin",
        "challengers": [s.bot_id for s in specs] if versus else [],
        "bots": [
            {"bot_id": s.bot_id, "name": s.name, "commit": s.commit, "path": s.path,
             "tags": list(s.tags)}
            for s in everyone
        ],
        "compliance": compliance.manifest_config(compliance_specs, compliance_map_paths),
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return destination, matches


def load_schedule(destination: Path) -> list[Match]:
    path = destination / "schedule.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"no schedule at {path} -- run `plan` first")
    with open(path) as handle:
        return [Match(**json.loads(line)) for line in handle if line.strip()]


def load_manifest(destination: Path) -> dict:
    return json.loads((destination / "manifest.json").read_text())


def pending(destination: Path, matches: list[Match]) -> list[Match]:
    """Matches with no result file yet -- the basis for resuming a partial tournament."""
    results = destination / "results"
    return [m for m in matches if not (results / f"{m.match_id}.json").exists()]
