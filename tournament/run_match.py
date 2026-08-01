"""Run exactly one match and write one result file. This is the LSF array-job payload.

    python -m tournament.run_match --run-dir runs/<tid> --index $LSB_JOBINDEX

*** This module and everything it imports must stay standard-library + fcode only. ***

The engine runs each bot in a CPython sub-interpreter with a SHARED_GIL and
check_multi_interp_extensions=1, inside this very process. Importing numpy/scipy/torch here would
put a second allocator and thread pool under that shared GIL; past attempts in this repo produced
segfaults and a "called while holding the GIL" autograd failure. Hence: one match per OS process,
no scientific stack, no reuse. tournament/local.py enforces the same rule with
max_tasks_per_child=1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import tempfile
import time
import traceback
from pathlib import Path

# Engine `winner` values are "A" / "B" / "draw"; we normalise case and carry a numeric score for
# bot A so the rating code never has to re-interpret the outcome.
SCORE = {"a": 1.0, "b": 0.0, "draw": 0.5}


def compliance_timings(replay: str) -> dict[str, int | list[int]]:
    """Extract instrumented unit-turn timings from a compliance replay.

    Bot stdout is embedded verbatim in the protobuf replay.  Pairing start/end markers lets us
    distinguish a CPU timeout (start without end) from a normal return, while an explicit error
    marker keeps ordinary bot exceptions from being mislabeled as timing violations.
    """
    from tournament.compliance import END_MARKER, ERROR_MARKER, START_MARKER

    try:
        payload = Path(replay).read_bytes()
    except OSError:
        return {
            "compliance_samples": 0,
            "compliance_turn_us": [],
            "compliance_max_turn_us": 0,
            "compliance_max_round": 0,
            "compliance_timeouts": 0,
            "compliance_exceptions": 0,
            "compliance_terminal_starts": 0,
        }

    def pairs(marker: str) -> list[tuple[int, int]]:
        pattern = re.escape(marker.encode()) + rb":(\d+):(\d+)"
        return [(int(round_), int(entity)) for round_, entity in re.findall(pattern, payload)]

    starts = pairs(START_MARKER)
    errors = set(pairs(ERROR_MARKER))
    end_pattern = re.escape(END_MARKER.encode()) + rb":(\d+):(\d+):(\d+)"
    ends = [
        (int(round_), int(entity), int(elapsed))
        for round_, entity, elapsed in re.findall(end_pattern, payload)
    ]
    completed = {(round_, entity) for round_, entity, _ in ends}
    unmatched = [key for key in starts if key not in completed and key not in errors]
    latest_round = {
        entity: max(round_ for round_, candidate in starts if candidate == entity)
        for _, entity in starts
    }
    # Actions such as self_destruct() deliberately end the entity during run(), so the wrapper's
    # end marker is unreachable.  A real CPU interruption is distinguishable because official
    # semantics call the same entity again next round.  An unmatched final appearance is retained
    # in the raw data but is not falsely called a timeout.
    timed_out = [key for key in unmatched if latest_round[key[1]] > key[0]]
    maximum = max(ends, key=lambda item: item[2], default=(0, 0, 0))
    return {
        "compliance_samples": len(ends),
        "compliance_turn_us": [elapsed for _, _, elapsed in ends],
        "compliance_max_turn_us": maximum[2],
        "compliance_max_round": maximum[0],
        "compliance_timeouts": len(timed_out),
        "compliance_exceptions": len(errors),
        "compliance_terminal_starts": len(unmatched) - len(timed_out),
    }


def engine_root() -> str:
    """The fcode package directory -- run_game needs it to locate the sandbox prelude."""
    import fcode

    return str(Path(fcode.__file__).resolve().parent)


def load_match(run_dir: Path, index: int) -> dict:
    """Read the 1-based `index`-th line of the schedule."""
    path = run_dir / "schedule.jsonl"
    with open(path) as handle:
        for lineno, line in enumerate(handle, start=1):
            if lineno == index:
                return json.loads(line)
    raise IndexError(f"index {index} is past the end of {path}")


def run(run_dir: Path, match: dict, keep_replay: bool = False) -> dict:
    """Play the match. Engine failures are recorded, never raised."""
    from fcode.fcode_engine import run_game

    a_main = str((run_dir / match["a_main"]).resolve())
    b_main = str((run_dir / match["b_main"]).resolve())
    map_path = str((run_dir / match["map_path"]).resolve())

    record = {
        "match_id": match["match_id"],
        "index": match["index"],
        "bot_a": match["bot_a"],
        "bot_b": match["bot_b"],
        "map": match["map"],
        "seed": match["seed"],
        "tle": match["tle"],
        "kind": match.get("kind", "rating"),
        "host": socket.gethostname(),
        "lsf_job": os.environ.get("LSB_JOBID", ""),
    }

    # Replays are megabytes each, so they go to node-local scratch and are deleted. Compliance
    # checks first extract their tiny timing markers; ordinary rating matches never read them.
    # The engine has no way to disable replay writing -- only to redirect it.
    replay_dir = tempfile.mkdtemp(prefix="fcode-replay-")
    replay = os.path.join(replay_dir, f"{match['match_id']}.replay26")

    started = time.time()
    try:
        result = run_game(
            a_main,
            b_main,
            engine_root(),
            map_path,
            replay,
            int(match["seed"]),
            int(match["tle"]),
        )
        winner = str(result.get("winner", "")).lower()
        if winner not in SCORE:
            raise ValueError(f"unexpected winner value from engine: {result.get('winner')!r}")
        record.update(
            status="ok",
            error="",
            winner=winner,
            score_a=SCORE[winner],
            win_condition=result.get("win_condition", ""),
            turns=result.get("turns", 0),
            resign_message=result.get("resign_message") or "",
            a_titanium=result.get("a_titanium", 0),
            a_titanium_collected=result.get("a_titanium_collected", 0),
            a_units=result.get("a_units", 0),
            a_buildings=result.get("a_buildings", 0),
            b_titanium=result.get("b_titanium", 0),
            b_titanium_collected=result.get("b_titanium_collected", 0),
            b_units=result.get("b_units", 0),
            b_buildings=result.get("b_buildings", 0),
        )
    except BaseException as error:  # noqa: BLE001 - one bad bot must not sink the tournament
        record.update(
            status="error",
            error=f"{type(error).__name__}: {error}".replace("\n", " ")[:500],
            winner="",
            score_a="",
            win_condition="",
            turns=0,
            resign_message="",
        )
        print(traceback.format_exc(), file=sys.stderr)
    finally:
        if match.get("kind") == "compliance":
            record.update(compliance_timings(replay))
        record["duration_s"] = round(time.time() - started, 3)
        record["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        if not keep_replay:
            try:
                os.unlink(replay)
            except OSError:
                pass
            try:
                os.rmdir(replay_dir)
            except OSError:
                pass
    return record


def write(run_dir: Path, record: dict) -> Path:
    """Write atomically: `fetch` rsyncs this directory while jobs are still writing into it."""
    results = run_dir / "results"
    results.mkdir(parents=True, exist_ok=True)
    final = results / f"{record['match_id']}.json"
    temporary = results / f".{record['match_id']}.json.tmp"
    temporary.write_text(json.dumps(record) + "\n")
    os.replace(temporary, final)
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one tournament match.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--index", required=True, type=int, help="1-based schedule line")
    parser.add_argument("--keep-replay", action="store_true")
    parser.add_argument(
        "--force", action="store_true", help="re-run even if a result file already exists"
    )
    args = parser.parse_args(argv)

    run_dir = args.run_dir.resolve()
    match = load_match(run_dir, args.index)

    existing = run_dir / "results" / f"{match['match_id']}.json"
    if existing.exists() and not args.force:
        print(f"skip {match['match_id']} (already done)")
        return 0

    record = run(run_dir, match, keep_replay=args.keep_replay)
    write(run_dir, record)
    print(
        f"{record['match_id']} {match['bot_a']} vs {match['bot_b']} on {match['map']}: "
        f"{record['status']} winner={record.get('winner') or '-'} "
        f"({record['duration_s']}s)"
    )
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
