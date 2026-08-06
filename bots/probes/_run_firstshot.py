"""Run duel probe pairs and print the reporter's resign message PLUS the full
result dict (winner / win_condition / turns / building counts).

Usage: python scratchpad/rundu.py <tag> [<tag> ...] [--map duel]
Tags name a pair: bot A is du_<tag>_a, bot B is du_<tag>_b.
"""

import os
import pathlib
import shutil
import sys

import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(r"c:/Users/edlun/Desktop/lucky shots/Hackathons/florent-code-league")
ENGINE = str(pathlib.Path(fcode.__file__).resolve().parent)
PROBES = ROOT / "bots" / "probes"


def nuke_pycache():
    for p in PROBES.glob("*/__pycache__"):
        shutil.rmtree(p, ignore_errors=True)


def main():
    mapname = "firstshot"
    tags = []
    rest = sys.argv[1:]
    i = 0
    while i < len(rest):
        if rest[i] == "--map":
            mapname = rest[i + 1]
            i += 2
        else:
            tags.append(rest[i])
            i += 1

    mappath = ROOT / "maps" / "lab" / ("%s.map26" % mapname)
    if not mappath.is_file():
        mappath = ROOT / "maps" / ("%s.map26" % mapname)

    for tag in tags:
        nuke_pycache()
        a = PROBES / ("du_%s_a" % tag) / "main.py"
        b = PROBES / ("du_%s_b" % tag) / "main.py"
        if not a.is_file() or not b.is_file():
            print("### %s MISSING" % tag)
            continue
        try:
            res = run_game(str(a), str(b), ENGINE, str(mappath), os.devnull, 1, 0)
        except Exception as exc:
            print("### %s FAILED %s: %s" % (tag, type(exc).__name__, str(exc)[:160]))
            continue
        print("\n### %s  win=%s cond=%s turns=%s  Abld=%s Aunits=%s Bbld=%s Bunits=%s"
              % (tag, res.get("winner"), res.get("win_condition"), res.get("turns"),
                 res.get("a_buildings"), res.get("a_units"),
                 res.get("b_buildings"), res.get("b_units")))
        print(res.get("resign_message") or "(no resign)")


if __name__ == "__main__":
    main()
