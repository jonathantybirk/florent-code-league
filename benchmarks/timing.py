"""Measure per-unit turn CPU time against the ladder's 10 ms limit.

Uses the same technique as `tournament/compliance.py`: wrap the bot's Player,
call the engine's own `get_cpu_time_elapsed()` after each `run()`, and print a
marker. Bot stdout is embedded verbatim in the replay, which is the only
channel that survives, so the markers are read back out of the replay bytes.

    uv run python -m benchmarks.timing --bot bots/luc/ragnarok --maps all

Reports the worst turn per map and per entity type. A unit over 10,000 us is
interrupted mid-`run()` and simply does not act that round.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LIMIT_US = 10_000
START = "FCLTIME_START"
END = "FCLTIME_END"

WRAPPER = f'''"""Generated timing wrapper."""

from _submission import Player as _SubmissionPlayer


class Player(_SubmissionPlayer):
    def run(self, ct):
        round_number = ct.get_current_round()
        entity = ct.get_entity_type().name
        started = ct.get_cpu_time_elapsed()
        print("{START}:%s:%s" % (round_number, entity))
        overhead = ct.get_cpu_time_elapsed() - started
        super().run(ct)
        elapsed = ct.get_cpu_time_elapsed() - overhead
        print("{END}:%s:%s:%s" % (round_number, entity, elapsed))
'''


def stage(bot: Path, into: Path) -> Path:
    into.mkdir(parents=True, exist_ok=True)
    for source in bot.rglob("*"):
        if source.is_file() and "__pycache__" not in source.parts:
            target = into / source.relative_to(bot)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    # The submission's own main.py becomes _submission.py; the wrapper takes
    # its place so the engine loads the instrumented Player.
    (into / "main.py").rename(into / "_submission.py")
    (into / "main.py").write_text(WRAPPER)
    return into / "main.py"


def play(a: Path, b: Path, map_path: Path, replay: Path, seed: int = 1) -> None:
    script = (
        "import sys; sys.path.insert(0, %r)\n"
        "from pathlib import Path\n"
        "import fcode\n"
        "from fcode.fcode_engine import run_game\n"
        "run_game(%r, %r, str(Path(fcode.__file__).resolve().parent), %r, %r, %d, 0)\n"
    ) % (str(REPO), str(a), str(b), str(map_path), str(replay), seed)
    subprocess.run([sys.executable, "-c", script], cwd=REPO,
                   capture_output=True, timeout=900)


def samples(replay: Path) -> list[tuple[int, str, int]]:
    payload = replay.read_bytes()
    pattern = re.escape(END.encode()) + rb":(\d+):([A-Z_]+):(\d+)"
    return [(int(r), kind.decode(), int(us))
            for r, kind, us in re.findall(pattern, payload)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot", required=True, type=Path)
    parser.add_argument("--opponent", type=Path,
                        default=REPO / "bots/luc/vigil")
    parser.add_argument("--maps", default="quarry,hive,aurora,longship,twins")
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args()

    maps = ([p.stem for p in sorted((REPO / "maps").glob("*.map26"))]
            if args.maps == "all" else args.maps.split(","))

    work = Path(tempfile.mkdtemp(prefix="fcl-timing-"))
    try:
        subject = stage(args.bot, work / "subject")
        opponent = args.opponent / "main.py"

        per_map: dict[str, list[tuple[int, str, int]]] = {}
        for name in maps:
            replay = work / f"{name}.replay26"
            play(subject, opponent, REPO / "maps" / f"{name}.map26", replay)
            per_map[name] = samples(replay) if replay.exists() else []
            replay.unlink(missing_ok=True)

        by_kind: dict[str, list[int]] = defaultdict(list)
        rows = []
        for name, data in per_map.items():
            if not data:
                rows.append((0, name, 0, "-", 0, 0))
                continue
            worst = max(data, key=lambda s: s[2])
            over = sum(1 for s in data if s[2] > LIMIT_US)
            rows.append((worst[2], name, worst[0], worst[1], over, len(data)))
            for _, kind, us in data:
                by_kind[kind].append(us)

        print(f"{'map':12s} {'worst_us':>9s} {'round':>6s} {'unit':>12s} "
              f"{'over_10ms':>10s} {'turns':>7s}")
        for worst, name, round_, kind, over, total in sorted(rows, reverse=True):
            flag = "  <-- OVER" if worst > LIMIT_US else ""
            print(f"{name:12s} {worst:9d} {round_:6d} {kind:>12s} "
                  f"{over:10d} {total:7d}{flag}")

        print("\nby unit type:")
        for kind, values in sorted(by_kind.items(),
                                   key=lambda kv: -max(kv[1])):
            values.sort()
            p50 = values[len(values) // 2]
            p99 = values[min(len(values) - 1, int(len(values) * 0.99))]
            print(f"  {kind:14s} n={len(values):6d} p50={p50:6d} "
                  f"p99={p99:7d} max={values[-1]:7d}")
        total_over = sum(row[4] for row in rows)
        print(f"\ntotal turns over {LIMIT_US} us: {total_over}")
        return 1 if total_over else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
