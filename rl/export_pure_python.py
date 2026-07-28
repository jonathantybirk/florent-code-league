"""Export a trained torch checkpoint into a self-contained, dependency-free bot that
can actually be submitted to the ladder (`fcode submit`).

Why this exists: bots/rl/main.py (used for local self-play training) queries an
external inference server over a Unix socket, because torch can't be imported inside
the engine's per-unit sub-interpreters. That's fine for local/HPC training, where we
control the whole process tree -- but a submitted bot runs alone on AWS Graviton3
under a 10ms-per-turn CPU budget (docs/game-rules/game-rules-how-matches-work.md),
with no inference-server process running alongside it and, as far as the docs
describe, no reason to expect outbound socket/subprocess access to be available or
even permitted in that sandbox. So the deployable bot has to do everything itself,
in plain Python, using only what the training run already learned.

This script reads a checkpoint, dumps the trunk + per-entity-type head weights to
JSON, and copies a hand-rolled pure-Python forward pass (mirroring rl/policy.py's
architecture exactly) alongside it in bots/rl_deploy/. Keep rl/policy.py's HIDDEN_DIM
/ TRUNK_OUT_DIM small -- this is what makes the plain-Python matmuls fit the CPU
budget; see rl/policy.py's comment and the timing check in this module's __main__.

Usage:
    uv run python -m rl.export_pure_python checkpoints/policy.pt
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from rl.features import ENTITY_TYPES
from rl.policy import load_checkpoint

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = REPO_ROOT / "bots" / "rl_deploy"


def export(checkpoint_path: str | Path, out_dir: Path = DEPLOY_DIR) -> None:
    policy = load_checkpoint(checkpoint_path)
    state = policy.state_dict()

    def linear(prefix: str) -> dict:
        return {
            "w": state[f"{prefix}.weight"].tolist(),
            "b": state[f"{prefix}.bias"].tolist(),
        }

    weights = {
        "trunk": [linear("trunk.0"), linear("trunk.2")],
        "actor_heads": {t.value: linear(f"actor_heads.{t.value}") for t in ENTITY_TYPES},
        "critic_heads": {t.value: linear(f"critic_heads.{t.value}") for t in ENTITY_TYPES},
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "weights.json", "w") as f:
        json.dump(weights, f)

    shutil.copy(REPO_ROOT / "rl" / "features.py", out_dir / "features.py")
    shutil.copy(REPO_ROOT / "rl" / "_deploy_main_template.py", out_dir / "main.py")
    print(f"Exported to {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint")
    parser.add_argument("--out", default=str(DEPLOY_DIR))
    args = parser.parse_args()
    export(args.checkpoint, Path(args.out))


if __name__ == "__main__":
    main()
