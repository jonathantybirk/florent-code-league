"""Run one benchmark match in this process and write a metrics JSON.

One match per OS process (engine runs bots in sub-interpreters in-process;
see tournament/run_match.py). Stdlib + fcode only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks import metrics as metrics_mod  # noqa: E402
from benchmarks import replay as replay_mod  # noqa: E402


def engine_root() -> str:
    import fcode

    return str(Path(fcode.__file__).resolve().parent)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True, help="path to bot A entry .py")
    parser.add_argument("--b", required=True, help="path to bot B entry .py")
    parser.add_argument("--map", required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--tle", type=int, default=0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--keep-replay", default=None)
    args = parser.parse_args()

    record: dict = {
        "a": args.a,
        "b": args.b,
        "map": Path(args.map).stem,
        "seed": args.seed,
    }
    replay_dir = tempfile.mkdtemp(prefix="bench-replay-")
    replay_path = args.keep_replay or os.path.join(replay_dir, "match.replay26")

    started = time.time()
    try:
        from fcode.fcode_engine import run_game

        result = run_game(
            str(Path(args.a).resolve()),
            str(Path(args.b).resolve()),
            engine_root(),
            str(Path(args.map).resolve()),
            replay_path,
            args.seed,
            args.tle,
        )
        record["status"] = "ok"
        record["engine"] = {
            key: result.get(key)
            for key in (
                "winner", "win_condition", "turns", "resign_message",
                "a_titanium", "a_titanium_collected", "a_units", "a_buildings",
                "b_titanium", "b_titanium_collected", "b_units", "b_buildings",
            )
        }
        decoded = replay_mod.decode(replay_path)
        record["metrics"] = metrics_mod.compute(decoded)
    except BaseException as error:  # noqa: BLE001 - record, never crash the suite
        record["status"] = "error"
        record["error"] = f"{type(error).__name__}: {error}"
        traceback.print_exc()
    finally:
        record["duration_s"] = round(time.time() - started, 3)
        if not args.keep_replay:
            try:
                os.unlink(replay_path)
            except OSError:
                pass
            try:
                os.rmdir(replay_dir)
            except OSError:
                pass

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(record) + "\n")
    os.replace(tmp, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
