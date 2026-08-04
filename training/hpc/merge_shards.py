"""Merge manifest.jsonl files from a sharded HPC run (training/hpc/submit_dtu_lsf.sh)
into one manifest training/dataset.py can read.

Each shard's telemetry_path entries are relative to the repo root (the bsub
script cds there before running the harness) and point into that shard's own
training/runs/shard_N/telemetry/ dir, which is left in place -- this only
concatenates the small manifest.jsonl files, it doesn't move any telemetry.
Run this from the repo root, same as training.dataset.

Usage:
    uv run python -m training.hpc.merge_shards --out training/runs/manifest.jsonl
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards-glob", default="training/runs/shard_*/manifest.jsonl")
    parser.add_argument("--out", type=Path, default=ROOT / "training" / "runs" / "manifest.jsonl")
    args = parser.parse_args()

    shard_manifests = sorted(ROOT.glob(args.shards_glob))
    if not shard_manifests:
        print(f"no shard manifests matched {args.shards_glob!r}")
        return 1

    total_lines = 0
    with open(args.out, "w") as out_f:
        for shard_manifest in shard_manifests:
            with open(shard_manifest) as in_f:
                for line in in_f:
                    if line.strip():
                        out_f.write(line)
                        total_lines += 1
            print(f"{shard_manifest}: merged")

    print(f"{total_lines} entries from {len(shard_manifests)} shards -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
