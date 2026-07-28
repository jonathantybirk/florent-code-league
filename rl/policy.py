"""Actor-critic policy: one independent network per entity type, not a shared trunk.

Each unit type's decision complexity is wildly different -- Builder Bot has 34
actions and needs map-memory context, Gunner/Sentinel/Launcher have 1-4 actions and
just react to engine-provided targeting helpers. A shared trunk would force every
type through the same width, wasting budget on the simple types or starving the
complex one. Instead each type gets its own (obs_dim -> hidden1 -> hidden2 ->
heads) net, sized in HIDDEN_DIMS below so the *exported pure-Python* forward pass
(see rl/export_pure_python.py) stays well under the ladder's 10ms-per-unit budget
even after adding the Builder Bot's map-memory bookkeeping cost on top.
"""

from __future__ import annotations

from pathlib import Path

import torch
from torch import nn
from torch.distributions import Categorical

from fcode import EntityType

from rl.features import NUM_ACTIONS, OBS_DIM

# (hidden1, hidden2) per type. Builder Bot is the only type with a large obs (839
# dims from map memory + comms); its hidden dims are kept modest specifically to
# offset that, rather than compounding it -- see the docstring above.
HIDDEN_DIMS = {
    EntityType.CORE: (48, 24),
    EntityType.BUILDER_BOT: (96, 48),
    EntityType.GUNNER: (16, 8),
    EntityType.SENTINEL: (16, 8),
    EntityType.LAUNCHER: (8, 8),
}


def _key(etype: EntityType) -> str:
    return etype.value


class _TypeNet(nn.Module):
    def __init__(self, obs_dim: int, hidden1: int, hidden2: int, num_actions: int):
        super().__init__()
        self.body = nn.Sequential(
            nn.Linear(obs_dim, hidden1),
            nn.ReLU(),
            nn.Linear(hidden1, hidden2),
            nn.ReLU(),
        )
        self.actor = nn.Linear(hidden2, num_actions)
        self.critic = nn.Linear(hidden2, 1)

    def forward(self, obs: torch.Tensor):
        features = self.body(obs)
        return self.actor(features), self.critic(features).squeeze(-1)


class PolicyNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.nets = nn.ModuleDict(
            {
                _key(t): _TypeNet(OBS_DIM[t], *HIDDEN_DIMS[t], NUM_ACTIONS[t])
                for t in NUM_ACTIONS
            }
        )

    def forward(self, obs: torch.Tensor, entity_type: EntityType):
        return self.nets[_key(entity_type)](obs)

    @torch.no_grad()
    def act(self, obs: torch.Tensor, entity_type: EntityType, greedy: bool = False):
        """obs: 1D tensor of shape (OBS_DIM[entity_type],). Returns (action, log_prob, value)."""
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
