"""RL bot entrypoint.

Talks to a local rl.inference_server over a Unix socket (path from $RL_SOCK) instead
of importing torch directly: the fcode engine runs every unit in its own Python
sub-interpreter within one process, and torch/numpy cannot be imported into more than
one sub-interpreter per process (confirmed by testing -- the second unit's import
segfaults/errors). Only stdlib modules (socket, json) are used here.

When $RL_LOG_DIR is set, appends one JSON line per (unit, round) decision plus a
per-round team signal line (from the CORE instance), so the outer training loop in
rl/self_play.py can reconstruct trajectories and rewards after the match finishes.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fcode import Controller, EntityType

from rl.features import OBS_DIM, RICH_TYPES, encode_observation, apply_action
from rl.map_memory import MapMemory

_SOCK_PATH = os.environ.get("RL_SOCK")
_GREEDY = os.environ.get("RL_GREEDY") == "1"
_LOG_DIR = os.environ.get("RL_LOG_DIR")

_log_files: dict[str, object] = {}


def _query_policy(obs: list[float], entity_type_value: str) -> tuple[int, float, float]:
    if _SOCK_PATH is None:
        return 0, 0.0, 0.0  # no inference server configured: always no-op
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(_SOCK_PATH)
        f = sock.makefile("rwb")
        req = json.dumps({"obs": obs, "entity_type": entity_type_value, "greedy": _GREEDY})
        f.write((req + "\n").encode())
        f.flush()
        resp = json.loads(f.readline())
    return resp["action"], resp["log_prob"], resp["value"]


def _get_log_file(team_value: str):
    if not _LOG_DIR:
        return None
    if team_value not in _log_files:
        Path(_LOG_DIR).mkdir(parents=True, exist_ok=True)
        # Both teams may run this same script within one OS process (self-play
        # mirror matches), so key the file by team + pid, read from ct.get_team()
        # rather than an env var (env vars are shared by both subinterpreters).
        _log_files[team_value] = open(Path(_LOG_DIR) / f"{team_value}.{os.getpid()}.jsonl", "a")
    return _log_files[team_value]


class Player:
    def __init__(self) -> None:
        self._memory: MapMemory | None = None

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype in RICH_TYPES and self._memory is None:
            self._memory = MapMemory()
        obs = encode_observation(ct, self._memory)
        assert len(obs) == OBS_DIM[etype]

        action, log_prob, value = _query_policy(obs, etype.value)
        apply_action(ct, etype, action)

        log_file = _get_log_file(ct.get_team().value)
        if log_file is not None:
            record = {
                "round": ct.get_current_round(),
                "unit_id": ct.get_id(),
                "entity_type": etype.value,
                "obs": obs,
                "action": action,
                "log_prob": log_prob,
                "value": value,
            }
            log_file.write(json.dumps(record) + "\n")
            log_file.flush()

            if etype.value == "core":
                signal = {
                    "round": ct.get_current_round(),
                    "resources": ct.get_global_resources(),
                    "unit_count": ct.get_unit_count(),
                }
                log_file.write(json.dumps({"team_signal": signal}) + "\n")
                log_file.flush()
