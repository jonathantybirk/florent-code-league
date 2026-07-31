"""Compare every bot with the per-turn CPU limit ENFORCED versus unenforced.

Windows silently reports get_cpu_time_elapsed() == 0 and never enforces --tle (G21), so this is only
meaningful on Linux. On Linux an over-budget turn silently voids everything the unit did after the
threshold while the unit survives (G22) -- so a CPU-heavy bot loses actions on the ladder and its author
would never see it locally on Windows.

A bot that is CPU-clean scores identically under both settings. Any divergence is budget overrun.

Usage (inside WSL):  python3 tools/tle_audit.py [bot ...]
"""

import os
import pathlib
import sys

import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)

BOTS = {
    "AutistimusPrime": "bot",
    "luc1": "bots/rivals/luc1",
    "lockin": "bots/rivals/lockin",
    "jonbot": "bots/rivals/jonbot",
    "vanguard": "bots/rivals/vanguard",
}
OPPONENT = "bots/zoo/starter_fixed"


def resolve(bot):
    p = ROOT / bot
    return str(p / "main.py") if p.is_dir() else str(p)


def sweep(bot, tle):
    """Return (wins, per-map results) over all maps, both sides."""
    maps = sorted((ROOT / "maps").glob("*.map26"))
    wins = 0
    rows = {}
    for mp in maps:
        for side in ("a", "b"):
            a, b = (bot, OPPONENT) if side == "a" else (OPPONENT, bot)
            res = run_game(resolve(a), resolve(b), ENGINE, str(mp), os.devnull, 1, tle)
            won = (res["winner"] == "A") if side == "a" else (res["winner"] == "B")
            wins += bool(won)
            rows[(mp.stem, side)] = (won, res["turns"], res["win_condition"])
    return wins, rows


def main():
    names = sys.argv[1:] or list(BOTS)
    print(f"{'bot':<18}{'tle=0 (off)':<14}{'tle=10 (on)':<14}{'delta':<8}divergent maps")
    for name in names:
        path = BOTS.get(name, name)
        off_w, off_r = sweep(path, 0)
        on_w, on_r = sweep(path, 10)
        diff = [f"{m}/{s}" for (m, s) in off_r if off_r[(m, s)][0] != on_r[(m, s)][0]]
        flag = "" if off_w == on_w and not diff else "  <-- AFFECTED BY CPU LIMIT"
        print(f"{name:<18}{f'{off_w}-{30 - off_w}':<14}{f'{on_w}-{30 - on_w}':<14}"
              f"{on_w - off_w:<8}{', '.join(diff[:6]) if diff else 'none'}{flag}")


if __name__ == "__main__":
    main()
