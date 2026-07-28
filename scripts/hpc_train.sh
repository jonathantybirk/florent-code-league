#!/bin/sh
### DTU HPC (LSF/bsub) job: self-play RL training for florent-code-league.
### See docs/hpc/HPC-docs.txt for the general cluster reference this is based on.
###
### Submit from the repo root with:  bsub < scripts/hpc_train.sh
### Watch with:   bstat
###
### Note: the game engine itself (fcode_engine, run per match in rl/play_one_game.py)
### is single-threaded CPU simulation -- the GPU only speeds up the PPO backward pass
### in rl/self_play.py's main process. If the policy network stays small, a CPU-only
### queue may train just as fast for less queue wait; swap #BSUB -q below if so.
#BSUB -q gpuv100
#BSUB -J llm-rl-selfplay
#BSUB -n 4
#BSUB -gpu "num=1:mode=exclusive_process"
#BSUB -W 24:00
#BSUB -R "rusage[mem=8GB]"
#BSUB -o llm_rl_%J.out
#BSUB -e llm_rl_%J.err

module load python3/3.13.11
module load cuda/12.6

### bsub runs this script's body piped through stdin, so $0 isn't a real path --
### LSF sets LS_SUBCWD to the directory `bsub` was invoked from instead. Submit
### from the repo root (see above) so this resolves correctly.
cd "$LS_SUBCWD" || exit 1

# This repo is managed with uv (see CLAUDE.md). Install it once per account with:
#   curl -LsSf https://astral.sh/uv/install.sh | sh
command -v uv >/dev/null 2>&1 || { echo "uv not found on PATH -- see comment above"; exit 1; }

uv sync

# wandb logging is opt-in: run `uv run wandb login` once interactively first
# (or export WANDB_API_KEY), then pass WANDB=1 to this job.
WANDB_ARGS=""
if [ "${WANDB:-0}" = "1" ]; then
    WANDB_ARGS="--wandb --wandb-run-name ${LSB_JOBID:-local}"
fi

uv run python3 -m rl.self_play \
    --iterations "${ITERATIONS:-2000}" \
    --opponent "${OPPONENT:-opponent_luc}" \
    --checkpoint checkpoints/policy.pt \
    --save-every 20 \
    $WANDB_ARGS
