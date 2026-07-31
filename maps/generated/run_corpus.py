"""Run a bot pairing over every generated map in both player orders."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
WINNER = re.compile(r"Winner:\s+(\S+)\s+\((.*?), turn\s+(\d+)\)")


@dataclass(frozen=True)
class Match:
    map_path: Path
    order: str
    first: str
    second: str


@dataclass(frozen=True)
class Result:
    match: Match
    winner: str | None
    reason: str
    turn: int


def bot_name(path: str) -> str:
    candidate = Path(path)
    return candidate.parent.name if candidate.name == "main.py" else candidate.name


def play(match: Match, tle: int, seed: int) -> Result:
    with tempfile.NamedTemporaryFile(suffix=".replay26") as replay:
        command = [
            "uv",
            "run",
            "fcode",
            "run",
            "--tle",
            str(tle),
            "--seed",
            str(seed),
            "--replay",
            replay.name,
            match.first,
            match.second,
            str(match.map_path),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            return Result(match, None, "runner timeout", 0)
    found = WINNER.search(completed.stdout.replace("\n", " "))
    if found is None:
        detail = completed.stderr.strip().splitlines()
        return Result(
            match,
            None,
            detail[-1] if detail else f"fcode exit {completed.returncode}",
            0,
        )
    return Result(match, found.group(1), found.group(2), int(found.group(3)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bot_a")
    parser.add_argument("bot_b")
    parser.add_argument(
        "--maps",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="directory containing generated .map26 files",
    )
    parser.add_argument("--tle", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    maps = sorted(args.maps.glob("*.map26"))
    if not maps:
        parser.error(f"no .map26 files in {args.maps}")
    jobs = [
        Match(path, "forward", args.bot_a, args.bot_b)
        for path in maps
    ] + [
        Match(path, "reverse", args.bot_b, args.bot_a)
        for path in maps
    ]
    name_a, name_b = bot_name(args.bot_a), bot_name(args.bot_b)
    wins = {name_a: 0, name_b: 0}
    errors = []
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        pending = {
            executor.submit(play, match, args.tle, args.seed): match
            for match in jobs
        }
        for future in as_completed(pending):
            result = future.result()
            results.append(result)
            if result.winner in wins:
                wins[result.winner] += 1
            else:
                errors.append(result)

    if args.verbose:
        for result in sorted(
            results, key=lambda item: (item.match.map_path.name, item.match.order)
        ):
            print(
                f"{result.match.map_path.name:54s} {result.match.order:7s} "
                f"{result.winner or 'ERROR':20s} "
                f"{result.reason} r{result.turn}"
            )
    total = len(jobs)
    print(
        f"{name_a} {wins[name_a]} - {wins[name_b]} {name_b}; "
        f"games={total} errors={len(errors)} seed={args.seed} tle={args.tle}"
    )
    for error in errors:
        print(
            f"ERROR {error.match.map_path.name} {error.match.order}: "
            f"{error.reason}"
        )
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
