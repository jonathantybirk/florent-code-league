"""Compare subjects in a benchmarks/suite.py run: rate, composition, and identity.

Three questions, one pass over the result JSONs:

    who won              win rate against a shared opponent, with a z against
                         a named baseline
    what they built      the per-game composition metrics the suite already
                         writes (builders, turrets, conveyors, core damage)
    did it even run      how many of the baseline's games came out *bit
                         identical* -- same winner, same round count

The third column is the one worth having. A variant that measures 0.0 sd may be
a real mechanism that cancels out, or code that never executed, and those want
opposite responses -- tune the first, fix the gate on the second. On
2026-08-09 this separated three seat-B flags that were reported as "0.0 sd, no
improvement" in an earlier sweep from the truth, which is that all three are
pure no-ops: 300 of 300 games identical to shipped.

    uv run python tools/suite_compare.py RUN_DIR --opponent spar_sentinel
    uv run python tools/suite_compare.py RUN_DIR --opponent undertow --baseline snotra_h

Stdlib only.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import os


def subject(path: str) -> str:
    """The bot directory name, which is how the suite identifies a subject."""
    return os.path.basename(os.path.dirname(path))


def load(run_dir: str, opponent: str):
    """(wins, games, metrics, per-game outcome) for every subject in the run."""
    record = collections.defaultdict(lambda: [0, 0])
    metrics = collections.defaultdict(lambda: collections.defaultdict(list))
    outcome = collections.defaultdict(dict)
    for path in glob.glob(os.path.join(run_dir, "results", "*.json")):
        with open(path) as handle:
            game = json.load(handle)
        if game.get("status") != "ok":
            continue
        a, b = subject(game["a"]), subject(game["b"])
        if opponent not in (a, b):
            continue
        name = b if a == opponent else a
        # Which seat the subject played, so `a_`/`b_` metrics can be read as
        # "ours" and "theirs" rather than by position.
        ours = "b" if a == opponent else "a"
        seat = "A" if ours == "a" else "B"
        record[name][0] += game["engine"]["winner"] == seat
        record[name][1] += 1
        # A cell is one map played from one seat; that is the unit that has to
        # match for two builds to have played the same game.
        outcome[name][(game["map"], seat)] = (game["engine"]["winner"],
                                              game["metrics"].get("rounds"))
        for key, value in game["metrics"].items():
            if isinstance(value, (int, float)) and key.startswith(ours + "_"):
                metrics[name][key[2:]].append(value)
    return record, metrics, outcome


def mean(values) -> float:
    return sum(values) / len(values) if values else float("nan")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--opponent", required=True,
                        help="the shared opponent every subject was duelled against")
    parser.add_argument("--baseline", default=None,
                        help="subject to compare against (default: best guess)")
    parser.add_argument("--metrics", default="builders_spawned,gunners_built,"
                        "sentinels_built,harvesters_built,conveyors_built",
                        help="comma-separated metric names to show")
    args = parser.parse_args()

    record, metrics, outcome = load(args.run_dir, args.opponent)
    if not record:
        print(f"no games against {args.opponent!r} in {args.run_dir}")
        return 1

    baseline = args.baseline
    if baseline is None:
        # Whichever subject looks like the shipped build, else the first name.
        for candidate in ("snotra_h", "steward_hardened_reinforced"):
            if candidate in record:
                baseline = candidate
                break
        else:
            baseline = sorted(record)[0]
    if baseline not in record:
        print(f"baseline {baseline!r} not in this run: {sorted(record)}")
        return 1

    base_wins, base_games = record[baseline]
    base_rate = base_wins / base_games
    base_outcome = outcome[baseline]
    shown = [m.strip() for m in args.metrics.split(",") if m.strip()]

    print(f"run {args.run_dir}   opponent {args.opponent}   baseline {baseline}\n")
    header = f"{'subject':22s}{'record':>11}{'rate':>8}{'vs base':>18}{'identical':>11}"
    header += "".join(m[:13].rjust(15) for m in shown)
    print(header)
    print("-" * len(header))
    for name, (wins, games) in sorted(record.items(),
                                      key=lambda kv: -kv[1][0] / max(1, kv[1][1])):
        rate = wins / games
        delta = ""
        if name != baseline:
            difference = rate - base_rate
            spread = math.sqrt(rate * (1 - rate) / games
                               + base_rate * (1 - base_rate) / base_games)
            delta = f"{difference:+.3f} ({difference / spread:+.1f} sd)" if spread else ""
        same = sum(1 for cell, value in outcome[name].items()
                   if base_outcome.get(cell) == value)
        identical = "-" if name == baseline else f"{same}/{len(outcome[name])}"
        row = f"{name[:22]:22s}{wins:5d}/{games:<5d}{rate:8.4f}{delta:>18}{identical:>11}"
        row += "".join(f"{mean(metrics[name][m]):15.2f}" for m in shown)
        print(row)
        if name != baseline and same == len(outcome[name]) and same:
            print(f"{'':22s}^ pure no-op against this opponent: every game identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
