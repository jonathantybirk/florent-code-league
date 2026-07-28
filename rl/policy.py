"""Actor-critic policy: a shared trunk with a small actor+critic head per entity type.

Action spaces differ per entity type (see rl/features.py), so each type gets its own
head, but they all share the trunk so learning about map/unit context transfers across
roles -- similar in spirit to how OpenAI Five shares an LSTM torso across heroes.
"""

from __future__ import annotations

from pathlib import Path

import torch
from torch import nn
from torch.distributions import Categorical

from fcode import EntityType

from rl.features import ENTITY_TYPES, NUM_ACTIONS, OBS_DIM

HIDDEN_DIM = 256
TRUNK_OUT_DIM = 128


def _key(etype: EntityType) -> str:
    return etype.value


class PolicyNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(OBS_DIM, HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(HIDDEN_DIM, TRUNK_OUT_DIM),
            nn.ReLU(),
        )
        self.actor_heads = nn.ModuleDict(
            {_key(t): nn.Linear(TRUNK_OUT_DIM, NUM_ACTIONS[t]) for t in ENTITY_TYPES}
        )
        self.critic_heads = nn.ModuleDict(
            {_key(t): nn.Linear(TRUNK_OUT_DIM, 1) for t in ENTITY_TYPES}
        )

    def forward(self, obs: torch.Tensor, entity_type: EntityType):
        features = self.trunk(obs)
        logits = self.actor_heads[_key(entity_type)](features)
        value = self.critic_heads[_key(entity_type)](features).squeeze(-1)
        return logits, value

    @torch.no_grad()
    def act(self, obs: torch.Tensor, entity_type: EntityType, greedy: bool = False):
        """obs: 1D tensor of shape (OBS_DIM,). Returns (action, log_prob, value) as python scalars."""
        logits, value = self.forward(obs.unsqueeze(0), entity_type)
        dist = Categorical(logits=logits)
        action = logits.argmax(dim=-1) if greedy else dist.sample()
        log_prob = dist.log_prob(action)
        return int(action.item()), float(log_prob.item()), float(value.item())


def new_policy() -> PolicyNet:
    return PolicyNet()


def save_checkpoint(policy: PolicyNet, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(policy.state_dict(), tmp)
    tmp.replace(path)


def load_checkpoint(path: str | Path, map_location: str = "cpu") -> PolicyNet:
    policy = new_policy()
    state = torch.load(path, map_location=map_location)
    policy.load_state_dict(state)
    return policy
