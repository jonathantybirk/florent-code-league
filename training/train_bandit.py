"""Fit a per-arm linear reward model from training/runs/dataset.jsonl.

For each strategy arm, fits reward ~ w . features + b via ordinary least
squares (numpy lstsq) over the rows where that arm was chosen. This is the
plan's "contextual bandit" tier: a linear regression, greedy-argmax policy --
not yet any bootstrapped value function. Per the plan's rollout order, this
is the cheapest thing that could work and the starting point before
escalating to a semi-MDP actor-critic.

Writes bots/strategist/policy_weights.py, but does NOT wire it into
policy.py -- that's Phase 4, gated on evaluating these weights against the
fixed-rule selector over held-out seeds/maps first (plan's Phase 5).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

NUM_ARMS = 3  # HarvesterRush, GunnerDefense, SaboteurScout


def load_dataset(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f]


def fit(dataset: list[dict], ridge: float) -> list[dict]:
    num_features = len(dataset[0]["features"])
    weights = []
    for arm in range(NUM_ARMS):
        rows = [r for r in dataset if r["strategy_idx"] == arm]
        if len(rows) < num_features + 1:
            weights.append({"w": [0.0] * num_features, "b": 0.0, "n": len(rows)})
            continue
        x = np.array([r["features"] for r in rows], dtype=np.float64)
        y = np.array([r["reward"] for r in rows], dtype=np.float64)
        x_aug = np.hstack([x, np.ones((x.shape[0], 1))])
        # Ridge, not plain lstsq: features that are constant (or collinear)
        # within a small/early sample -- e.g. HP or nearby-enemy-count often
        # sit flat for a whole match -- make the unregularized system
        # rank-deficient and lstsq's least-norm solution distributes huge
        # canceling coefficients across those columns (seen firsthand on a
        # 61-row smoke test: one weight came out as -573). Don't regularize
        # the bias column.
        reg = ridge * np.eye(x_aug.shape[1])
        reg[-1, -1] = 0.0
        coef = np.linalg.solve(x_aug.T @ x_aug + reg, x_aug.T @ y)
        weights.append({"w": coef[:-1].tolist(), "b": float(coef[-1]), "n": len(rows)})
    return weights


def export(weights: list[dict], out_path: Path) -> None:
    lines = [
        '"""Learned per-arm linear reward weights.',
        "",
        "Exported by training/train_bandit.py from training/runs/dataset.jsonl.",
        "Not wired into policy.py yet -- Phase 4 of the plan replaces the fixed",
        "thresholds with argmax over arm(features) = w[arm] . features + b[arm]",
        'using these, once validated against the fixed-rule selector.',
        '"""',
        "",
        "ARM_WEIGHTS = [",
    ]
    for arm, w in enumerate(weights):
        lines.append(f"    {{'w': {w['w']!r}, 'b': {w['b']!r}}},  # arm {arm}, n={w['n']}")
    lines.append("]")
    out_path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parent / "runs" / "dataset.jsonl")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "bots" / "strategist" / "policy_weights.py",
    )
    parser.add_argument("--ridge", type=float, default=1.0, help="L2 penalty strength")
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)
    if not dataset:
        parser.error(f"no rows in {args.dataset} -- run training.harness and training.dataset first")

    weights = fit(dataset, args.ridge)
    export(weights, args.out)

    for arm, w in enumerate(weights):
        print(f"arm {arm}: n={w['n']} b={w['b']:.3f}")
    print(f"weights written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
