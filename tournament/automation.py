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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tournament import duplicates, hpc, report
from tournament import plan as planning
from tournament.discover import DEFAULT_EXCLUDES, discover
from tournament.gitutil import REPO_ROOT, resolve_commit
from tournament.merge import merge, read
from tournament.rating import evaluate
from tournament.registry import BotSpec
from tournament import registry
from tournament.site_data import build as build_site_data


STATE_VERSION = 2


@dataclass(frozen=True)
class Source:
    """One watched branch and the subtree under it that holds that person's bots.

    Each contributor owns a directory, so a prefix keeps discovery from wandering into vendored
    copies of other people's work. Elias in particular keeps bots/rivals/ (Jon's and Luc's bots,
    verbatim) and bots/probes/ (single-mechanic instruments that resign or idle on purpose);
    neither is an entrant. Excludes are fnmatch patterns against the repo-relative bot directory.
    """

    branch: str
    prefix: str
    excludes: tuple[str, ...] = ()

    @property
    def ref(self) -> str:
        return f"origin/{self.branch}"

    @classmethod
    def parse(cls, text: str) -> "Source":
        """`branch:prefix[:exclude,exclude]`, e.g. `x/jon:bots/jon`."""
        parts = text.split(":")
        if len(parts) == 2:
            branch, prefix = parts
            excludes: tuple[str, ...] = ()
        elif len(parts) == 3:
            branch, prefix, raw = parts
            excludes = tuple(item for item in raw.split(",") if item)
        else:
            raise argparse.ArgumentTypeError(
                f"expected branch:prefix[:excludes], got {text!r}"
            )
        return cls(branch=branch, prefix=prefix, excludes=excludes)


# The active branches. A contributor who starts a new top-level directory needs a line here --
# discovery is deliberately opt-in per subtree rather than scanning all of bots/, because the
# repo also contains vendored rivals, probes and starter templates that must never be entered.
DEFAULT_SOURCES = (
    Source("x/jon", "bots/jon"),
    Source("x/luc", "bots/luc"),
    Source("elias_dev", "bots/elias"),
)
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


def _preferred(specs: list[BotSpec]) -> BotSpec:
    """Prefer a live bot path over archived/versioned aliases, then choose stably."""
    archive = {"versions", "archive", "legacy", "probes", "old"}

    def key(spec: BotSpec) -> tuple:
        parts = Path(spec.path).parts
        live = not bool(archive & set(parts))
        return (live, -len(parts), spec.name, spec.path)

    return max(specs, key=key)


def played_bot_ids() -> set[str]:
    """Every bot_id that has actually played a rating match, read from the match CSVs.

    This is the ground truth for "have we evaluated this?". Compliance probes are excluded --
    they measure turn time and never enter a win matrix, so a bot that has only been probed has
    not been rated.
    """
    found: set[str] = set()
    for path in sorted(planning.RUNS_ROOT.glob("*/matches.csv")):
        with open(path, newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("kind") == "compliance":
                    continue
                found.add(row["bot_a"])
                found.add(row["bot_b"])
    return found


def unfinished_runs() -> dict[str, set[str]]:
    """Runs whose schedule is not fully merged, mapped to the bot_ids they cover.

    A run that has been submitted but not merged is evidence of work in progress, and it is
    invisible to the ledger: results only reach matches.csv at merge time, so until then every
    bot in that run looks un-evaluated. Without this, an interrupted evaluation gets scheduled
    a second time while the first one is still on the cluster.

    Compliance probes are counted separately -- they land in compliance_matches.csv, so counting
    them against the rating schedule would mark every complete run as unfinished.
    """
    pending: dict[str, set[str]] = {}
    for schedule_path in sorted(planning.RUNS_ROOT.glob("*/schedule.jsonl")):
        run_dir = schedule_path.parent
        scheduled: set[str] = set()
        bots: set[str] = set()
        for line in schedule_path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("kind") == "compliance":
                continue
            scheduled.add(entry["match_id"])
            bots.add(entry["bot_a"])
            bots.add(entry["bot_b"])
        if not scheduled:
            continue
        merged: set[str] = set()
        matches = run_dir / "matches.csv"
        if matches.exists():
            with open(matches, newline="") as handle:
                for row in csv.DictReader(handle):
                    merged.add(row["match_id"])
        if scheduled - merged:
            pending[run_dir.name] = bots
    return pending


def pending_runs() -> dict[str, set[str]]:
    """Automation runs that have been submitted but not yet rated and published.

    Completion is defined by the published artefact, not by how many results have been merged.
    Merging is only one step: a run whose matches have all arrived but whose rating failed is
    still outstanding work, and keying this on merge progress made such a run invisible -- it
    dropped out of the queue the moment its last result landed, and was never revisited.
    """
    pending: dict[str, set[str]] = {}
    for marker in sorted(planning.RUNS_ROOT.glob("*/automation.json")):
        run_dir = marker.parent
        if (run_dir / "ratings-distinct.csv").exists():
            continue
        bots: set[str] = set()
        schedule = run_dir / "schedule.jsonl"
        if schedule.exists():
            for line in schedule.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get("kind") == "compliance":
                    continue
                bots.add(entry["bot_a"])
                bots.add(entry["bot_b"])
        pending[run_dir.name] = bots
    return pending


def derive_ledger() -> tuple[dict[str, dict], dict[str, BotSpec]]:
    """Rebuild "which implementations have been rated" from the match data itself.

    The alternative -- a hand-maintained tested_hashes file -- is a cache of exactly this, and a
    cache of the repo's own contents can only ever drift out of date. Deriving it means a run
    performed by hand, on the cluster, or by an older version of this script all count, and there
    is no bootstrap step to get wrong.

    Returns (hash -> {representative, aliases}, bot_id -> spec).

    Raises if a bot has played but its source is unresolvable: that would silently look like an
    un-evaluated implementation and get scheduled again, which is the failure this whole function
    exists to prevent.
    """
    specs = _all_specs()
    played = played_bot_ids()
    unresolved = sorted(bot_id for bot_id in played if bot_id not in specs)
    if unresolved:
        raise RuntimeError(
            f"{len(unresolved)} bot(s) have played but have no source metadata, so their code "
            f"cannot be hashed and they would be re-evaluated as if new: "
            f"{', '.join(unresolved[:5])}"
        )

    by_hash: dict[str, list[BotSpec]] = defaultdict(list)
    unhashable: list[str] = []
    for bot_id in sorted(played):
        spec = specs[bot_id]
        digest = duplicates.code_hash(spec.commit, spec.path)
        if digest:
            by_hash[digest].append(spec)
        else:
            unhashable.append(bot_id)
    if unhashable:
        raise RuntimeError(
            f"{len(unhashable)} rated bot(s) no longer resolve to a git object, so their code "
            f"cannot be compared against new pushes: {', '.join(unhashable[:5])}"
        )

    ledger: dict[str, dict] = {}
    for digest, group in by_hash.items():
        representative = _preferred(group).bot_id
        ledger[digest] = {
            "representative": representative,
            "aliases": sorted(spec.bot_id for spec in group if spec.bot_id != representative),
        }
    return ledger, specs


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
    sources: tuple[Source, ...],
    fetch_remote: str,
    site_repo: Path,
    publish: bool,
    fetch: bool,
    dry_run: bool,
) -> int:
    if fetch:
        print(f"fetching {fetch_remote}: {', '.join(source.branch for source in sources)}")
        _run(["git", "fetch", fetch_remote, *(source.branch for source in sources)])
    heads = {source.branch: resolve_commit(source.ref) for source in sources}
    # One identity for the combined state of every watched branch, so a push to any of them
    # produces a distinct run id.
    head = hashlib.sha256(
        "|".join(f"{branch}@{sha}" for branch, sha in sorted(heads.items())).encode()
    ).hexdigest()

    # The ledger is derived from the match CSVs on every tick, never cached. A stale cache was
    # holding 48 implementations while the repo's own results held 81.
    tested, all_specs = derive_ledger()
    print(f"ledger: {len(tested)} implementation(s) already rated (derived from match data)")

    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state.get("version") == 1:
            # v1 watched a single branch and stored one head. Everything else -- tested_hashes,
            # canonical_bots, canonical_run -- is content-addressed and carries over unchanged,
            # so migration only has to widen the head record.
            state["last_seen_refs"] = {}
            state["version"] = STATE_VERSION
            print("migrated automation state v1 -> v2 (single branch -> multi-branch)")
        if state.get("version") != STATE_VERSION:
            raise RuntimeError(f"unsupported automation state version: {state.get('version')}")
    else:
        if not canonical_run:
            raise RuntimeError("first run needs --canonical-run")
        state = {"version": STATE_VERSION, "canonical_run": canonical_run}
        _save_state(state_path, state)
        print(f"initialised automation state (canonical run: {canonical_run})")

    current: list[BotSpec] = []
    for source in sources:
        found = discover(
            heads[source.branch],
            source.prefix,
            excludes=DEFAULT_EXCLUDES + source.excludes,
        )
        print(f"  {source.branch}@{heads[source.branch][:7]}: {len(found)} bot(s) under {source.prefix}")
        current.extend(found)

    by_hash: dict[str, list[BotSpec]] = defaultdict(list)
    for spec in current:
        digest = duplicates.code_hash(spec.commit, spec.path)
        if digest:
            by_hash[digest].append(spec)
    # tested_hashes is shared across branches on purpose. Elias vendors Jon's bots under
    # bots/rivals/ and Luc's starter is a fork of the stock one; keying on .py content means an
    # implementation already rated from one branch is recorded as an alias, never re-scheduled.

    # Phase 1: make progress on work already submitted. Each visit either collects and publishes
    # a finished run or reports it as still going; nothing here blocks on the cluster.
    in_flight_bots = set()
    # Bots in a half-merged run of any kind are under test, automation-owned or not.
    for run_name, bots in sorted(unfinished_runs().items()):
        in_flight_bots |= bots
    pending = pending_runs()
    for run_name, bots in sorted(pending.items()):
        if dry_run:
            print(f"  run {run_name} is unfinished ({len(bots)} bot(s) under test)")
            in_flight_bots |= bots
            continue
        try:
            done = finalise(
                run_name, state=state, state_path=state_path,
                site_repo=site_repo, publish=publish,
            )
        except hpc.HpcError:
            raise
        if not done:
            in_flight_bots |= bots
    in_flight_hashes = {
        digest
        for digest, specs in by_hash.items()
        if any(spec.bot_id in in_flight_bots for spec in specs)
    }

    unseen = {
        digest: specs
        for digest, specs in by_hash.items()
        if digest not in tested and digest not in in_flight_hashes
    }
    # A pushed alias of already-rated code needs no bookkeeping: the next tick re-derives the
    # ledger from the match data and sees the same hash again.
    aliases = {
        spec.bot_id
        for digest, specs in by_hash.items()
        if digest in tested
        for spec in specs
        if spec.bot_id != tested[digest]["representative"]
    }
    if aliases:
        print(f"  {len(aliases)} pushed alias(es) of already-rated code, not scheduled")

    if not unseen:
        state["last_seen_ref"] = head
        state["last_seen_refs"] = heads
        state["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        _save_state(state_path, state)
        print(f"no unseen Python implementations in {len(current)} bot directories")
        return 0

    representatives = [_preferred(specs) for specs in unseen.values()]
    representatives.sort(key=lambda spec: spec.bot_id)
    print(f"{len(representatives)} unseen implementation(s) across {len(sources)} branch(es)")
    for spec in representatives:
        print(f"  {spec.bot_id:<30} {spec.path}")
    if dry_run:
        return 0

    settings = hpc.config()
    hpc.check_connection(settings["host"])
    # The same field finalise() will rate over, so the challenger cannot miss a survivor.
    canonical_specs, _ = canonical_field()
    # Keyed on the implementations under test and nothing else. An unrelated branch moving must
    # not change the tid: the run directory is where partial results live, and content-addressed
    # match ids mean re-submitting the same tid resumes rather than repeats. Keying this on the
    # branch heads stranded a half-finished run every time anyone else pushed.
    run_key = hashlib.sha256("|".join(sorted(unseen)).encode()).hexdigest()[:12]
    tid = f"auto-{run_key}"
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
        print("all scheduled results already exist")
    # Record what this run is for, so a later tick can finish it without re-deriving the
    # discovery that produced it. The run directory describes itself; nothing lives in memory
    # across ticks, because there is no process that spans them any more.
    _save_state(destination / "automation.json", {
        "challengers": sorted(spec.bot_id for spec in representatives),
        "heads": heads,
        "submitted_at": datetime.now(UTC).isoformat(timespec="seconds"),
    })
    state["last_seen_ref"] = head
    state["last_seen_refs"] = heads
    state["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    _save_state(state_path, state)
    print(f"submitted {tid}; a later tick will collect and publish it")
    return 0


def pooled_matches() -> list[dict]:
    """Every rating match in the repo, deduplicated by match_id.

    Ratings are only meaningful inside one win matrix, so the published ladder has to be built
    from all the evidence there is, not from one run plus one challenger set. match_id is
    content-addressed, so the same pairing recorded by two runs collapses to one row.
    """
    seen: set[str] = set()
    rows: list[dict] = []
    for path in sorted(planning.RUNS_ROOT.glob("*/matches.csv")):
        with open(path, newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("kind") == "compliance":
                    continue
                if row["match_id"] in seen:
                    continue
                seen.add(row["match_id"])
                rows.append(row)
    return rows


def canonical_field() -> tuple[list[BotSpec], list[tuple[str, str]]]:
    """The deduplicated set of bots a challenger must play, and the copies pruned away.

    Both callers must agree on this. A challenger is scheduled against these bots, and the
    published ladder is rated over these bots -- if the two disagree by even one entrant, the
    challenger never played somebody who ends up in the matrix, and the result is an unplayed
    pair imputed as a draw. Deriving both from this one function is what keeps that impossible.
    """
    _, all_specs = derive_ledger()
    rows = pooled_matches()
    played = {row["bot_a"] for row in rows} | {row["bot_b"] for row in rows}
    entrants = [spec for bot_id, spec in sorted(all_specs.items()) if bot_id in played]
    groups = duplicates.behaviour_groups(rows) + duplicates.code_groups(entrants)
    return duplicates.prune(entrants, groups)


def finalise(
    tid: str,
    *,
    state: dict,
    state_path: Path,
    site_repo: Path,
    publish: bool,
) -> bool:
    """Collect a submitted run, then rate and publish if the cluster has finished it.

    Returns True when the run is complete and has been published, False when it is still going.
    Splitting this out is what lets a tick stay short: submission and collection are separate
    visits, so the lock is never held across hours of cluster time.
    """
    destination = planning.run_dir(tid)
    marker = destination / "automation.json"
    if not marker.exists():
        print(f"  {tid}: not an automation run, leaving alone")
        return False
    info = json.loads(marker.read_text())

    settings = hpc.config()
    hpc.check_connection(settings["host"])
    hpc.fetch(tid, settings)
    _, merged = merge(destination)
    scheduled = planning.rating_match_count(destination)
    if merged < scheduled:
        print(f"  {tid}: {merged}/{scheduled} matches collected; still running")
        return False

    failures = [row for row in read(destination) if row.get("status") != "ok"]
    if failures:
        raise RuntimeError(
            f"{tid}: {len(failures)} rating match(es) failed; refusing to publish partial data"
        )

    # Rate the whole field, not this run against one older run. Behavioural duplicates are
    # collapsed to one representative each: keeping every copy would double-count whatever the
    # duplicated bot is good at (the paper's Example 1).
    rows = pooled_matches()
    kept, dropped = canonical_field()
    desired = {spec.bot_id for spec in kept}
    distinct_rows = [
        row for row in rows if row["bot_a"] in desired and row["bot_b"] in desired
    ]

    ratings = evaluate(distinct_rows)
    if not ratings.complete:
        # Unplayed pairs enter A as 0, which is indistinguishable from a measured draw. Publishing
        # that to a live ladder would present imputed numbers as results.
        pairs = "\n".join(f"      {a}  vs  {b}" for a, b in ratings.missing_pairs[:20])
        raise RuntimeError(
            f"{tid}: refusing to publish an incomplete matrix -- "
            f"{len(ratings.missing_pairs)} pair(s) have never played:\n{pairs}"
        )

    _write_csv(destination / "matches-distinct.csv", distinct_rows)
    metadata = {spec.bot_id: _spec_dict(spec) for spec in kept}
    report.write_csv(ratings, metadata, destination / "ratings-distinct.csv")
    report.write_csv(ratings, metadata, destination / "ratings.csv")
    duplicates.write_csv(duplicates.behaviour_groups(distinct_rows),
                         destination / "duplicates.csv")

    print(f"  {tid}: rated {len(desired)} distinct bot(s) over {len(distinct_rows)} matches")
    for bot_id, covered_by in sorted(dropped):
        print(f"    duplicate: {bot_id} -> {covered_by}")

    head = next(iter(info.get("heads", {}).values()), tid)
    if publish:
        _publish(destination, site_repo, head)
    state["canonical_run"] = tid
    state["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    _save_state(state_path, state)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--canonical-run", help="run id recorded as the starting point; the\n                        rated-implementation ledger is derived from match data regardless")
    parser.add_argument(
        "--source",
        type=Source.parse,
        action="append",
        dest="sources",
        metavar="BRANCH:PREFIX[:EXCLUDES]",
        help="watched branch and bot subtree; repeatable. Defaults to "
        + ", ".join(f"{s.branch}:{s.prefix}" for s in DEFAULT_SOURCES),
    )
    parser.add_argument("--fetch-remote", default="origin")
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
                sources=tuple(args.sources) if args.sources else DEFAULT_SOURCES,
                fetch_remote=args.fetch_remote,
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
