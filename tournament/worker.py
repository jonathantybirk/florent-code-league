"""Run a worklist through a small, dynamically scheduled pool of match processes.

The LSF job owns several cores, but an individual fcode match still owns exactly one fresh OS
process.  Keeping the pool here (rather than starting one LSF array element per match) gives LSF
one long-lived job while fast workers immediately take another match instead of going idle behind
a slow, statically assigned slice.

This module intentionally stays standard-library-only.  See run_match.py for why importing the
scientific Python stack anywhere in the match process path is unsafe.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


STOPPED = 75


def load_worklist(path: Path) -> list[int]:
    return [int(line) for line in path.read_text().splitlines() if line.strip()]


def run_indices(
    indices: Iterable[int],
    jobs: int,
    run_one: Callable[[int], int],
    stop_file: Path | None = None,
) -> tuple[int, bool]:
    """Drain `indices` with at most `jobs` active calls, stopping between matches on demand."""
    if jobs < 1:
        raise ValueError("jobs must be at least one")

    stopped = False

    def guarded(index: int) -> int | None:
        nonlocal stopped
        if stop_file is not None and stop_file.exists():
            stopped = True
            return None
        return run_one(index)

    completed = 0
    with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="match-worker") as pool:
        # Calls may already be queued in the executor, but the stop check runs when a thread
        # actually takes one. Already-running matches finish and leave their atomic result files.
        for result in pool.map(guarded, indices):
            if result is not None:
                completed += 1
    return completed, stopped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drain an HPC tournament worklist.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--worklist", required=True, type=Path)
    parser.add_argument("--jobs", required=True, type=int)
    parser.add_argument("--stop-file", type=Path)
    args = parser.parse_args(argv)

    indices = load_worklist(args.worklist)
    print(f"worker pool: {len(indices)} matches across {args.jobs} process slots", flush=True)

    def run_one(index: int) -> int:
        # No capture: LSF receives each child's diagnostics as they happen.  A failed engine match
        # still writes an error result; a process-level failure leaves a gap for normal recovery.
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "tournament.run_match",
                "--run-dir",
                str(args.run_dir),
                "--index",
                str(index),
            ],
            check=False,
        ).returncode

    completed, stopped = run_indices(indices, args.jobs, run_one, args.stop_file)
    print(f"worker pool: launched {completed}/{len(indices)} matches", flush=True)
    return STOPPED if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
