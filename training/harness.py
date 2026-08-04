"""Self-play + vs-reference-bot match harness for training bots/strategist's
strategy selector.

Runs bots/strategist against every opponent in --opponents (bots/strategist
itself included, for self-play) across a pool of maps (official +
maps/generated/'s representative/random corpora), each match its own
`fcode run --json --tle <n>` subprocess with FCL_TELEMETRY_PATH pointed at a
per-match *prefix*. Mirrors maps/generated/run_corpus.py's parallel-subprocess
pattern (Jon's map-corpus runner), but adds JSON output parsing instead of
regex-on-text and per-match telemetry wiring.

FCL_TELEMETRY_PATH is a prefix, not a literal file: policy.py's
_log_decision appends ".<team>.<unit_id>.jsonl" per unit, since the engine
runs multiple Builder Bots concurrently within one match and sharing a
single file caused interleaved/corrupted JSON lines in practice. dataset.py
globs "<prefix>.*.jsonl" to recover every unit's file for a match. Only
bots/strategist's own policy.py ever writes telemetry (the reference bots --
starter/green/tester -- have no such hook), so these files always contain
only "our" decisions: both teams' in a self-play match (distinguished by the
"team" field), or just strategist's side in a vs-reference-bot match.

Each invocation truncates manifest.jsonl at --out (default training/runs/)
-- point --out at a fresh directory for a real run, or a scratch directory
when just testing the harness itself, so a real run's manifest never gets
clobbered by an unrelated test invocation.

Usage:
    uv run python -m training.harness --limit-maps 3 --seeds 1
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGIST = "bots/strategist"

DEFAULT_OPPONENTS = [
    STRATEGIST,  # self-play
    # Pulled from origin/x/luc (git checkout origin/x/luc -- bots/luc/heimdall
    # bots/luc/odin), same approach as maps/generated from x/jon: both are
    # marked status = "development" in their own BOT_VERSION.toml, so these
    # are point-in-time snapshots, not synced copies -- re-pull if training
    # against Luc's current version matters later, and worth telling him
    # they're being used as training opponents. Filed under bots/test/ along
    # with the rest of this repo's non-original/non-ready bots.
    "bots/test/luc/heimdall",
    "bots/test/luc/odin",
]

DEFAULT_MAP_DIRS = [
    ROOT / "maps",
    ROOT / "maps" / "generated",
    ROOT / "maps" / "generated" / "representative",
]


@dataclass(frozen=True)
class MatchJob:
    map_path: Path
    order: str  # "forward": strategist plays A; "reverse": strategist plays B
    opponent: str
    seed: int


@dataclass
class MatchOutcome:
    job: MatchJob
    result: dict | None
    telemetry_path: Path
    error: str | None = None


def _collect_maps() -> list[Path]:
    seen = set()
    maps = []
    for d in DEFAULT_MAP_DIRS:
        for p in sorted(d.glob("*.map26")):
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                maps.append(p)
    return maps


def run_match(
    bot_a: str, bot_b: str, map_path: Path, seed: int, tle: int, telemetry_path: Path | None,
    explore_eps: float = 0.0,
) -> tuple[dict | None, str | None]:
    """Run one `fcode run --json` subprocess and return (result, error).

    telemetry_path, if given, is a *prefix* (see the module docstring) passed
    via FCL_TELEMETRY_PATH -- left unset entirely when None, e.g. for
    evaluate.py's win-rate comparisons, which have no use for training data.

    explore_eps sets FCL_EXPLORE_EPS, policy.py's epsilon-greedy override
    that samples arms the fixed rule alone never would (see
    bots/strategist/policy.py's _maybe_explore docstring) -- 0.0 (default) is
    a no-op, matching policy.py's own unset-env-var default.
    """
    with tempfile.NamedTemporaryFile(suffix=".replay26") as replay:
        command = [
            "uv", "run", "fcode", "run",
            "--tle", str(tle),
            "--seed", str(seed),
            "--replay", replay.name,
            "--json",
            bot_a, bot_b, str(map_path),
        ]
        env = dict(os.environ)
        if telemetry_path is not None:
            env["FCL_TELEMETRY_PATH"] = str(telemetry_path)
        if explore_eps > 0.0:
            env["FCL_EXPLORE_EPS"] = str(explore_eps)
        try:
            completed = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, timeout=180, env=env,
            )
        except subprocess.TimeoutExpired:
            return None, "runner timeout"

    lines = completed.stdout.strip().splitlines()
    try:
        result = json.loads(lines[-1]) if lines else {}
    except ValueError:
        result = {}
    if "winner" not in result:
        detail = completed.stderr.strip().splitlines()
        return None, detail[-1] if detail else f"fcode exit {completed.returncode}"
    return result, None


def play(job: MatchJob, tle: int, telemetry_dir: Path, explore_eps: float = 0.0) -> MatchOutcome:
    bot_a, bot_b = (STRATEGIST, job.opponent) if job.order == "forward" else (job.opponent, STRATEGIST)
    # A prefix, not a literal file -- policy.py's _log_decision appends
    # ".<team>.<unit_id>.jsonl" per unit (see the module docstring above).
    telemetry_path = telemetry_dir / (
        f"{job.map_path.stem}-{job.order}-{Path(job.opponent).name}-seed{job.seed}"
    )
    result, error = run_match(bot_a, bot_b, job.map_path, job.seed, tle, telemetry_path, explore_eps)
    return MatchOutcome(job, result, telemetry_path, error)


def build_jobs(maps: list[Path], opponents: list[str], seeds: list[int]) -> list[MatchJob]:
    jobs = []
    for map_path in maps:
        for opponent in opponents:
            orders = ["forward"] if opponent == STRATEGIST else ["forward", "reverse"]
            for order in orders:
                for seed in seeds:
                    jobs.append(MatchJob(map_path, order, opponent, seed))
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opponents", nargs="+", default=DEFAULT_OPPONENTS)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--tle", type=int, default=10)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--out", type=Path, default=ROOT / "training" / "runs")
    parser.add_argument("--limit-maps", type=int, default=None, help="cap map count, for a quick smoke test")
    parser.add_argument(
        "--explore-eps", type=float, default=0.0,
        help="epsilon for policy.py's exploration override (0.0 = fixed-rule only, no coverage fix)",
    )
    parser.add_argument(
        "--shard-count", type=int, default=1,
        help="split the full job list into this many shards (for HPC job arrays); each shard "
             "still needs its own --out, since manifest.jsonl/telemetry aren't shard-aware",
    )
    parser.add_argument(
        "--shard-index", type=int, default=0,
        help="0-indexed shard to run out of --shard-count (e.g. LSB_JOBINDEX - 1 in a bsub array)",
    )
    args = parser.parse_args()
    if not 0 <= args.shard_index < args.shard_count:
        parser.error("--shard-index must be in [0, --shard-count)")

    maps = _collect_maps()
    if args.limit_maps:
        maps = maps[: args.limit_maps]

    telemetry_dir = args.out / "telemetry"
    # Wiped, not just created, on every invocation -- telemetry filenames are
    # deterministic (map/order/opponent/seed, no run-id) and policy.py's
    # _log_decision appends per unit, so a second invocation over a leftover
    # telemetry dir silently concatenates unrelated matches' round-numbered
    # records into the same file instead of overwriting. This corrupted a
    # real run's dataset (multiple exploring/non-exploring attempts merged
    # into single files, 4x duplicated round sequences) before this guard
    # existed. manifest.jsonl already gets truncated the same way below --
    # this just makes telemetry consistent with that "every run starts
    # clean" contract instead of being the one piece that silently doesn't.
    if telemetry_dir.exists():
        shutil.rmtree(telemetry_dir)
    telemetry_dir.mkdir(parents=True)

    jobs = build_jobs(maps, args.opponents, args.seeds)
    # Sliced after building the full deterministic list (not e.g. seeds
    # pre-split per shard) so shard count can change between runs without
    # anyone having to work out a matching seed/map partition by hand.
    jobs = jobs[args.shard_index :: args.shard_count]
    shard_note = f", shard {args.shard_index + 1}/{args.shard_count}" if args.shard_count > 1 else ""
    print(
        f"{len(jobs)} matches queued "
        f"({len(maps)} maps x {len(args.opponents)} opponents x {len(args.seeds)} seeds{shard_note}), "
        f"{args.jobs} parallel workers",
        flush=True,
    )

    # Appended to as each match finishes (not batched at the end): a run of
    # 2000+ matches can take hours, and losing every completed result to an
    # interruption or crash partway through would be a bad way to find that
    # out. training.dataset can be pointed at a still-growing manifest.
    manifest_path = args.out / "manifest.jsonl"
    errors: list[MatchOutcome] = []
    done = 0
    start = time.monotonic()
    with open(manifest_path, "w") as manifest_f, ThreadPoolExecutor(max_workers=args.jobs) as executor:
        pending = {
            executor.submit(play, job, args.tle, telemetry_dir, args.explore_eps): job for job in jobs
        }
        for future in as_completed(pending):
            outcome = future.result()
            done += 1
            if outcome.error:
                errors.append(outcome)
            else:
                manifest_f.write(json.dumps({
                    "map": str(outcome.job.map_path),
                    "opponent": outcome.job.opponent,
                    "order": outcome.job.order,
                    "seed": outcome.job.seed,
                    "telemetry_path": str(outcome.telemetry_path),
                    "result": outcome.result,
                }) + "\n")
                manifest_f.flush()

            elapsed = time.monotonic() - start
            rate = done / elapsed if elapsed > 0 else 0.0
            eta_min = (len(jobs) - done) / rate / 60 if rate > 0 else float("inf")
            status = f"ERROR: {outcome.error}" if outcome.error else f"winner={outcome.result.get('winner')}"
            print(
                f"[{done}/{len(jobs)}] {outcome.job.map_path.name} vs {outcome.job.opponent} "
                f"({outcome.job.order}) seed={outcome.job.seed} -> {status}  "
                f"[{rate:.2f} matches/s, ~{eta_min:.1f} min left]",
                flush=True,
            )
    print(f"done in {(time.monotonic() - start) / 60:.1f} min", flush=True)

    print(f"{done - len(errors)}/{len(jobs)} matches ok, {len(errors)} errors")
    for e in errors[:10]:
        print(f"ERROR {e.job.map_path.name} vs {e.job.opponent} ({e.job.order}) seed={e.job.seed}: {e.error}")
    print(f"manifest written to {manifest_path}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
