"""Run one or more probe bots and print whatever they resign with.

ct.resign(message) is the only channel that reaches run_game's result dict; print() is swallowed into
the .replay26 (G29). Probes are written to resign with their findings, so this is how you read them.

Usage:  python tools/runprobe.py <probe> [<probe> ...] [--map sprint] [--vs idle]
"""

import os
import pathlib
import sys

import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)


def resolve(name):
    for base in ("bots/probes", "bots/cand", "bots/rivals", "bots/zoo", "bots"):
        p = ROOT / base / name / "main.py"
        if p.is_file():
            return str(p)
    p = ROOT / name
    if (p / "main.py").is_file():
        return str(p / "main.py")
    return None


def main():
    mapname = "sprint"
    opponent = "idle"
    args = []
    rest = sys.argv[1:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--map" and i + 1 < len(rest):
            mapname = rest[i + 1]
            i += 2
        elif a == "--vs" and i + 1 < len(rest):
            opponent = rest[i + 1]
            i += 2
        elif a.startswith("--"):
            i += 1
        else:
            args.append(a)
            i += 1

    mappath = ROOT / "maps" / f"{mapname}.map26"
    if not mappath.is_file():
        for sub in ("lab", "generated"):
            cand = ROOT / "maps" / sub / f"{mapname}.map26"
            if cand.is_file():
                mappath = cand
                break

    opp = resolve(opponent)
    for name in args:
        path = resolve(name)
        if path is None:
            print(f"{name:<16} NOT FOUND")
            continue
        try:
            res = run_game(path, opp, ENGINE, str(mappath), os.devnull, 1, 0)
            msg = res.get("resign_message") or f"(no resign) {res['win_condition']} turn {res['turns']}"
            print(f"\n### {name}  [{mapname} vs {opponent}]\n{msg}")
        except Exception as exc:
            print(f"\n### {name}  FAILED {type(exc).__name__}: {str(exc)[:120]}")


if __name__ == "__main__":
    main()
