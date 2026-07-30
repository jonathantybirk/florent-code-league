"""Record replays of specific matchups so they can be watched with `fcode watch`.

Usage:
    python tools/record.py                       # a curated set vs luc1
    python tools/record.py luc1 sprint a         # one specific game
    python tools/record.py <opponent> <map> <a|b>

Writes to replays/<bot>_vs_<opponent>_<map>_<side>.replay26 and prints the watch command.
"""

import pathlib
import sys

import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
OUT = ROOT / "replays"

RIVALS = {
    "luc1": "bots/rivals/luc1",
    "lockin": "bots/rivals/lockin",
    "frontier": "bots/rivals/frontier",
    "starter_fixed": "bots/zoo/starter_fixed",
    "idle": "bots/zoo/idle",
}


def resolve(bot):
    p = ROOT / bot
    return str(p / "main.py") if p.is_dir() else str(p)


def record(opponent, map_name, side):
    OUT.mkdir(exist_ok=True)
    opp_path = RIVALS.get(opponent, opponent)
    dest = OUT / f"ap_vs_{opponent}_{map_name}_{side}.replay26"
    a, b = ("bot", opp_path) if side == "a" else (opp_path, "bot")
    res = run_game(
        resolve(a), resolve(b), ENGINE,
        str(ROOT / "maps" / f"{map_name}.map26"), str(dest), 1, 0,
    )
    we_won = (res["winner"] == "A") if side == "a" else (res["winner"] == "B")
    mine = "a" if side == "a" else "b"
    theirs = "b" if side == "a" else "a"
    print(
        f"{map_name:<11}side={side}  {'WIN ' if we_won else 'LOSS'}  "
        f"{res['win_condition']:<18}turn {res['turns']:<5}"
        f"ours {res[f'{mine}_titanium_collected']:<7}theirs {res[f'{theirs}_titanium_collected']:<7}"
        f"-> {dest.name}"
    )


def main():
    if len(sys.argv) == 4:
        record(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        # A curated set against luc1: a fast rush kill, a slower one, a map we lose,
        # and the same map from the other side so the side bias is visible.
        for map_name, side in (("sprint", "a"), ("twins", "a"), ("aurora", "a"),
                               ("quarry", "a"), ("vault", "a"), ("sprint", "b")):
            record("luc1", map_name, side)
    print(f"\nWatch with:\n  .\\.venv\\Scripts\\fcode.exe watch replays\\<file>.replay26")


if __name__ == "__main__":
    main()
