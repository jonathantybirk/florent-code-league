"""Fan a batch of matches out over K one-shot workers and collect the JSONL back.

The one non-obvious requirement: the bot's sub-interpreter resolves `import fcode`
from PYTHONPATH / site-packages, *not* from the parent process's runtime sys.path.
A worker launched without PYTHONPATH set will happily start and then fail every
match. `worker_env()` sets it explicitly.

The other invariant: a worker that dies or times out must never silently shrink
the sample. Every match id handed to a worker comes back, either as a real result
or as a `crashed: True` record that the scorer treats as a loss.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Sequence

from arena import REPO_ROOT, physical_cores, site_packages_dir

WORKER_PY = str(Path(__file__).resolve().parent / "worker.py")

#: Generous per-match budget. Observed cost is 1.0-4.8 s/match on 1000-turn games;
#: this only has to catch a genuinely wedged worker, not police slow maps.
DEFAULT_PER_MATCH_TIMEOUT = 60.0
#: Interpreter start + engine extension load + spec read.
DEFAULT_STARTUP_TIMEOUT = 60.0


def worker_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a worker: PYTHONPATH carries site-packages and the repo root."""
    env = dict(os.environ)
    parts: list[str] = []
    sp = site_packages_dir()
    if sp:
        parts.append(sp)
    parts.append(str(REPO_ROOT))
    existing = env.get("PYTHONPATH")
    if existing:
        parts.append(existing)
    seen: set[str] = set()
    ordered = []
    for p in parts:
        key = os.path.normcase(p)
        if key not in seen:
            seen.add(key)
            ordered.append(p)
    env["PYTHONPATH"] = os.pathsep.join(ordered)
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")  # never leave __pycache__ near a bot
    if extra:
        env.update(extra)
    return env


def _crashed_record(spec: dict, reason: str) -> dict:
    return {
        "id": spec.get("id"),
        "a": spec.get("a"),
        "b": spec.get("b"),
        "map": spec.get("map"),
        "seed": spec.get("seed"),
        "ok": False,
        "crashed": True,
        "error": reason,
        "winner": None,
        "turns": 0,
        "win_condition": "crashed",
        "resign_message": None,
        "a_titanium": 0,
        "a_titanium_collected": 0,
        "a_units": 0,
        "a_buildings": 0,
        "b_titanium": 0,
        "b_titanium_collected": 0,
        "b_units": 0,
        "b_buildings": 0,
        "elapsed": 0.0,
        "replay": spec.get("replay"),
        "a_exceptions": 0,
        "b_exceptions": 0,
        "unknown_exceptions": 0,
        "exceptions_by_dir": {},
        "traceback_samples": [],
        "replay_traceback_hits": 0,
    }


def _chunk_round_robin(items: Sequence[dict], k: int) -> list[list[dict]]:
    """Deal matches like cards.

    Map cost varies 5x (fjord ~4.8 s, duel ~1.0 s). Contiguous slicing would put
    all the expensive maps on one worker and leave the rest idle; dealing spreads
    them, which is what makes wall time track the mean instead of the max.
    """
    chunks: list[list[dict]] = [[] for _ in range(k)]
    for i, it in enumerate(items):
        chunks[i % k].append(it)
    return [c for c in chunks if c]


class _Worker:
    def __init__(self, chunk: list[dict], python: str, env: dict[str, str], tmpdir: Path, idx: int):
        self.chunk = chunk
        self.idx = idx
        self.spec_path = tmpdir / f"spec_{idx}.json"
        self.err_path = tmpdir / f"err_{idx}.txt"
        self.lines: list[str] = []
        self.spec_path.write_text(
            json.dumps({"matches": chunk, "capture_file": str(tmpdir / f"cap_{idx}.txt")}),
            encoding="utf-8",
        )
        self._err_fh = open(self.err_path, "wb")
        self.proc = subprocess.Popen(
            [python, WORKER_PY, str(self.spec_path)],
            stdout=subprocess.PIPE,
            stderr=self._err_fh,
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=str(REPO_ROOT),
        )
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for raw in self.proc.stdout:
            text = raw.decode("utf-8", "replace").strip()
            if text:
                self.lines.append(text)
        try:
            self.proc.stdout.close()
        except OSError:
            pass

    def collect(self, deadline: float) -> tuple[list[dict], str | None]:
        remaining = max(0.0, deadline - time.monotonic())
        self.thread.join(remaining)
        timed_out = self.thread.is_alive()
        if timed_out:
            self.proc.kill()
            self.thread.join(10.0)
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self._err_fh.close()

        results: list[dict] = []
        for line in self.lines:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        reason: str | None = None
        if timed_out:
            reason = f"worker {self.idx} timed out"
        elif self.proc.returncode not in (0, None) and len(results) < len(self.chunk):
            tail = ""
            try:
                tail = self.err_path.read_text(encoding="utf-8", errors="replace")[-800:]
            except OSError:
                pass
            reason = f"worker {self.idx} exited rc={self.proc.returncode}: {tail.strip()}"
        elif len(results) < len(self.chunk):
            reason = f"worker {self.idx} produced {len(results)}/{len(self.chunk)} results"
        return results, reason


def run_matches(
    matches: Iterable[dict],
    workers: int | None = None,
    python: str | None = None,
    per_match_timeout: float = DEFAULT_PER_MATCH_TIMEOUT,
    startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[list[dict], dict]:
    """Run every match and return `(results_in_input_order, stats)`.

    `matches` items need `a`, `b`, `map`; optional `seed` (1), `replay` (None),
    `capture` (True), `tle` (0). An `id` is assigned here and used to reassemble
    order, so callers must not set it.

    Never raises for a bot-side or worker-side failure: those come back as
    records with `crashed: True`.
    """
    specs: list[dict] = []
    for i, m in enumerate(matches):
        spec = dict(m)
        spec["id"] = i
        spec.setdefault("seed", 1)
        spec.setdefault("replay", None)
        spec.setdefault("capture", True)
        spec.setdefault("tle", 0)
        specs.append(spec)

    stats = {
        "matches": len(specs),
        "workers": 0,
        "wall_seconds": 0.0,
        "matches_per_sec": 0.0,
        "matches_per_hour": 0.0,
        "crashed": 0,
        "worker_failures": [],
    }
    if not specs:
        return [], stats

    k = workers or physical_cores()
    k = max(1, min(k, len(specs)))
    stats["workers"] = k
    py = python or sys.executable
    env = worker_env()
    by_id: dict[int, dict] = {}
    failures: list[str] = []

    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="arena_") as td:
        tmpdir = Path(td)
        chunks = _chunk_round_robin(specs, k)
        pool = [_Worker(chunk, py, env, tmpdir, i) for i, chunk in enumerate(chunks)]
        deadlines = [
            time.monotonic() + startup_timeout + per_match_timeout * len(w.chunk) for w in pool
        ]
        done = 0
        for w, deadline in zip(pool, deadlines):
            results, reason = w.collect(deadline)
            if reason:
                failures.append(reason)
            for r in results:
                by_id[r["id"]] = r
            for spec in w.chunk:
                if spec["id"] not in by_id:
                    by_id[spec["id"]] = _crashed_record(spec, reason or "no result from worker")
            done += len(w.chunk)
            if progress:
                progress(done, len(specs))
    wall = time.perf_counter() - t0

    ordered = [by_id[s["id"]] for s in specs]
    stats["wall_seconds"] = wall
    stats["matches_per_sec"] = len(specs) / wall if wall > 0 else 0.0
    stats["matches_per_hour"] = stats["matches_per_sec"] * 3600.0
    stats["crashed"] = sum(1 for r in ordered if r.get("crashed"))
    stats["worker_failures"] = failures
    return ordered, stats


def _cli(argv: list[str]) -> int:
    import argparse

    from arena import ALL_MAPS, resolve_bot, resolve_map

    ap = argparse.ArgumentParser(description="Run a raw batch of matches (no mirroring).")
    ap.add_argument("bot_a")
    ap.add_argument("bot_b")
    ap.add_argument("--maps", nargs="*", default=list(ALL_MAPS))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args(argv)

    a = str(resolve_bot(args.bot_a))
    b = str(resolve_bot(args.bot_b))
    matches = [{"a": a, "b": b, "map": str(resolve_map(m)), "seed": args.seed} for m in args.maps]
    results, stats = run_matches(matches, workers=args.workers)
    for r in results:
        print(
            f"{Path(r['map']).stem:<12} winner={r['winner']!s:<5} "
            f"{r['win_condition']:<20} turns={r['turns']:<5} "
            f"crashed={r['crashed']} exc(a/b)={r['a_exceptions']}/{r['b_exceptions']}"
        )
    print(
        f"\n{stats['matches']} matches on {stats['workers']} workers in "
        f"{stats['wall_seconds']:.2f}s -> {stats['matches_per_sec']:.2f} matches/sec"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
