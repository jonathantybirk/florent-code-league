"""One-shot arena worker: run a batch of matches in-process, emit one JSON line each.

Contract
--------
    python arena/worker.py <spec.json>      # spec read from a file
    python arena/worker.py -                # spec read from stdin

The spec is::

    {"matches": [{"id": 0,
                  "a": "<abs path to bot A main.py>",
                  "b": "<abs path to bot B main.py>",
                  "map": "<abs path to .map26>",
                  "seed": 1,
                  "replay": null | "<abs path>",   # null => os.devnull, replay I/O is pure cost
                  "capture": true,                 # capture engine stdout/stderr for crash scan
                  "tle": 0},
                 ...]}

Exactly one JSON line is written to the *real* stdout per match, in spec order,
and the process ends with `os._exit(0)`.

Why this file is standalone (no `from arena import ...`): the runner may launch it
with a bare interpreter, and importing the package would be one more failure mode
between us and a clean JSONL stream.

Two hard engine behaviours this file exists to handle
-----------------------------------------------------
1. The engine writes "Completed turn N" progress lines and full Python tracebacks
   straight to file descriptors 1 and 2. `contextlib.redirect_stdout` cannot stop
   that -- it only rebinds `sys.stdout`. So we dup the real stdout away and keep
   fd 1 pointed somewhere harmless for the whole run.
2. `Py_Finalize` aborts with "remaining subinterpreters" after run_game, so the
   process must leave via `os._exit(0)` and never fall off the end of main().
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback

TRACEBACK_MARKERS = (
    b"Traceback (most recent call last)",
    b"fcode._types.GameError",
    b"GameError:",
)

_TB_HEADER = "Traceback (most recent call last):"
_FILE_LINE = re.compile(r'^\s+File "(?P<path>.*?)", line (?P<line>\d+), in (?P<func>.*)$')


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _split_tracebacks(text: str) -> list[str]:
    """Split captured engine output into individual traceback blocks.

    A block runs from a 'Traceback (most recent call last):' header up to and
    including the first following line that starts at column 0 (the exception
    line). Anything else in the stream (progress chatter) is dropped.
    """
    blocks: list[str] = []
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip() == _TB_HEADER:
            block = [lines[i]]
            i += 1
            while i < n:
                block.append(lines[i])
                cur = lines[i]
                i += 1
                if cur and not cur[0].isspace():
                    break
            blocks.append("\n".join(block))
        else:
            i += 1
    return blocks


def _attribute(blocks: list[str], a_dir: str, b_dir: str) -> dict:
    """Attribute traceback blocks to bot A / bot B by the paths inside the frames.

    Attribution is by *directory*, so a bot that imports helper modules is still
    matched. When A and B are the same directory (a mirror), the block counts
    against both -- which is right: it is the same code crashing either way.
    """
    per_dir: dict[str, int] = {}
    a_hits = b_hits = unknown = 0
    samples: list[str] = []
    for block in blocks:
        dirs = set()
        for line in block.splitlines():
            m = _FILE_LINE.match(line)
            if m:
                dirs.add(os.path.normcase(os.path.dirname(os.path.abspath(m.group("path")))))
        for d in dirs:
            per_dir[d] = per_dir.get(d, 0) + 1
        hit_a = a_dir in dirs
        hit_b = b_dir in dirs
        if hit_a:
            a_hits += 1
        if hit_b:
            b_hits += 1
        if not hit_a and not hit_b:
            unknown += 1
        if len(samples) < 3:
            samples.append(block[:2000])
    return {
        "a_exceptions": a_hits,
        "b_exceptions": b_hits,
        "unknown_exceptions": unknown,
        "exceptions_by_dir": per_dir,
        "traceback_samples": samples,
    }


def _scan_replay(path: str) -> int:
    """Count traceback markers in a .replay26.

    On this Windows build the engine keeps tracebacks on stdout and only bot
    print() output reaches the replay; on other builds it has gone the other
    way. Scanning both channels means the gate does not depend on which.
    """
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return 0
    return sum(data.count(marker) for marker in TRACEBACK_MARKERS)


def _blank_stats(spec: dict, error: str) -> dict:
    return {
        "id": spec.get("id"),
        "a": spec.get("a"),
        "b": spec.get("b"),
        "map": spec.get("map"),
        "seed": spec.get("seed"),
        "ok": False,
        "crashed": True,
        "error": error,
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
        "replay": None,
        "a_exceptions": 0,
        "b_exceptions": 0,
        "unknown_exceptions": 0,
        "exceptions_by_dir": {},
        "traceback_samples": [],
        "replay_traceback_hits": 0,
    }


def main(argv: list[str]) -> None:
    arg = argv[1] if len(argv) > 1 else "-"
    if arg == "-":
        spec = json.loads(sys.stdin.read())
    else:
        with open(arg, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
    matches = spec.get("matches", [])

    # Take the real stdout away from the engine before it can scribble on it.
    out_fd = os.dup(1)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_err = os.dup(2)
    os.dup2(devnull_fd, 1)
    os.dup2(devnull_fd, 2)

    cap_path = spec.get("capture_file") or (
        os.path.join(
            os.environ.get("TEMP") or os.environ.get("TMPDIR") or ".",
            f"arena_cap_{os.getpid()}.txt",
        )
    )
    cap_fd = os.open(cap_path, os.O_RDWR | os.O_CREAT | os.O_TRUNC)

    # Import after the redirect: the engine extension chatters on load on some builds.
    import fcode
    from fcode.fcode_engine import run_game

    eng_root = spec.get("engine_root") or os.path.dirname(os.path.abspath(fcode.__file__))

    def emit(record: dict) -> None:
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
        while data:
            written = os.write(out_fd, data)
            data = data[written:]

    for m in matches:
        want_capture = bool(m.get("capture", True))
        replay_req = m.get("replay")
        replay_path = replay_req or os.devnull
        a_dir = _norm(os.path.dirname(m["a"]))
        b_dir = _norm(os.path.dirname(m["b"]))

        if want_capture:
            os.lseek(cap_fd, 0, os.SEEK_SET)
            os.ftruncate(cap_fd, 0)
            os.dup2(cap_fd, 1)
            os.dup2(cap_fd, 2)
        else:
            os.dup2(devnull_fd, 1)
            os.dup2(devnull_fd, 2)

        t0 = time.perf_counter()
        err: str | None = None
        result: dict | None = None
        try:
            result = run_game(
                m["a"],
                m["b"],
                eng_root,
                m["map"],
                replay_path,
                int(m.get("seed", 1)),
                int(m.get("tle", 0)),
            )
        except Exception:
            err = traceback.format_exc(limit=8)
        elapsed = time.perf_counter() - t0

        captured = ""
        if want_capture:
            try:
                size = os.lseek(cap_fd, 0, os.SEEK_END)
                os.lseek(cap_fd, 0, os.SEEK_SET)
                raw = os.read(cap_fd, min(size, 8 * 1024 * 1024)) if size else b""
                captured = raw.decode("utf-8", "replace")
            except OSError:
                captured = ""

        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)

        if result is None:
            record = _blank_stats(m, err or "run_game returned None")
            record["elapsed"] = elapsed
            emit(record)
            continue

        record = {
            "id": m.get("id"),
            "a": m["a"],
            "b": m["b"],
            "map": m["map"],
            "seed": int(m.get("seed", 1)),
            "ok": True,
            "crashed": False,
            "error": None,
            "winner": result.get("winner"),
            "turns": result.get("turns"),
            "win_condition": result.get("win_condition"),
            "resign_message": result.get("resign_message"),
            "a_titanium": result.get("a_titanium"),
            "a_titanium_collected": result.get("a_titanium_collected"),
            "a_units": result.get("a_units"),
            "a_buildings": result.get("a_buildings"),
            "b_titanium": result.get("b_titanium"),
            "b_titanium_collected": result.get("b_titanium_collected"),
            "b_units": result.get("b_units"),
            "b_buildings": result.get("b_buildings"),
            "elapsed": elapsed,
            "replay": replay_req,
            "replay_traceback_hits": _scan_replay(replay_req) if replay_req else 0,
        }
        record.update(_attribute(_split_tracebacks(captured), a_dir, b_dir))
        emit(record)

    try:
        os.fsync(out_fd)
    except OSError:
        pass
    os.close(cap_fd)
    try:
        os.unlink(cap_path)
    except OSError:
        pass
    os.dup2(saved_err, 2)

    # Never let CPython finalize: Py_EndInterpreter leaves sub-interpreters
    # registered and the process aborts on a normal exit.
    os._exit(0)


if __name__ == "__main__":
    main(sys.argv)
