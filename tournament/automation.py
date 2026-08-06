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
import re
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
from tournament import loadcheck
from tournament.maps import is_secret
from tournament.merge import merge, read
from tournament.rating import evaluate
from tournament.registry import BotSpec
from tournament import registry
from tournament.site_data import build as build_site_data


STATE_VERSION = 2

# What every automated run plays. Both official pools, so a new bot arrives with a record on the
# current competition maps *and* a record comparable to the 144 bots already rated on the old
# ones -- 33 maps rather than 15, at 57% more compute per challenger.
#
# Note what this does not do: it schedules the challenger against the field, so the field's own
# pairwise results on the twelve new maps still do not exist, and the new-official pool stays
# incomplete -- and therefore unpublished -- until somebody backfills the whole matrix over them.
# Dropping this back to "official" is the right move once that backfill has landed and the old
# pool has become a museum piece.
RUN_MAP_SPEC = "all_official"


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


# Fallback for hand-run invocations only. The installed systemd unit passes explicit --source
# flags that replace this list wholesale, so editing it does NOT change what the live ladder
# watches -- see "Where the CI actually runs" in tournament/README.md.
#
# A contributor who starts a new top-level directory needs a line here --
# discovery is deliberately opt-in per subtree rather than scanning all of bots/, because the
# repo also contains vendored rivals, probes and starter templates that must never be entered.
# The leaderboard-v2 prune (2026-08-04): bots retired from the roster still exist on their
# branches, and their v1 match data is archived outside tournament/runs/, so without these
# excludes discovery would see them as brand-new implementations and re-evaluate them.
PRUNED_V2_EXCLUDES = (
    "bots/jon/legacy",
    "bots/jon/legacy/*",
    "bots/jon/archive/attack_wave_v1",
    "bots/jon/archive/frontier_v1",
    "bots/jon/archive/frontier_v2",
    "bots/jon/archive/siege_v1",
    "bots/jon/archive/siege_v2",
    "bots/jon/archive/titanium_v1",
    "bots/jon/fair/casemate",
)
DEFAULT_SOURCES = (
    Source("x/jon", "bots/jon", excludes=PRUNED_V2_EXCLUDES),
    Source("x/luc", "bots/luc"),
    Source("elias_dev", "bots/elias"),
    # Viktor keeps his bots at the top level instead of a personal directory, so the prefix is all
    # of bots/ minus the scratch bots and the starter template that also lives on main. bots/test
    # is planned as a directory holding many scratch bots, so it needs the subtree glob as well as
    # its own path; named exactly so a real bot like bots/testudo still enters.
    Source(
        "viktor",
        "bots",
        excludes=(
            "bots/tester", "bots/test", "bots/test/*", "bots/starter",
            # leaderboard-v2 prune, same reason as PRUNED_V2_EXCLUDES above
            "bots/green", "bots/green/*", "bots/hardshell", "bots/hardshell/*",
        ),
    ),
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


# ---------------------------------------------------------------------------------------------
# ATTENTION, AGENTS RUNNING SWEEPS AND EXPERIMENTS IN tournament/runs/: ladder evidence is
# OPT-IN. A run's matches enter the public rankings pool only if the run directory carries an
# automation.json (written by the evaluator itself) or a LADDER marker file (a deliberate manual
# ladder run, e.g. the v2-full bootstrap or a gap-fill). Everything else -- your ablations,
# panels, head-to-heads -- is treated as a private experiment: every CLI command still works on
# it, but its matches never enter the published matrix and its bots do not count as rated.
#
# Why: the published matrix must be COMPLETE (an unplayed pair is indistinguishable from a
# measured draw), so on 2026-08-04 a handful of 9-12 bot vidar sweeps injected entrants that
# had never played the full field and blocked every ladder publish with "refusing to publish an
# incomplete matrix". Auto-gap-filling was rejected: it would multiply a cheap sweep into ~14x
# the matches and permanently grow the field every future challenger must play.
#
# So: to put a bot on the ladder, push it to your bot branch and let the evaluator schedule it
# against the full canonical field. To make a manual run count as ladder evidence, plan it with
# --ladder (or touch LADDER in its directory) -- and only do that for a complete round robin or
# a full-field challenger set. An EXPERIMENT marker documents intent and always wins over both.
# ---------------------------------------------------------------------------------------------
EXPERIMENT_MARKER = "EXPERIMENT"
LADDER_MARKER = "LADDER"


def _ladder_match_files() -> list[Path]:
    """Every matches.csv that counts as ladder evidence. See the opt-in note above."""
    files = []
    for path in sorted(planning.RUNS_ROOT.glob("*/matches.csv")):
        run = path.parent
        if (run / EXPERIMENT_MARKER).exists():
            continue
        if (run / "automation.json").exists() or (run / LADDER_MARKER).exists():
            files.append(path)
    return files


def played_bot_ids() -> set[str]:
    """Every bot_id that has actually played a rating match, read from the match CSVs.

    This is the ground truth for "have we evaluated this?". Compliance probes are excluded --
    they measure turn time and never enter a win matrix, so a bot that has only been probed has
    not been rated. Experiment-marked runs are excluded for the same reason on the other side:
    a bot that has only been swept in an experiment has not been rated either, and must still
    be scheduled against the full field if it lands on a bot branch.
    """
    found: set[str] = set()
    for path in _ladder_match_files():
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
        if not outstanding_matches(run_dir):
            continue
        bots: set[str] = set()
        for line in schedule_path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("kind") == "compliance":
                continue
            bots.add(entry["bot_a"])
            bots.add(entry["bot_b"])
        pending[run_dir.name] = bots
    return pending


def _unloadable_in(run_dir: Path) -> set[str]:
    """bot_ids in this run whose code cannot be imported, from its own manifest."""
    try:
        bots = json.loads((run_dir / "manifest.json").read_text()).get("bots", [])
    except (OSError, json.JSONDecodeError):
        return set()
    return loadcheck.unloadable_ids(
        {bot["bot_id"]: {"commit": bot.get("commit", ""), "path": bot.get("path", "")}
         for bot in bots}
    )


def _unplayable_scheduled(run_dir: Path) -> set[str]:
    """Rating match ids in this run that involve a bot which cannot be imported."""
    schedule_path = run_dir / "schedule.jsonl"
    broken = _unloadable_in(run_dir)
    if not broken or not schedule_path.exists():
        return set()
    found = set()
    for line in schedule_path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("kind") == "compliance":
            continue
        if entry["bot_a"] in broken or entry["bot_b"] in broken:
            found.add(entry["match_id"])
    return found


def outstanding_matches(run_dir: Path) -> set[str]:
    """Rating match ids this run scheduled but has not merged locally.

    Matches involving a bot that cannot be imported are not counted. They will never produce a
    result no matter how often they are re-run, so counting them leaves the run in flight forever
    and defers every later bot behind it -- which is exactly what one bot missing a sibling module
    did to the ladder.
    """
    schedule_path = run_dir / "schedule.jsonl"
    if not schedule_path.exists():
        return set()
    broken = _unloadable_in(run_dir)
    scheduled = set()
    for line in schedule_path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("kind") == "compliance":
            continue
        if broken and (entry["bot_a"] in broken or entry["bot_b"] in broken):
            continue
        scheduled.add(entry["match_id"])
    merged: set[str] = set()
    matches = run_dir / "matches.csv"
    if matches.exists():
        with open(matches, newline="") as handle:
            for row in csv.DictReader(handle):
                merged.add(row["match_id"])
    return scheduled - merged


MAX_RESUBMITS = 3


def _idle_arrays(bjobs: str) -> dict[str, bool]:
    """Map job id -> "this array has nothing left to run", parsed from a `bjobs -A` table.

    The table is one row per array:

        JOBID       ARRAY_SPEC  OWNER   NJOBS PEND DONE  RUN EXIT SSUSP USUSP PSUSP
        29034232    trn_auto  s234842       1    0    0    0    1     0     0     0

    An array with no PEND, no RUN and nothing suspended has finished every element it will ever
    finish, whatever the DONE/EXIT split says. Counting only DONE would be wrong in the other
    direction: EXIT elements are finished too, they just produced no results.
    """
    idle: dict[str, bool] = {}
    for line in (bjobs or "").splitlines():
        fields = line.split()
        if len(fields) < 11 or not fields[0].isdigit():
            continue
        try:
            njobs, pend, done, run, exited, ssusp, ususp, psusp = (
                int(value) for value in fields[3:11]
            )
        except ValueError:
            continue
        idle[fields[0]] = (pend + run + ssusp + ususp + psusp) == 0 and (done + exited) == njobs
    return idle


def _abandoned(state: dict) -> bool:
    """True when no array this run submitted will do any more work.

    Two ways that happens, and both have wedged the ladder:

    `bjobs -A` answers "Job array <id> is not found" for an array the scheduler no longer knows
    about. One such line is not enough -- a run split across five arrays can have four finished
    and one still going -- so every submitted id has to be accounted for.

    An array LSF *does* still list, but whose every element has ended in EXIT, is equally never
    coming back, and matching only on "not found" missed it: auto-ac98e09efc0e sat on 8 of 5,901
    matches with one EXITed element, which recover_stranded_results() also skips because the
    cluster never reached done == total. Nothing fetched it, nothing re-queued it, and it
    deferred every later bot for as long as it was left alone.
    """
    job_ids = [str(job_id) for job_id in (state.get("job_ids") or [])]
    if not job_ids:
        return False
    bjobs = state.get("bjobs") or ""
    missing = set(re.findall(r"Job array <(\d+)> is not found", bjobs))
    idle = _idle_arrays(bjobs)
    return all(job_id in missing or idle.get(job_id, False) for job_id in job_ids)


def _resubmit_count(run_dir: Path) -> int:
    try:
        return int(json.loads((run_dir / "resubmits.json").read_text()).get("count", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        return 0


def _record_resubmit(run_dir: Path) -> None:
    count = _resubmit_count(run_dir) + 1
    try:
        (run_dir / "resubmits.json").write_text(
            json.dumps({"count": count, "at": datetime.now(UTC).isoformat(timespec="seconds")})
        )
    except OSError:
        pass


def resubmit_abandoned_runs(run_names: list[str], *, dry_run: bool = False) -> list[str]:
    """Re-queue runs whose arrays vanished with work still outstanding.

    The sibling failure to a stranded fetch, and the one that cannot fix itself. There, the
    cluster had finished and only the transfer was missing. Here the cluster stopped early --
    elements killed at walltime, an array cancelled, a scheduler restart -- so no amount of
    fetching completes the run, and because the automation evaluates one run at a time it defers
    every later bot behind work nobody is doing. auto-852f773c9500 sat that way with 4,830 of
    28,476 matches unrun and all its arrays gone.

    `hpc submit` is idempotent and content-addressed: it skips every match that already has a
    result and queues only the gaps, so this cannot duplicate work.

    Capped at MAX_RESUBMITS per run. A run that keeps coming back short is failing for a reason
    re-queueing will not fix, and an uncapped retry would quietly burn the cluster on it forever.
    """
    requeued: list[str] = []
    for tid in run_names:
        run_dir = planning.RUNS_ROOT / tid
        if not outstanding_matches(run_dir):
            continue
        try:
            settings = hpc.config()
            state = hpc.status(tid, settings)
        except (hpc.HpcError, OSError, KeyError) as error:
            print(f"  {tid}: cannot ask the cluster whether its jobs are gone ({error})")
            continue
        # A run that never recorded a job id was never queued at all -- planning wrote the
        # schedule, then the push or the bsub died before hpc.json existed. _abandoned() cannot
        # see it (it returns False on empty job_ids) and recover_stranded_results() cannot either
        # (the cluster never reaches done == total), so nothing owned it. On 2026-08-06 the
        # staging rsync hit a full quota and auto-33ab234bb994 sat at 0/6489 for four hours,
        # deferring every later bot behind a run no machine was working on.
        # All three have to hold. A missing hpc.json on its own is not proof: the file can be
        # absent while the cluster is demonstrably working the run, and re-pushing under a live
        # array would duplicate staged bots on the very quota this is meant to protect.
        never_submitted = (
            not (run_dir / "hpc.json").exists()
            and not state.get("job_ids")
            and state["done"] == 0
        )
        if state["done"] >= state["total"] or not (never_submitted or _abandoned(state)):
            continue
        unrun = state["total"] - state["done"]
        # Say which of the three it is. "every array is gone" was written for the vanished-array
        # case and read as a lie in the other two, which cost real time when reading the log.
        if never_submitted:
            cause = "was never queued (no job id was ever recorded)"
        elif _idle_arrays(state.get("bjobs") or ""):
            cause = "has no element left running"
        else:
            cause = "has lost every array"
        attempts = _resubmit_count(run_dir)
        if attempts >= MAX_RESUBMITS:
            print(
                f"  {tid}: {cause} with {unrun} match(es) unrun, but it has already been "
                f"re-submitted {attempts} time(s); leaving it for a human"
            )
            continue
        print(
            f"  {tid}: {cause} with {unrun} match(es) never run; "
            f"re-submitting the gaps (attempt {attempts + 1} of {MAX_RESUBMITS})"
        )
        if dry_run:
            requeued.append(tid)
            continue
        try:
            if never_submitted:
                # Nothing of this run reached the cluster, so there is nothing to fetch and the
                # staged bots still have to be pushed before bsub has anything to run.
                hpc.push(tid, settings)
            else:
                hpc.fetch(tid, settings)
            hpc.submit(tid, settings)
        except (hpc.HpcError, OSError) as error:
            print(f"  {tid}: re-submission failed ({error}); still treating it as in flight")
            continue
        _record_resubmit(run_dir)
        requeued.append(tid)
    return requeued


def recover_stranded_results(run_names: list[str], *, dry_run: bool = False) -> list[str]:
    """Fetch runs the cluster has finished but whose results never reached this machine.

    A run is "in flight" here iff its schedule is not fully merged locally, and that is derived
    from files on disk -- so a handful of result files that never came down keeps a *finished*
    run flagged forever, and every tick defers new bots behind it while printing nothing more
    alarming than "deferring". auto-f11bf027e3d4 sat that way on five results out of 12,285,
    holding three bots out of evaluation for about an hour.

    Deferring is correct when work really is running; it is only wrong when the cluster is done
    and the gap is a transfer that did not happen. So ask the cluster, and if it says the run is
    finished, pull it rather than waiting for a landing that has already happened.

    Returns the run ids that were recovered.
    """
    recovered: list[str] = []
    for tid in run_names:
        run_dir = planning.RUNS_ROOT / tid
        missing = outstanding_matches(run_dir)
        if not missing:
            continue
        try:
            settings = hpc.config()
            state = hpc.status(tid, settings)
        except (hpc.HpcError, OSError, KeyError) as error:
            # Never let a cluster hiccup stop a tick: deferring is still the safe outcome.
            print(f"  {tid}: cannot ask the cluster whether it finished ({error})")
            continue
        if state["done"] < state["total"]:
            continue
        print(
            f"  {tid}: cluster finished all {state['total']} matches but {len(missing)} result(s) "
            f"never reached this machine; fetching rather than deferring behind it"
        )
        if dry_run:
            recovered.append(tid)
            continue
        try:
            hpc.fetch(tid, settings)
        except (hpc.HpcError, OSError) as error:
            print(f"  {tid}: fetch failed ({error}); still treating it as in flight")
            continue
        left = outstanding_matches(run_dir)
        if left:
            print(f"  {tid}: {len(left)} result(s) still missing after fetch")
        else:
            recovered.append(tid)
    return recovered


def self_update(branch: str) -> bool:
    """Fast-forward this checkout onto origin/<branch>. Returns True if the code moved.

    The evaluator runs from a worktree pinned to a commit, so improvements to the harness or the
    site bundle never reach it otherwise -- it keeps publishing with whatever code it was
    installed with, which is invisible until the page looks wrong.

    Two safeguards. Fast-forward only, so a rewritten branch stops the update rather than
    silently discarding local state. And the test suite must pass on the new commit, otherwise
    the checkout is rolled back: a broken evaluator does not just fail, it submits cluster work
    and publishes to a live site.
    """
    before = _run(["git", "rev-parse", "HEAD"]).strip()
    try:
        _run(["git", "fetch", "origin", branch])
        _run(["git", "merge", "--ff-only", f"origin/{branch}"])
    except RuntimeError as error:
        print(f"self-update skipped: {error}".splitlines()[0])
        return False
    after = _run(["git", "rev-parse", "HEAD"]).strip()
    if after == before:
        return False

    print(f"self-update: {before[:7]} -> {after[:7]}; running tests before adopting it")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tournament/", "-q", "-x"],
        cwd=REPO_ROOT, text=True, capture_output=True,
    )
    if result.returncode != 0:
        _run(["git", "reset", "--hard", before])
        print(
            f"self-update ROLLED BACK to {before[:7]}: tests fail on {after[:7]}\n"
            + "\n".join(result.stdout.strip().splitlines()[-8:])
        )
        return False
    print(f"self-update adopted {after[:7]}; exiting so the next tick runs it")
    return True


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
    """Refresh the site's data bundle and deploy it.

    The bundle is deliberately *not* in git. It reached 185 MB across 167 files that are rewritten
    wholesale on every run, so committing it grew `.git` larger than the data itself within a week
    -- and bought nothing, because production is served from `wrangler deploy`, which uploads the
    working tree and never reads the repository. `public/botrankings/data/` is gitignored.

    That removes the side effect the deploy used to be triggered by. Committing the bundle moved
    the site's HEAD, and `_deploy` fired on HEAD moving; with no commit, HEAD never moves and the
    ladder would quietly stop updating. So a data refresh now asks for a deploy explicitly.
    """
    output = site_repo / "public" / "botrankings" / "data"
    build_site_data(run_dir, output)
    deploy_assets(site_repo, reason=f"ranking data for {ref[:7]}", build=True)


def _unpushed(branch: str, remote: str) -> bool:
    """True when HEAD carries commits the remote-tracking ref does not have.

    Deliberately reads the local ref rather than asking the remote: a tick that runs while the
    network is down should still try. A stale ref only costs a push that gets rejected, and the
    caller already rebases and retries on rejection.
    """
    try:
        ahead = _run(["git", "rev-list", "--count", f"{remote}/{branch}..HEAD"]).strip()
    except RuntimeError:
        # No remote-tracking ref yet -- a first push is exactly what is wanted.
        return True
    return ahead != "0"


def _push_data(branch: str, remote: str = "origin") -> None:
    """Commit whatever run data this checkout has gained and push it to <remote>/<branch>.

    The match and rating CSVs are the raw material for everyone else's analyses, so they have to
    leave the machine that happens to run the timer. .gitignore already narrows a run directory
    to the durable files -- manifest, matches, ratings, compliance; the bulk (staged bots,
    per-match JSON, LSF logs) stays local and is reproducible from them.

    Called once per tick over all of tournament/runs/ rather than per finished run, so a run
    still mid-collection travels too, and so results that a crashed tick or an older version of
    this worker left behind get picked up rather than stranded. Match rows are append-only and
    content-addressed, so a partial push simply gains the rest later.
    """
    head = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if head != branch:
        print(f"data push skipped: checkout is on {head}, not {branch}")
        return
    dirty = [
        line for line in _run(["git", "status", "--porcelain"]).splitlines()
        if line and not line[3:].startswith("tournament/runs/")
    ]
    if dirty:
        # A rebase or a stray commit of someone's half-edited harness is a worse outcome than a
        # late push; the next tick retries once the tree is clean.
        print("data push skipped: uncommitted changes outside tournament/runs/:")
        for line in dirty[:10]:
            print(f"    {line}")
        return

    _run(["git", "add", "--", "tournament/runs"])
    runs: list[str] = []
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT).returncode != 0:
        summary = _run(["git", "diff", "--cached", "--name-only"]).splitlines()
        runs = sorted(
            {Path(name).parts[2] for name in summary if name.startswith("tournament/runs/")}
        )
        _run(["git", "commit", "-m", "Add tournament results for " + ", ".join(runs)])

    # Committing and pushing are separate failures, so returning early on "nothing new to commit"
    # stranded every commit an earlier push had failed to deliver -- they could only leave on the
    # back of the *next* run's data. auto-ac98e09efc0e lost a race at 19:52 and left 13 commits
    # of match and rating CSVs sitting on this workstation with no retry in sight.
    if not _unpushed(branch, remote):
        return
    try:
        _run(["git", "push", remote, f"{branch}:{branch}"])
    except RuntimeError as error:
        # Somebody pushed to the branch while the cluster was working. Replay the data commit on
        # top instead of forcing: run directories are additive, so this cannot clobber their work.
        print(f"push rejected, rebasing onto {remote}/{branch}: {str(error).splitlines()[0]}")
        _run(["git", "fetch", remote, branch])
        _run(["git", "rebase", f"{remote}/{branch}"])
        _run(["git", "push", remote, f"{branch}:{branch}"])
    what = ", ".join(runs) if runs else "commits an earlier tick could not deliver"
    print(f"pushed run data to {remote}/{branch}: {what}")


def _site_is_dirty(site_repo: Path) -> list[str]:
    """Uncommitted *tracked* changes in the site checkout.

    `npm run build` compiles the working tree, so building while somebody edits the site would
    deploy their unfinished work, including a file saved mid-edit. Generated artefacts do not
    count: the data bundle, `dist/` and the deploy stamp are all gitignored, and `git status
    --porcelain` omits ignored paths, so this sees only genuine hand edits.
    """
    return [line for line in _run(["git", "status", "--porcelain"], site_repo).splitlines() if line]


def _dist_is_behind(site_repo: Path) -> bool:
    """True when the compiled output is missing ranking data that `public/` already has.

    The fast path uploads `dist/` untouched, and only `astro build` copies `public/` into it. So a
    ranking refresh whose own deploy was skipped -- lock lost, tree dirty, process killed -- leaves
    new data in `public/` that no later feed deploy will ever pick up, and the ladder sits frozen
    while every log line says "deployed". That is exactly how the site got stuck two runs behind
    while the feed kept publishing happily on top of it. Comparing the two manifests makes the
    fast path self-correcting: it notices it is about to ship something stale and compiles instead.
    """
    published = site_repo / "public" / "botrankings" / "data" / "index.json"
    compiled = site_repo / "dist" / "botrankings" / "data" / "index.json"
    if not published.exists():
        return False
    if not compiled.exists():
        return True
    return published.read_bytes() != compiled.read_bytes()


def deploy_assets(site_repo: Path, *, reason: str, build: bool = True) -> bool:
    """Publish the site to Cloudflare. Returns True when a deploy actually happened.

    `build=False` skips `astro build` for callers that have already written their output straight
    into `dist/`. That is the difference between a refresh costing seconds and costing minutes,
    which is what makes a feed on a five-minute timer viable at all. It is only safe when `dist/`
    already exists -- otherwise there is nothing to upload, so we build regardless.

    Two timers can reach this concurrently (the evaluator every two minutes, the live feed every
    five), and two overlapping `wrangler deploy` runs against one project is a race whose loser
    silently publishes stale assets. The lock serialises them; a caller that cannot get it returns
    rather than queueing, because by the next tick its content will be republished anyway.
    """
    if not site_repo.exists():
        return False
    dirty = _site_is_dirty(site_repo)
    if dirty:
        print(
            f"site repo has uncommitted changes; not deploying {reason}, so work in progress "
            "is not published:"
        )
        for line in dirty[:10]:
            print(f"    {line}")
        return False

    pending = site_repo / ".deploy-pending"
    lock_path = site_repo / ".deploy.lock"
    with open(lock_path, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Losing the lock used to be free, because the data commit had moved HEAD and the next
            # tick's HEAD check would retry. Untracked data removed that safety net: a skipped
            # compile leaves fresh output in public/ that nothing will ever copy into dist/. The
            # feed holds the lock for roughly a third of every two-minute window, so this is a
            # coin flip, not a rare race. Leave a note for `_deploy` to pick up next tick.
            if build:
                pending.write_text(f"{reason}\n")
            print(f"another deploy holds the lock; skipping {reason}")
            return False

        compiled = build or not (site_repo / "dist").exists() or _dist_is_behind(site_repo)
        if compiled:
            _run(["npm", "run", "build"], site_repo)
        _run(["npm", "exec", "--yes", "wrangler@latest", "--", "deploy"], site_repo)
        if compiled:
            # The stamp means "the source at this commit has been compiled and shipped", which is
            # only true when we just compiled. A feed refresh uploads whatever dist/ already held,
            # and that can predate HEAD; stamping HEAD there would convince `_deploy` the newest
            # commit was already live and it would never run the build that makes that true.
            (site_repo / ".last-deployed-commit").write_text(
                _run(["git", "rev-parse", "HEAD"], site_repo).strip() + "\n"
            )
            pending.unlink(missing_ok=True)
        print(f"deployed to Cloudflare ({reason})")
        return True


def _deploy(site_repo: Path) -> None:
    """Per-tick deploy of *source* changes: a UI fix or rebuilt component with no new results.

    Keyed on HEAD so the common case costs two git commands. Data and feed refreshes no longer
    move HEAD, so they call `deploy_assets` directly instead of relying on this.
    """
    if not site_repo.exists():
        return
    pending = site_repo / ".deploy-pending"
    if pending.exists():
        deploy_assets(
            site_repo, reason=f"retry of {pending.read_text().strip() or 'a skipped deploy'}",
            build=True,
        )
        return
    head = _run(["git", "rev-parse", "HEAD"], site_repo).strip()
    stamp = site_repo / ".last-deployed-commit"
    if stamp.exists() and stamp.read_text().strip() == head:
        return
    print(f"site moved to {head[:7]}; building and deploying")
    deploy_assets(site_repo, reason=f"source {head[:7]}", build=True)


def run_once(
    *,
    state_path: Path,
    canonical_run: str | None,
    sources: tuple[Source, ...],
    fetch_remote: str,
    self_update_branch: str | None = None,
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

    if self_update_branch:
        if self_update(self_update_branch):
            # Deliberately do not continue: the rest of this process is still running the old
            # code, and mixing the two halves is exactly the failure this guards against.
            return 0

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
    # Before treating anything as in flight, separate "still running" from "finished, but its
    # results never got here". Only the first is a reason to wait, and this runs ahead of the
    # deferral decision so a tick that closes the gap acts on it immediately instead of
    # deferring once more on state it just fixed.
    half_merged = unfinished_runs()
    if half_merged:
        recover_stranded_results(sorted(half_merged), dry_run=dry_run)
        # Runs the cluster abandoned rather than finished. Nothing else notices these: fetching
        # cannot complete them, so without this they defer every later bot indefinitely.
        resubmit_abandoned_runs(sorted(half_merged), dry_run=dry_run)
        half_merged = unfinished_runs()
    # Bots in a half-merged run of any kind are under test, automation-owned or not.
    for run_name, bots in sorted(half_merged.items()):
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
    # Resolve each in-flight bot to the code it actually is, not to whatever currently sits at
    # that bot_id. A bot_id is name@<branch-tip-sha>, so any push to a bot branch re-mints an id
    # for every bot on it -- including bots the push did not touch. Matching in-flight ids only
    # against freshly discovered specs therefore misses the common case: `prospect@1b5f3d1` is
    # under test, the branch moves, and the identical code comes back as `prospect@bf9b3e3` and
    # reads as never seen. all_specs covers ids that have already recorded a result; by_hash
    # covers ids at the current heads. A bot in a run with no results yet and an id no longer at
    # any head is in neither, which is why this is a second line of defence and not the fix.
    known_specs = dict(all_specs)
    for specs in by_hash.values():
        for spec in specs:
            known_specs.setdefault(spec.bot_id, spec)
    in_flight_hashes = set()
    for bot_id in in_flight_bots:
        spec = known_specs.get(bot_id)
        digest = duplicates.code_hash(spec.commit, spec.path) if spec else None
        if digest:
            in_flight_hashes.add(digest)

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
        if publish:
            _deploy(site_repo)
        return 0

    representatives = [_preferred(specs) for specs in unseen.values()]
    representatives.sort(key=lambda spec: spec.bot_id)
    # A bot that cannot be imported cannot play, and scheduling it wastes a whole run: every one
    # of its matches fails identically, so the run never completes and every later bot defers
    # behind it. Judged once per implementation and never retried -- a fix is new code with a new
    # hash, which is checked on its own merits.
    representatives, unloadable = loadcheck.partition(representatives)
    for spec, reason in unloadable:
        print(f"  excluding {spec.bot_id}: cannot be imported -- {reason}")
    print(f"{len(representatives)} unseen implementation(s) across {len(sources)} branch(es)")
    for spec in representatives:
        print(f"  {spec.bot_id:<30} {spec.path}")
    if not representatives:
        print("nothing left to schedule once unloadable bots are excluded")
        if publish:
            _deploy(site_repo)
        return 0
    if dry_run:
        return 0

    if in_flight_bots:
        # One run at a time, because canonical_field() is not constant. It contains only bots
        # that have already played, so it grows the moment an in-flight run lands. A challenger
        # planned now is scheduled against the field as it stands now, but finalise() rates it
        # against the field as it stands then -- and every entrant that arrived in between is a
        # pair that was never played and can only be imputed as a draw. finalise() is right to
        # refuse that, so the cost of planning early is not a worse ladder, it is a wedged one:
        # on 2026-08-02 two pushes ten minutes apart left 9 such pairs and the site went stale
        # for eighteen consecutive ticks until the gap was filled by hand.
        #
        # Deferring costs a run's latency and nothing else. `unseen` is re-derived from the
        # match data every tick, so the first tick after the in-flight run publishes will plan
        # exactly this work against a field that has stopped moving.
        waiting = ", ".join(spec.bot_id for spec in representatives)
        print(
            f"deferring {len(representatives)} unseen implementation(s) until "
            f"{len(in_flight_bots)} bot(s) under test have landed: {waiting}"
        )
        if publish:
            _deploy(site_repo)
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
        RUN_MAP_SPEC,
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
    "All the evidence" means ladder evidence: runs carrying an EXPERIMENT marker are private
    sweeps and never enter the published pool (see the note above _ladder_match_files).
    """
    seen: set[str] = set()
    rows: list[dict] = []
    for path in _ladder_match_files():
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
    # Official matches only. Entry to the canonical field is earned on the official pool: a bot
    # known only from a held-out run has no official record, so admitting it would guarantee the
    # incomplete-matrix error below. Duplicate detection is judged on the same evidence.
    rows = [row for row in pooled_matches() if not is_secret(row["map"])]
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
    # Matches involving a bot that cannot be imported are not waited on: they will never produce
    # a result, so requiring them here is what held a finished run open indefinitely.
    unplayable = len(_unplayable_scheduled(destination))
    if unplayable:
        print(f"  {tid}: {unplayable} scheduled match(es) involve a bot that cannot be imported")
        scheduled -= unplayable
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

    # The published ladder is defined over the official pool and only that. Held-out matches still
    # travel in matches-distinct.csv, because the website offers them as a separately-rated pool --
    # but folding them into ratings.csv would silently redefine the canonical numbers, and would
    # break the completeness check besides, since a held-out run covers its own field.
    official_rows = [row for row in distinct_rows if not is_secret(row["map"])]
    ratings = evaluate(official_rows)
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
    # Judged on the official pool too: two bots that play identically there are duplicates for
    # ladder purposes, and letting a held-out map split them would change who gets pruned.
    duplicates.write_csv(duplicates.behaviour_groups(official_rows),
                         destination / "duplicates.csv")

    print(f"  {tid}: rated {len(desired)} distinct bot(s) over {len(distinct_rows)} matches")
    for bot_id, covered_by in sorted(dropped):
        print(f"    duplicate: {bot_id} -> {covered_by}")

    # Merged, rated, and about to be published: the cluster's copy of this run's scratch has
    # stopped being the only copy of anything, and is now ~400 MB of pure cost against a 30 GB
    # quota that has filled twice. Reclaim it here rather than on a timer, because this is the
    # exact moment it becomes safe.
    hpc.discard_workspace(tid, settings)

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
    parser.add_argument(
        "--self-update-branch", default="x/tournament",
        help="fast-forward this checkout onto origin/<branch> before each tick, adopting the "
             "new code only if its tests pass",
    )
    parser.add_argument("--no-self-update", action="store_true")
    parser.add_argument("--site-repo", type=Path, default=DEFAULT_SITE)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument(
        "--data-branch", default="x/tournament",
        help="branch this checkout commits finished run data to and pushes, so the match and "
             "rating CSVs are on the remote for everyone else to analyse",
    )
    parser.add_argument("--no-push-data", action="store_true")
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
                self_update_branch=None if args.no_self_update else args.self_update_branch,
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
        finally:
            # Every tick, not only the one that finishes a run: results merged by a tick that
            # later failed, or by a version of this worker that predates the push, would
            # otherwise stay on this machine forever.
            if not args.no_push_data and not args.dry_run:
                try:
                    _push_data(args.data_branch, args.fetch_remote)
                except Exception as error:      # noqa: BLE001 - a failed push must not fail a tick
                    print(f"data push failed: {error}".splitlines()[0], file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
