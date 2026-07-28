"""Minimal clipped-PPO update, trained separately per entity type since each has its
own action space and head (see rl/policy.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import torch
from torch.distributions import Categorical

from fcode import EntityType

from rl.policy import PolicyNet

GAMMA = 0.99
GAE_LAMBDA = 0.95
CLIP_EPS = 0.2
VALUE_COEF = 0.5
ENTROPY_COEF = 0.01
EPOCHS_PER_UPDATE = 4
MINIBATCH_SIZE = 256


@dataclass
class Step:
    obs: list[float]
    action: int
    log_prob: float
    value: float
    reward: float = 0.0


@dataclass
class Trajectory:
    entity_type: EntityType
    steps: list[Step] = field(default_factory=list)


def compute_gae(steps: list[Step]) -> tuple[list[float], list[float]]:
    """Return (advantages, returns) for one unit's ordered sequence of steps."""
    advantages = [0.0] * len(steps)
    gae = 0.0
    next_value = 0.0
    for t in reversed(range(len(steps))):
        delta = steps[t].reward + GAMMA * next_value - steps[t].value
        gae = delta + GAMMA * GAE_LAMBDA * gae
        advantages[t] = gae
        next_value = steps[t].value
    returns = [advantages[i] + steps[i].value for i in range(len(steps))]
    return advantages, returns


def ppo_update(policy: PolicyNet, optimizer: torch.optim.Optimizer, trajectories: list[Trajectory]) -> dict:
    """Run a few epochs of clipped PPO over all trajectories, grouped by entity type."""
    by_type: dict[EntityType, list[tuple]] = {}
    for traj in trajectories:
        advantages, returns = compute_gae(traj.steps)
        adv_mean = sum(advantages) / max(len(advantages), 1)
        adv_std = (sum((a - adv_mean) ** 2 for a in advantages) / max(len(advantages), 1)) ** 0.5 + 1e-8
        for step, adv, ret in zip(traj.steps, advantages, returns):
            norm_adv = (adv - adv_mean) / adv_std
            by_type.setdefault(traj.entity_type, []).append((step, norm_adv, ret))

    stats = {}
    for etype, samples in by_type.items():
        obs = torch.tensor([s[0].obs for s in samples], dtype=torch.float32)
        actions = torch.tensor([s[0].action for s in samples], dtype=torch.long)
        old_log_probs = torch.tensor([s[0].log_prob for s in samples], dtype=torch.float32)
        advantages = torch.tensor([s[1] for s in samples], dtype=torch.float32)
        returns = torch.tensor([s[2] for s in samples], dtype=torch.float32)

        n = obs.shape[0]
        policy_losses, value_losses, entropies = [], [], []
        for _ in range(EPOCHS_PER_UPDATE):
            perm = torch.randperm(n)
            for start in range(0, n, MINIBATCH_SIZE):
                idx = perm[start : start + MINIBATCH_SIZE]
                logits, values = policy.forward(obs[idx], etype)
                dist = Categorical(logits=logits)
                new_log_probs = dist.log_prob(actions[idx])
                ratio = (new_log_probs - old_log_probs[idx]).exp()

                surr1 = ratio * advantages[idx]
                surr2 = ratio.clamp(1 - CLIP_EPS, 1 + CLIP_EPS) * advantages[idx]
                policy_loss = -torch.min(surr1, surr2).mean()
                value_loss = (returns[idx] - values).pow(2).mean()
                entropy = dist.entropy().mean()

                loss = policy_loss + VALUE_COEF * value_loss - ENTROPY_COEF * entropy

                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
                optimizer.step()

                policy_losses.append(policy_loss.item())
                value_losses.append(value_loss.item())
                entropies.append(entropy.item())

        stats[etype.value] = {
            "n_samples": n,
            "policy_loss": sum(policy_losses) / len(policy_losses),
            "value_loss": sum(value_losses) / len(value_losses),
            "entropy": sum(entropies) / len(entropies),
            "mean_return": returns.mean().item(),
        }
    return stats
