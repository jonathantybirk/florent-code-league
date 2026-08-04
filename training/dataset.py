"""Assemble (features, strategy_idx, reward) training tuples from a harness run.

Reads training/runs/manifest.jsonl (written by harness.py) plus each match's
per-match telemetry file. policy.py re-evaluates select_strategy() every
round, but the fixed selector only actually *changes* strategy occasionally,
so consecutive rounds choosing the same strategy_idx for one unit are
grouped into a macro-decision "window" -- the unit of (features, action,
reward) this dataset trains over, matching the plan's temporal-abstraction
framing without needing main.py to throttle decisions to every K rounds.

Reward per window = locally shaped delta over the window (own titanium,
harvester count, HP fraction -- all already ~[0,1]-normalized features) plus
a terminal +/-TERMINAL_REWARD win/loss bonus on the window containing that
unit's last logged round. Weights are a starting point, not tuned.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

W_TITANIUM = 1.0
W_HARVESTER = 1.0
W_HP = 1.0
TERMINAL_REWARD = 5.0

# Indices into the feature tuple from bots/strategist/features.py's
# FEATURE_NAMES -- duplicated here (not imported) since this runs with the
# host's Python/numpy, not the bot's sys.path.
IDX_TITANIUM = 1
IDX_HP = 3
IDX_HARVESTER = 5


def _windows(records: list[dict]) -> list[dict]:
    """Group a round-sorted list of one unit's decisions into contiguous
    same-strategy_idx windows."""
    windows: list[dict] = []
    current: dict | None = None
    for rec in records:
        if current is None or rec["strategy_idx"] != current["strategy_idx"]:
            if current is not None:
                windows.append(current)
            current = {"strategy_idx": rec["strategy_idx"], "records": [rec]}
        else:
            current["records"].append(rec)
    if current is not None:
        windows.append(current)
    return windows


def _load_records(path: Path, skipped: list[int]) -> list[dict]:
    records = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                # Defensive only: per-unit files shouldn't see this anymore
                # (see policy.py's _log_decision), but a killed process could
                # still leave a truncated last line.
                skipped[0] += 1
    return records


def build_dataset(manifest_path: Path) -> list[dict]:
    dataset: list[dict] = []
    skipped = [0]
    with open(manifest_path) as f:
        entries = [json.loads(line) for line in f]

    for entry in entries:
        # entry["result"]["winner"] is "A"/"B" (fcode's CLI convention, upper
        # case) or null for a draw; telemetry's "team" field is Team.value
        # ("a"/"b", lower case, confirmed via `Team.A.value == "a"`). Without
        # lowering one side, `winner == team` is always False -- every unit,
        # including the actual winner's, would fall into the loss branch
        # below. Caught by hand-checking a known match's outcome.
        winner_raw = entry["result"].get("winner")
        winner = winner_raw.lower() if winner_raw else None
        # telemetry_path in the manifest is the prefix passed as
        # FCL_TELEMETRY_PATH; policy.py appends ".<team>.<unit_id>.jsonl"
        # per unit (see _log_decision), so one match maps to one file per
        # unit that actually made a Builder Bot decision.
        prefix = Path(entry["telemetry_path"])
        telemetry_files = sorted(prefix.parent.glob(prefix.name + ".*.jsonl"))
        if not telemetry_files:
            continue

        by_unit: dict[tuple[str, int], list[dict]] = {}
        for telemetry_path in telemetry_files:
            for rec in _load_records(telemetry_path, skipped):
                key = (rec["team"], rec["unit_id"])
                by_unit.setdefault(key, []).append(rec)

        for (team, _unit_id), records in by_unit.items():
            records.sort(key=lambda r: r["round"])
            windows = _windows(records)
            if winner == team:
                terminal_bonus = TERMINAL_REWARD
            elif winner is not None:
                terminal_bonus = -TERMINAL_REWARD
            else:
                terminal_bonus = 0.0

            for i, window in enumerate(windows):
                start_feats = window["records"][0]["features"]
                end_feats = window["records"][-1]["features"]
                reward = (
                    W_TITANIUM * (end_feats[IDX_TITANIUM] - start_feats[IDX_TITANIUM])
                    + W_HARVESTER * (end_feats[IDX_HARVESTER] - start_feats[IDX_HARVESTER])
                    + W_HP * (end_feats[IDX_HP] - start_feats[IDX_HP])
                )
                if i == len(windows) - 1:
                    reward += terminal_bonus
                dataset.append({
                    "features": start_feats,
                    "strategy_idx": window["strategy_idx"],
                    "reward": reward,
                })

    if skipped[0]:
        print(f"warning: skipped {skipped[0]} malformed telemetry line(s)")
    return dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parent / "runs" / "manifest.jsonl")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "runs" / "dataset.jsonl")
    args = parser.parse_args()

    dataset = build_dataset(args.manifest)
    with open(args.out, "w") as f:
        for row in dataset:
            f.write(json.dumps(row) + "\n")

    by_arm: dict[int, int] = {}
    for row in dataset:
        by_arm[row["strategy_idx"]] = by_arm.get(row["strategy_idx"], 0) + 1
    print(f"{len(dataset)} (features, strategy_idx, reward) tuples written to {args.out}")
    print(f"by arm: {by_arm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
