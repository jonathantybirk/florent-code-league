"""Run the rush on a single map against an inert opponent and report whether it lands."""

import os
import pathlib
import sys

import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)

sys.path.insert(0, str(ROOT / "bot"))
import atlas          # noqa: E402
import rushplan       # noqa: E402

maps = sys.argv[1:] or ["sprint", "duel", "atoll", "fjord", "crossfire"]
print(f"{'map':<11}{'plan':<38}{'winner':<8}{'turns':<7}{'cond':<18}bldgs")
for name in maps:
    plan = rushplan.attack_plan(name, "a")
    res = run_game(
        str(ROOT / "bot" / "main.py"), str(ROOT / "bots" / "zoo" / "idle" / "main.py"),
        ENGINE, str(ROOT / "maps" / f"{name}.map26"), os.devnull, 1, 0,
    )
    desc = "-" if plan is None else f"fire{plan['fire_pos']} {plan['facing'][:1]} ore{plan['ore']} kt{plan['kill_turn']}"
    print(f"{name:<11}{desc:<38}{res['winner']:<8}{res['turns']:<7}{res['win_condition']:<18}{res['a_buildings']}")
