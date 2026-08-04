"""Phase 5 evaluation gate: compare the learned bandit selector
(bots/strategist_learned, argmax over policy_weights.ARM_WEIGHTS) against
the fixed-rule baseline (bots/strategist) before wiring ARM_WEIGHTS into
bots/strategist/policy.py for real.

Runs both bots through the same opponent pool, plus a head-to-head match
against each other, on seeds not used to produce ARM_WEIGHTS (that run used
--seeds 1-5; default here is 6-10). No telemetry is written -- this is a
win-rate comparison, not another training data source.

Usage:
    uv run python -m training.evaluate --seeds 6 7 8 9 10
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from training.harness import _collect_maps, run_match

FIXED = "bots/strategist"
LEARNED = "bots/strategist_learned"
OPPONENTS = [
    "bots/test/luc/heimdall", "bots/test/luc/odin",  # pulled from origin/x/luc, see harness.py's DEFAULT_OPPONENTS
]


@dataclass(frozen=True)
class EvalJob:
    map_path: Path
    bot_a: str
    bot_b: str
    seed: int
    matchup: str
    head_to_head: bool  # fixed vs learned, rather than either vs an OPPONENTS entry


def build_jobs(maps: list[Path], seeds: list[int]) -> list[EvalJob]:
    jobs = []
    for map_path in maps:
        for seed in seeds:
            for candidate, tag in ((FIXED, "fixed"), (LEARNED, "learned")):
                for opponent in OPPONENTS:
                    opp_name = Path(opponent).name
                    jobs.append(EvalJob(map_path, candidate, opponent, seed, f"{tag}(A)-vs-{opp_name}(B)", False))
                    jobs.append(EvalJob(map_path, opponent, candidate, seed, f"{opp_name}(A)-vs-{tag}(B)", False))
            jobs.append(EvalJob(map_path, FIXED, LEARNED, seed, "fixed(A)-vs-learned(B)", True))
            jobs.append(EvalJob(map_path, LEARNED, FIXED, seed, "learned(A)-vs-fixed(B)", True))
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[6, 7, 8, 9, 10])
    parser.add_argument("--tle", type=int, default=10)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--limit-maps", type=int, default=None, help="cap map count, for a quick smoke test")
    args = parser.parse_args()

    maps = _collect_maps()
    if args.limit_maps:
        maps = maps[: args.limit_maps]

    jobs = build_jobs(maps, args.seeds)
    print(f"{len(jobs)} evaluation matches queued ({len(maps)} maps x {len(args.seeds)} seeds)", flush=True)

    # Tracked separately, not just one blended total: a head-to-head win only
    # says "beat the other strategist variant," not "beat heimdall/odin" --
    # collapsing the two into one win rate answers neither question cleanly.
    vs_opponent: dict[str, dict[str, int]] = defaultdict(lambda: {"w": 0, "l": 0, "d": 0})
    head_to_head: dict[str, dict[str, int]] = defaultdict(lambda: {"w": 0, "l": 0, "d": 0})
    errors: list[tuple[EvalJob, str]] = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        pending = {
            executor.submit(run_match, job.bot_a, job.bot_b, job.map_path, job.seed, args.tle, None): job
            for job in jobs
        }
        for future in as_completed(pending):
            job = pending[future]
            result, error = future.result()
            done += 1
            if error:
                errors.append((job, error))
                print(f"[{done}/{len(jobs)}] ERROR {job.matchup} seed={job.seed}: {error}", flush=True)
                continue

            winner = result.get("winner")
            record = head_to_head if job.head_to_head else vs_opponent
            for name, side in ((job.bot_a, "A"), (job.bot_b, "B")):
                if name not in (FIXED, LEARNED):
                    continue
                if winner == side:
                    record[name]["w"] += 1
                elif winner is None:
                    record[name]["d"] += 1
                else:
                    record[name]["l"] += 1
            print(f"[{done}/{len(jobs)}] {job.matchup} seed={job.seed} -> winner={winner}", flush=True)

    def _report(title: str, record: dict[str, dict[str, int]]) -> None:
        print(f"=== {title} ===")
        for name in (FIXED, LEARNED):
            r = record[name]
            total = r["w"] + r["l"] + r["d"]
            rate = r["w"] / total if total else 0.0
            print(f"{name}: {r['w']}W-{r['l']}L-{r['d']}D over {total} matches (win rate {rate:.1%})")

    print()
    _report(f"vs opponents ({', '.join(Path(o).name for o in OPPONENTS)})", vs_opponent)
    print()
    _report("head-to-head (fixed vs learned only)", head_to_head)
    if errors:
        print(f"\n{len(errors)} matches errored")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
