"""Poll a git ref, evaluate unseen bot implementations on DTU HPC, and publish the live ladder.

This is deliberately a one-shot command. A systemd user timer invokes it repeatedly; an advisory
lock makes overlapping timer events harmless, and content-addressed match IDs make interrupted
runs resumable.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from tournament import duplicates, hpc, report
from tournament import plan as planning
from tournament.discover import discover
from tournament.gitutil import REPO_ROOT, resolve_commit
from tournament.merge import merge, read
from tournament.rating import evaluate
from tournament.registry import BotSpec
from tournament import registry
from tournament.site_data import build as build_site_data


STATE_VERSION = 1
DEFAULT_STATE = REPO_ROOT / "tournament" / "automation-state.json"
DEFAULT_LOCK = REPO_ROOT / "tournament" / "automation.lock"
DEFAULT_SITE = REPO_ROOT.parent / "portfolio"


def _run(command: list[str], cwd: Path = REPO_ROOT) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}{result.stderr}"
        )
    return result.stdout


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))


def _distinct_matches(run_dir: Path) -> list[dict]:
    path = run_dir / "matches-distinct.csv"
    return _read_csv(path if path.exists() else run_dir / "matches.csv")


def _distinct_ratings(run_dir: Path) -> list[dict]:
    path = run_dir / "ratings-distinct.csv"
    return _read_csv(path if path.exists() else run_dir / "ratings.csv")


def _all_specs() -> dict[str, BotSpec]:
    found = {spec.bot_id: spec for spec in registry.load(validate=False)}
    for path in sorted(planning.RUNS_ROOT.glob("*/manifest.json")):
        try:
            bots = json.loads(path.read_text()).get("bots", [])
        except json.JSONDecodeError:
            continue
        for bot in bots:
            found[bot["bot_id"]] = BotSpec(
                bot["name"], bot["commit"], bot["path"], tuple(bot.get("tags", []))
            )
    return found


def _spec_dict(spec: BotSpec) -> dict:
    return {
        "name": spec.name,
        "commit": spec.commit,
        "path": spec.path,
        "tags": list(spec.tags),
        "bot_id": spec.bot_id,
    }


def _spec_from_dict(value: dict) -> BotSpec:
    return BotSpec(value["name"], value["commit"], value["path"], tuple(value.get("tags", [])))


def _preferred(specs: list[BotSpec]) -> BotSpec:
    """Prefer a live bot path over archived/versioned aliases, then choose stably."""
    archive = {"versions", "archive", "legacy", "probes", "old"}

    def key(spec: BotSpec) -> tuple:
        parts = Path(spec.path).parts
        live = not bool(archive & set(parts))
        return (live, -len(parts), spec.name, spec.path)

    return max(specs, key=key)


def bootstrap(canonical_run: str, ref: str) -> dict:
    run_dir = planning.run_dir(canonical_run)
    ratings = _distinct_ratings(run_dir)
    specs = _all_specs()
    canonical: dict[str, dict] = {}
    tested: dict[str, dict] = {}
    for row in ratings:
        bot_id = row["bot_id"]
        if bot_id not in specs:
            raise RuntimeError(f"cannot bootstrap: no source metadata for {bot_id}")
        spec = specs[bot_id]
        digest = duplicates.code_hash(spec.commit, spec.path)
        if not digest:
            raise RuntimeError(f"cannot hash {bot_id}")
        canonical[bot_id] = _spec_dict(spec)
        tested[digest] = {"representative": bot_id, "aliases": []}
    return {
        "version": STATE_VERSION,
        "canonical_run": canonical_run,
        "canonical_bots": canonical,
        "tested_hashes": tested,
        "last_seen_ref": resolve_commit(ref),
        "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"refusing to write empty CSV: {path}")
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def _publish(run_dir: Path, site_repo: Path, ref: str) -> None:
    output = site_repo / "public" / "botrankings" / "data"
    build_site_data(run_dir, output)
    _run(["npm", "run", "build"], site_repo)
    _run(["git", "add", "public/botrankings/data"], site_repo)
    changed = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=site_repo)
    if changed.returncode == 0:
        print("website data is unchanged")
        return
    _run(["git", "commit", "-m", f"Update bot rankings for {ref[:7]}"], site_repo)
    _run(["git", "push", "origin", "main"], site_repo)
    _run(["npm", "exec", "--yes", "wrangler@latest", "--", "deploy"], site_repo)
    print("published updated rankings to GitHub and Cloudflare")


def run_once(
    *,
    state_path: Path,
    canonical_run: str | None,
    ref: str,
    fetch_remote: str,
    fetch_branch: str,
    prefix: str,
    site_repo: Path,
    publish: bool,
    fetch: bool,
    dry_run: bool,
) -> int:
    if fetch:
        print(f"fetching {fetch_remote}/{fetch_branch}")
        _run(["git", "fetch", fetch_remote, fetch_branch])
    head = resolve_commit(ref)

    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state.get("version") != STATE_VERSION:
            raise RuntimeError(f"unsupported automation state version: {state.get('version')}")
    else:
        if not canonical_run:
            raise RuntimeError("first run needs --canonical-run")
        state = bootstrap(canonical_run, ref)
        _save_state(state_path, state)
        print(f"bootstrapped automation from {canonical_run}")

    current = discover(head, prefix)
    by_hash: dict[str, list[BotSpec]] = defaultdict(list)
    for spec in current:
        digest = duplicates.code_hash(spec.commit, spec.path)
        if digest:
            by_hash[digest].append(spec)

    tested = state["tested_hashes"]
    unseen = {digest: specs for digest, specs in by_hash.items() if digest not in tested}
    # A pushed alias of tested code is recorded, but never scheduled.
    for digest, specs in by_hash.items():
        if digest not in tested:
            continue
        aliases = set(tested[digest].get("aliases", []))
        aliases.update(spec.bot_id for spec in specs if spec.bot_id != tested[digest]["representative"])
        tested[digest]["aliases"] = sorted(aliases)

    if not unseen:
        state["last_seen_ref"] = head
        state["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        _save_state(state_path, state)
        print(f"{head[:7]}: no unseen Python implementations in {len(current)} bot directories")
        return 0

    representatives = [_preferred(specs) for specs in unseen.values()]
    representatives.sort(key=lambda spec: spec.bot_id)
    print(f"{head[:7]}: {len(representatives)} unseen implementation(s)")
    for spec in representatives:
        print(f"  {spec.bot_id:<30} {spec.path}")
    if dry_run:
        return 0

    settings = hpc.config()
    hpc.check_connection(settings["host"])
    canonical_specs = [_spec_from_dict(value) for value in state["canonical_bots"].values()]
    run_key = hashlib.sha256("|".join(sorted(unseen)).encode()).hexdigest()[:8]
    tid = f"auto-{head[:7]}-{run_key}"
    destination, schedule = planning.plan(
        tid,
        representatives,
        "official",
        (1,),
        0,
        versus=canonical_specs,
        compliance_specs=representatives,
    )
    print(f"planned {len(schedule)} matches in {tid}; submitting to DTU HPC")
    hpc.push(tid, settings)
    try:
        hpc.submit(tid, settings)
    except hpc.HpcError as error:
        if "nothing to submit" not in str(error):
            raise
        print("all scheduled results already exist; fetching them")
    hpc.watch(tid, settings)
    _, merged = merge(destination)
    if merged != len(schedule):
        raise RuntimeError(f"incomplete run: {merged}/{len(schedule)} results")
    challenger_rows = read(destination)
    failures = [row for row in challenger_rows if row.get("status") != "ok"]
    if failures:
        raise RuntimeError(f"{len(failures)} rating matches failed; not publishing partial data")

    canonical_dir = planning.run_dir(state["canonical_run"])
    canonical_rows = _distinct_matches(canonical_dir)
    combined = canonical_rows + challenger_rows
    behaviour = duplicates.behaviour_groups(combined)
    canonical_ids = set(state["canonical_bots"])
    new_ids = {spec.bot_id for spec in representatives}
    dropped: dict[str, str] = {}
    for group in behaviour:
        newcomers = [member for member in group.members if member in new_ids]
        incumbents = [member for member in group.members if member in canonical_ids]
        if not newcomers:
            continue
        if incumbents:
            keep = min(incumbents, key=lambda bot_id: int(next(r["rank"] for r in _distinct_ratings(canonical_dir) if r["bot_id"] == bot_id)))
            dropped.update({bot_id: keep for bot_id in newcomers})
        elif len(newcomers) > 1:
            specs = {spec.bot_id: spec for spec in representatives}
            keep = _preferred([specs[bot_id] for bot_id in newcomers]).bot_id
            dropped.update({bot_id: keep for bot_id in newcomers if bot_id != keep})

    kept = new_ids - set(dropped)
    desired = canonical_ids | kept
    distinct_rows = [
        row for row in combined if row["bot_a"] in desired and row["bot_b"] in desired
    ]
    map_count = len({row["map"] for row in distinct_rows})
    expected = len(desired) * (len(desired) - 1) // 2 * map_count * 2
    if len(distinct_rows) != expected:
        raise RuntimeError(
            f"distinct matrix incomplete after dedupe: {len(distinct_rows)}/{expected} matches"
        )
    _write_csv(destination / "matches-distinct.csv", distinct_rows)

    metadata = {bot_id: value for bot_id, value in state["canonical_bots"].items()}
    metadata.update({spec.bot_id: _spec_dict(spec) for spec in representatives})
    ratings = evaluate(distinct_rows)
    report.write_csv(ratings, metadata, destination / "ratings-distinct.csv")
    report.write_csv(ratings, metadata, destination / "ratings.csv")

    code_groups = []
    for digest, specs in unseen.items():
        if len(specs) > 1:
            code_groups.append(
                duplicates.Group(
                    "code",
                    tuple(sorted(spec.bot_id for spec in specs)),
                    f"identical .py content ({digest})",
                )
            )
    duplicates.write_csv(behaviour + code_groups, destination / "duplicates.csv")

    representative_by_id = {spec.bot_id: spec for spec in representatives}
    for bot_id in kept:
        state["canonical_bots"][bot_id] = _spec_dict(representative_by_id[bot_id])
    for digest, specs in unseen.items():
        played = _preferred(specs).bot_id
        representative = dropped.get(played, played)
        tested[digest] = {
            "representative": representative,
            "aliases": sorted(spec.bot_id for spec in specs if spec.bot_id != representative),
        }
    state["canonical_run"] = tid
    state["last_seen_ref"] = head
    state["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    print(f"canonical field: {len(desired)} bots; {len(dropped)} new duplicate(s) excluded")
    for bot_id, covered_by in sorted(dropped.items()):
        print(f"  {bot_id} -> {covered_by}")
    if publish:
        _publish(destination, site_repo, head)
    _save_state(state_path, state)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--canonical-run", help="initial duplicate-free run used to bootstrap")
    parser.add_argument("--ref", default="origin/x/jon")
    parser.add_argument("--fetch-remote", default="origin")
    parser.add_argument("--fetch-branch", default="x/jon")
    parser.add_argument("--prefix", default="bots/jon")
    parser.add_argument("--site-repo", type=Path, default=DEFAULT_SITE)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    DEFAULT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(DEFAULT_LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another evaluator is already running; exiting")
            return 0
        try:
            return run_once(
                state_path=args.state.resolve(),
                canonical_run=args.canonical_run,
                ref=args.ref,
                fetch_remote=args.fetch_remote,
                fetch_branch=args.fetch_branch,
                prefix=args.prefix,
                site_repo=args.site_repo.resolve(),
                publish=not args.no_publish,
                fetch=not args.no_fetch,
                dry_run=args.dry_run,
            )
        except hpc.HpcError as error:
            print(
                "DTU HPC is unavailable. Log in again, then let the next timer invocation "
                "resume the run:\n\n"
                "    SSH_ASKPASS_REQUIRE=never ssh dtu true\n\n"
                f"{error}",
                file=sys.stderr,
            )
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
