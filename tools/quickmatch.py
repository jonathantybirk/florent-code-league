"""Minimal mirrored sweep, used until arena/ lands.

Runs every map with both side assignments (the engine is deterministic and Team A wins ~58-60% of
identical-bot mirrors, so an unmirrored result is mostly side bias — G26/G27).
"""

import os
import pathlib
import sys

import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE_ROOT = str(pathlib.Path(fcode.__file__).resolve().parent)
MAPS = sorted(p.stem for p in (ROOT / "maps").glob("*.map26"))


def resolve(bot):
    """The engine wants the path to main.py; given a directory it walks up to the PARENT and
    AST-validates everything beneath it — which pulls in .venv and fails. Always pass main.py."""
    p = ROOT / bot
    return str(p / "main.py") if p.is_dir() else str(p)


def play(bot_a, bot_b, map_name, seed=1):
    return run_game(
        resolve(bot_a), resolve(bot_b), ENGINE_ROOT,
        str(ROOT / "maps" / f"{map_name}.map26"), os.devnull, seed, 0,
    )


def sweep(bot_x, bot_y, maps=None):
    maps = maps or MAPS
    wins = losses = 0
    kills = 0
    conds = {}
    rows = []
    for name in maps:
        for side in ("A", "B"):
            res = play(bot_x, bot_y, name, 1) if side == "A" else play(bot_y, bot_x, name, 1)
            won = (res["winner"] == "A") if side == "A" else (res["winner"] == "B")
            cond = res["win_condition"]
            conds[cond] = conds.get(cond, 0) + 1
            if won:
                wins += 1
                if cond == "core_destroyed":
                    kills += 1
            else:
                losses += 1
            mine = "a" if side == "A" else "b"
            rows.append((name, side, "W" if won else "L", cond, res["turns"],
                         res[f"{mine}_titanium_collected"], res[f"{mine}_units"]))
    return wins, losses, kills, conds, rows


if __name__ == "__main__":
    x = sys.argv[1] if len(sys.argv) > 1 else "bot"
    y = sys.argv[2] if len(sys.argv) > 2 else "bots/starter"
    w, l, k, conds, rows = sweep(x, y)
    print(f"{x}  vs  {y}")
    print(f"{'map':<11}{'side':<6}{'res':<5}{'win_condition':<20}{'turns':<7}{'collected':<11}units")
    for r in rows:
        print(f"{r[0]:<11}{r[1]:<6}{r[2]:<5}{r[3]:<20}{r[4]:<7}{r[5]:<11}{r[6]}")
    print(f"\nRECORD {w}-{l}   core kills: {k}")
    print("win_conditions:", conds)
