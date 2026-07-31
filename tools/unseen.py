"""Play a matchup on maps the bot has NEVER seen (maps/generated/), mirrored.

This is the honest test of a bot that bundles the published pool: on an unrecognised map the atlas
returns None, the rush is disabled, and whatever is left has to carry the game on its own.

Usage:  python tools/unseen.py <botdir> <opponentdir> [limit]
"""

import os
import pathlib
import sys

import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)


def resolve(bot):
    p = ROOT / bot
    return str(p / "main.py") if p.is_dir() else str(p)


def main():
    x = sys.argv[1] if len(sys.argv) > 1 else "bot"
    y = sys.argv[2] if len(sys.argv) > 2 else "bots/zoo/starter_fixed"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 12

    maps = sorted((ROOT / "maps" / "generated").glob("*.map26"))[:limit]
    wins = losses = kills = 0
    conds = {}
    print(f"{x} vs {y}   on {len(maps)} UNSEEN maps x 2 sides\n")
    print(f"{'map':<40}{'side':<5}{'res':<4}{'win_condition':<20}{'ours':<8}theirs")
    for mp in maps:
        for side in ("a", "b"):
            a, b = (x, y) if side == "a" else (y, x)
            res = run_game(resolve(a), resolve(b), ENGINE, str(mp), os.devnull, 1, 0)
            won = (res["winner"] == "A") if side == "a" else (res["winner"] == "B")
            cond = res["win_condition"]
            conds[cond] = conds.get(cond, 0) + 1
            mine = "a" if side == "a" else "b"
            theirs = "b" if side == "a" else "a"
            if won:
                wins += 1
                if cond == "core_destroyed":
                    kills += 1
            else:
                losses += 1
            print(f"{mp.stem[:39]:<40}{side:<5}{'W' if won else 'L':<4}{cond:<20}"
                  f"{res[f'{mine}_titanium_collected']:<8}{res[f'{theirs}_titanium_collected']}")
    print(f"\nRECORD {wins}-{losses}   core kills: {kills}")
    print("win_conditions:", conds)


if __name__ == "__main__":
    main()
