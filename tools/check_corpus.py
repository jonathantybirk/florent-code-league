"""Verify the generated unseen-map corpus still loads and plays on the current engine.

The corpus was produced for fcode 2.2.0. If 2.3.3 changed the .map26 format or added validation, every
"unseen" measurement we take is silently garbage, so this must pass before any generalization claim.
"""

import os
import pathlib
import sys

import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
IDLE = str(ROOT / "bots" / "zoo" / "idle" / "main.py")


def main():
    maps = sorted((ROOT / "maps" / "generated").glob("*.map26"))
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(maps)
    ok = bad = 0
    for m in maps[:limit]:
        try:
            res = run_game(IDLE, IDLE, ENGINE, str(m), os.devnull, 1, 0)
            ok += 1
            if ok <= 3:
                print(f"  {m.stem:<42} OK  {res['win_condition']} turn {res['turns']}")
        except Exception as exc:
            bad += 1
            print(f"  {m.stem:<42} FAIL {type(exc).__name__}: {str(exc)[:80]}")
    print(f"\n{ok} playable / {bad} failed  of {min(limit, len(maps))}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
