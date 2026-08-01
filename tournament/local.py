"""Run a schedule on this machine, one match per process.

Uses a process pool with max_tasks_per_child=1 for the same reason the HPC path uses one array
element per match: the engine's sub-interpreters are not safely reusable within a process. Workers
are therefore disposable by design, and the ~50 ms of interpreter startup per match is a rounding
error next to a match itself.
"""

from __future__ import annotations

import concurrent.futures as futures
import os
import sys
from pathlib import Path

from tournament.plan import Match, load_schedule, pending
from tournament.run_match import run, write


def _play(args: tuple[str, dict]) -> dict:
    run_dir, match = args
    record = run(Path(run_dir), match)
    write(Path(run_dir), record)
    return record


def run_all(run_dir: Path, jobs: int = 0, force: bool = False, limit: int = 0) -> list[dict]:
    """Play every outstanding match. Returns the records produced by this invocation."""
    matches: list[Match] = load_schedule(run_dir)
    todo = matches if force else pending(run_dir, matches)
    if limit:
        todo = todo[:limit]

    done = len(matches) - len(todo)
    if not todo:
        print(f"nothing to do: all {len(matches)} matches already have results")
        return []

    jobs = jobs or min(os.cpu_count() or 1, 8)
    print(f"{len(todo)} matches to play ({done} already done), {jobs} workers")

    payload = [(str(run_dir), match.__dict__) for match in todo]
    records: list[dict] = []
    errors = 0
    with futures.ProcessPoolExecutor(max_workers=jobs, max_tasks_per_child=1) as pool:
        for finished, record in enumerate(pool.map(_play, payload), start=1):
            records.append(record)
            if record["status"] != "ok":
                errors += 1
                print(f"  ERROR {record['match_id']}: {record['error']}", file=sys.stderr)
            if finished % 25 == 0 or finished == len(todo):
                print(f"  {finished}/{len(todo)} ({errors} errors)", flush=True)

    print(f"played {len(records)} matches, {errors} errors")
    return records
