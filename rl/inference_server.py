"""Local inference server: loads the torch policy once and answers action requests
over a Unix domain socket.

Why this exists: the fcode engine runs every unit's bot code in its own Python
sub-interpreter within one OS process (see fcode/_types.py's Controller comment).
Neither torch nor numpy support being imported into more than one sub-interpreter per
process -- the second unit's import crashes ("cannot load module more than once per
process" / a segfault for torch). So the bot script (bots/rl/main.py) cannot import
torch directly. Instead, one persistent process loads the model normally and the bot
just sends its observation over a socket -- plain `socket`/`json` are core-CPython
modules and don't have this problem.

Protocol: newline-delimited JSON, one request per connection.
  request:  {"obs": [...], "entity_type": "builder_bot", "greedy": false}
  response: {"action": 3, "log_prob": -1.2, "value": 0.4}
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
from pathlib import Path

import torch

from fcode import EntityType

from rl.policy import load_checkpoint, new_policy

ENTITY_TYPE_BY_VALUE = {t.value: t for t in EntityType}


def serve(checkpoint: str | None, socket_path: str, stop_event: threading.Event | None = None) -> None:
    if checkpoint and Path(checkpoint).exists():
        policy = load_checkpoint(checkpoint)
    else:
        policy = new_policy()
    policy.eval()

    sock_path = Path(socket_path)
    if sock_path.exists():
        sock_path.unlink()
    sock_path.parent.mkdir(parents=True, exist_ok=True)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(64)
    server.settimeout(1.0)
    print(f"[inference_server] listening on {sock_path}", flush=True)

    try:
        while stop_event is None or not stop_event.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            with conn:
                f = conn.makefile("rwb")
                line = f.readline()
                if not line:
                    continue
                req = json.loads(line)
                obs = torch.tensor(req["obs"], dtype=torch.float32)
                etype = ENTITY_TYPE_BY_VALUE[req["entity_type"]]
                action, log_prob, value = policy.act(obs, etype, greedy=req.get("greedy", False))
                resp = json.dumps({"action": action, "log_prob": log_prob, "value": value})
                f.write((resp + "\n").encode())
                f.flush()
    finally:
        server.close()
        if sock_path.exists():
            sock_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--socket", required=True)
    args = parser.parse_args()
    serve(args.checkpoint, args.socket)


if __name__ == "__main__":
    main()
