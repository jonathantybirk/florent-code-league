#!/bin/sh
### DTU HPC (LSF) job array for training/harness.py.
###
### The full sweep is ~2415 matches (5 seeds x 69 maps x 4 opponents,
### doubled for forward/reverse on non-self-play opponents -- see
### training/harness.py's build_jobs()). Each match is one CPU-bound
### `fcode run` subprocess; matches are fully independent, so this splits
### the job list into ARRAY_SIZE shards (training.harness's --shard-index/
### --shard-count) and lets LSF run them as separate array tasks instead of
### one long single-node job.
###
### Fill in / check before submitting:
###   - REPO: absolute path to this checkout on the DTU filesystem.
###   - Run `uv sync` once yourself (interactively, on a login node) before
###     submitting the array -- letting N array tasks race to build the
###     venv on first `uv run` is asking for trouble.
###   - `module load python3` below assumes a module of that name exists;
###     check `module avail python3` and adjust the version if needed. uv
###     itself isn't preinstalled on DTU HPC -- `pip install --user uv` (or
###     equivalent) once, so it's on PATH for the array tasks too.
###   - CORES_PER_TASK below is also passed as --jobs to the harness --
###     matches don't benefit from --jobs exceeding allocated cores (see the
###     desktop profiling notes in the plan: --jobs past the physical core
###     count showed no throughput gain).
###   - ARRAY_SIZE x CORES_PER_TASK is your total core footprint on the
###     cluster at once -- check it against your account's fair-share/queue
###     limits before submitting; DTU may queue or reject an array that
###     large.
###
### Submit with: bsub < training/hpc/submit_dtu_lsf.sh
### Monitor with: bstat  /  bjobs -A <jobid>

### -- queue --
#BSUB -q hpc
### -- job name + array size (edit ARRAY_SIZE in two places: here and below) --
#BSUB -J fcl_harness[1-20]
### -- cores per array task (must match CORES_PER_TASK below) --
#BSUB -n 8
### -- keep one task's cores on one host --
#BSUB -R "span[hosts=1]"
### -- memory per core --
#BSUB -R "rusage[mem=2GB]"
#BSUB -M 3GB
### -- walltime per task (hh:mm) -- generous; actual need depends on core count --
#BSUB -W 04:00
#BSUB -o training/hpc/logs/Output_%J_%I.out
#BSUB -e training/hpc/logs/Output_%J_%I.err

set -eu

REPO="$HOME/florent-code-league"       # <-- fill in the actual checkout path
ARRAY_SIZE=20                          # <-- must match the [1-20] above
CORES_PER_TASK=8                       # <-- must match #BSUB -n above
SEEDS="1 2 3 4 5"
EXPLORE_EPS=0.15

cd "$REPO"
mkdir -p training/hpc/logs

module load python3

SHARD_INDEX=$((LSB_JOBINDEX - 1))

uv run python -m training.harness \
    --seeds $SEEDS \
    --explore-eps "$EXPLORE_EPS" \
    --jobs "$CORES_PER_TASK" \
    --shard-count "$ARRAY_SIZE" \
    --shard-index "$SHARD_INDEX" \
    --out "training/runs/shard_${LSB_JOBINDEX}"
