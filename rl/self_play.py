"""Self-play / vs-scripted-opponent training loop.

Each iteration: save the current policy to a checkpoint file, start a local inference
server (rl/inference_server.py) that the bot processes query over a socket, play one
match via rl/play_one_game.py (a subprocess -- see that module's docstring for why it
isn't called in-process), read back the trajectories the bot logged to disk, turn them
into a reward signal, and run a PPO update.

Reward design (OpenAI-Five-inspired dense shaping rather than AlphaZero-style
terminal-only reward, since a single game can run up to 1000 rounds and credit
assignment over sparse terminal reward alone is slow to bootstrap this way):
  - every round: small reward from the team's own titanium/unit-count deltas
  - final round: a large terminal bonus for win/loss/draw
The same per-round reward is given to every unit that acted that round -- a common
shared-team-reward simplification, not per-agent credit assignment.

Usage:
    uv run python -m rl.self_play --iterations 200 --opponent opponent_luc
    uv run python -m rl.self_play --iterations 200 --opponent self   # mirror self-play
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import torch

from fcode import EntityType
from rl.policy import new_policy, load_checkpoint, save_checkpoint
from rl.ppo import Step, Trajectory, ppo_update

REPO_ROOT = Path(__file__).resolve().parent.parent
BOTS_DIR = REPO_ROOT / "bots"
MAPS_DIR = REPO_ROOT / "maps"
CHECKPOINTS_DIR = REPO_ROOT / "checkpoints"
RUNS_DIR = REPO_ROOT / "runs"

RL_BOT_MAIN = str(BOTS_DIR / "rl" / "main.py")
OPPONENT_MAIN = str(BOTS_DIR / "opponent_luc" / "main.py")
SOCKET_PATH = str(RUNS_DIR / "inference.sock")

TERMINAL_REWARD = 5.0
RESOURCE_REWARD_SCALE = 1.0 / 200.0
UNIT_REWARD_SCALE = 1.0 / 10.0
ENTITY_TYPE_BY_VALUE = {t.value: t for t in EntityType}


def _read_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _team_round_rewards(team_signals: list[dict], won: bool | None, max_round: int) -> dict[int, float]:
    """won: True/False/None (draw). Returns {round: reward}."""
    team_signals = sorted(team_signals, key=lambda s: s["round"])
    rewards: dict[int, float] = {}
    prev_resources = None
    prev_units = None
    for sig in team_signals:
        r = sig["round"]
        reward = 0.0
        if prev_resources is not None:
            reward += RESOURCE_REWARD_SCALE * max(sig["resources"] - prev_resources, 0)
            reward += UNIT_REWARD_SCALE * (sig["unit_count"] - prev_units)
        prev_resources = sig["resources"]
        prev_units = sig["unit_count"]
        rewards[r] = reward

    if won is True:
        rewards[max_round] = rewards.get(max_round, 0.0) + TERMINAL_REWARD
    elif won is False:
        rewards[max_round] = rewards.get(max_round, 0.0) - TERMINAL_REWARD
    return rewards


def _build_trajectories(log_dir: Path, team_value: str, won: bool | None) -> list[Trajectory]:
    files = list(log_dir.glob(f"{team_value}.*.jsonl"))
    if not files:
        return []

    unit_records: dict[int, list[dict]] = {}
    team_signals: list[dict] = []
    max_round = 0
    for path in files:
        for rec in _read_jsonl(path):
            if "team_signal" in rec:
                team_signals.append(rec["team_signal"])
                continue
            unit_records.setdefault(rec["unit_id"], []).append(rec)
            max_round = max(max_round, rec["round"])

    reward_by_round = _team_round_rewards(team_signals, won, max_round)

    trajectories = []
    for records in unit_records.values():
        records.sort(key=lambda r: r["round"])
        etype = ENTITY_TYPE_BY_VALUE[records[0]["entity_type"]]
        steps = [
            Step(
                obs=r["obs"],
                action=r["action"],
                log_prob=r["log_prob"],
                value=r["value"],
                reward=reward_by_round.get(r["round"], 0.0),
            )
            for r in records
        ]
        trajectories.append(Trajectory(entity_type=etype, steps=steps))
    return trajectories


def _start_inference_server(checkpoint_path: Path) -> subprocess.Popen:
    sock_path = Path(SOCKET_PATH)
    if sock_path.exists():
        sock_path.unlink()
    proc = subprocess.Popen(
        [sys.executable, "-m", "rl.inference_server", "--checkpoint", str(checkpoint_path), "--socket", SOCKET_PATH],
        cwd=REPO_ROOT,
    )
    for _ in range(100):  # up to ~10s for the socket file to appear
        if sock_path.exists():
            return proc
        time.sleep(0.1)
    proc.kill()
    raise RuntimeError("inference server did not start (socket file never appeared)")


def _run_match(worker_id: int, opponent_main: str, seed: int | None) -> dict:
    """Play one match in its own log dir/replay path so it can run alongside sibling
    workers without clobbering their files. All workers query the same inference
    server (already handling connections concurrently -- see inference_server.py)."""
    maps = sorted(MAPS_DIR.glob("*.map26"))
    map_path = str(random.choice(maps))

    log_dir = RUNS_DIR / "game_logs" / f"worker{worker_id}"
    if log_dir.exists():
        shutil.rmtree(log_dir)
    log_dir.mkdir(parents=True)

    replays_dir = RUNS_DIR / "replays"
    replays_dir.mkdir(parents=True, exist_ok=True)
    replay_path = str(replays_dir / f"latest_worker{worker_id}.replay26")

    env = os.environ.copy()
    env["RL_SOCK"] = SOCKET_PATH
    env["RL_LOG_DIR"] = str(log_dir)
    env["RL_GREEDY"] = "0"

    match_seed = None if seed is None else seed + worker_id
    seed_args = ["--seed", str(match_seed)] if match_seed is not None else []
    proc = subprocess.run(
        [sys.executable, "-m", "rl.play_one_game", RL_BOT_MAIN, opponent_main, map_path, replay_path, *seed_args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"play_one_game (worker {worker_id}) failed:\n{proc.stderr}")
    result = json.loads(proc.stdout.strip().splitlines()[-1])

    won = None
    if result["winner"] == "A":
        won = True
    elif result["winner"] == "B":
        won = False

    trajectories = _build_trajectories(log_dir, "a", won)
    return {"result": result, "trajectories": trajectories, "replay_path": replay_path}


def run_iteration(policy_path: Path, opponent_main: str, seed: int | None, n_workers: int) -> dict:
    """Play n_workers matches concurrently against the same frozen checkpoint, then
    return their pooled results/trajectories for a single batched PPO update."""
    server = _start_inference_server(policy_path)
    try:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            # subprocess.run releases the GIL while waiting on the child, so these
            # threads genuinely run the n_workers matches in parallel.
            outs = list(pool.map(lambda w: _run_match(w, opponent_main, seed), range(n_workers)))
    finally:
        server.terminate()
        server.wait(timeout=5)

    return {
        "results": [o["result"] for o in outs],
        "trajectories": [t for o in outs for t in o["trajectories"]],
        "replay_paths": [o["replay_path"] for o in outs],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--opponent", default="opponent_luc", help="'opponent_luc' or 'self' (mirror self-play)")
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--checkpoint", default=str(CHECKPOINTS_DIR / "policy.pt"))
    parser.add_argument("--save-every", type=int, default=10)
    # LSB_DJOB_NUMPROC (set by LSF to the job's actual allocated core count) takes
    # priority over os.cpu_count(), which reports the whole node rather than our slice.
    default_parallel = int(os.environ.get("LSB_DJOB_NUMPROC", 0)) or max(1, (os.cpu_count() or 1) - 1)
    parser.add_argument(
        "--parallel",
        type=int,
        default=default_parallel,
        help="matches to play concurrently per iteration (one PPO update per batch of these)",
    )
    parser.add_argument("--wandb", action="store_true", help="log metrics to Weights & Biases")
    parser.add_argument("--wandb-project", default="florent-code-league-rl")
    parser.add_argument("--wandb-run-name", default=None)
    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint)
    if checkpoint_path.exists():
        policy = load_checkpoint(checkpoint_path)
        print(f"Resumed policy from {checkpoint_path}")
    else:
        policy = new_policy()
        print("Starting from a fresh random-init policy")

    optimizer = torch.optim.Adam(policy.parameters(), lr=args.lr)
    opponent_main = RL_BOT_MAIN if args.opponent == "self" else OPPONENT_MAIN

    run = None
    if args.wandb:
        import wandb

        run = wandb.init(project=args.wandb_project, name=args.wandb_run_name, config=vars(args))

    RUNS_DIR.mkdir(exist_ok=True)
    save_checkpoint(policy, checkpoint_path)

    print(f"Playing {args.parallel} matches per iteration in parallel")

    wins = losses = draws = 0
    total_matches = 0
    for i in range(1, args.iterations + 1):
        t0 = time.time()
        save_checkpoint(policy, checkpoint_path)  # bot processes load from disk

        out = run_iteration(checkpoint_path, opponent_main, args.seed, args.parallel)
        results, trajectories, replay_paths = out["results"], out["trajectories"], out["replay_paths"]

        batch_wins = sum(1 for r in results if r["winner"] == "A")
        batch_losses = sum(1 for r in results if r["winner"] == "B")
        batch_draws = len(results) - batch_wins - batch_losses
        wins += batch_wins
        losses += batch_losses
        draws += batch_draws
        total_matches += len(results)

        ppo_stats = ppo_update(policy, optimizer, trajectories) if trajectories else {}

        dt = time.time() - t0
        avg_turns = sum(r["turns"] for r in results) / len(results)
        print(
            f"[{i}/{args.iterations}] matches={len(results)} avg_turns={avg_turns:.0f} "
            f"batch(W/L/D)={batch_wins}/{batch_losses}/{batch_draws} "
            f"record(W/L/D)={wins}/{losses}/{draws} ({dt:.1f}s, {dt / len(results):.1f}s/match)"
        )

        if run is not None:
            log = {
                "match/win_rate_batch": batch_wins / len(results),
                "match/avg_turns": avg_turns,
                "match/avg_a_titanium": sum(r["a_titanium"] for r in results) / len(results),
                "match/avg_b_titanium": sum(r["b_titanium"] for r in results) / len(results),
                "match/avg_a_units": sum(r["a_units"] for r in results) / len(results),
                "match/avg_b_units": sum(r["b_units"] for r in results) / len(results),
                "match/matches_per_iteration": len(results),
                "match/seconds_per_iteration": dt,
                "match/seconds_per_match": dt / len(results),
                "record/wins": wins,
                "record/losses": losses,
                "record/draws": draws,
                "record/win_rate": wins / total_matches,
            }
            for etype_value, s in ppo_stats.items():
                for k, v in s.items():
                    log[f"ppo/{etype_value}/{k}"] = v
            wandb.log(log, step=i)

        if i % args.save_every == 0:
            archive_path = CHECKPOINTS_DIR / f"policy_iter{i}.pt"
            save_checkpoint(policy, archive_path)
            # Archive one replay from this batch so training progress can be watched
            # later with `fcode watch` -- runs/replays/latest_worker*.replay26 only
            # ever holds the most recent batch.
            archive_replay_dir = RUNS_DIR / "replays" / "archive"
            archive_replay_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(replay_paths[0], archive_replay_dir / f"iter{i}.replay26")

    save_checkpoint(policy, checkpoint_path)
    if run is not None:
        run.finish()


if __name__ == "__main__":
    main()
