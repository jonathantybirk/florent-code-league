"""Run a probe bot for one match and print its resign message."""
import os
import pathlib
import shutil
import sys

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

import fcode
from fcode.fcode_engine import run_game

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE_ROOT = str(pathlib.Path(fcode.__file__).resolve().parent)


def scrub():
    for pc in ROOT.rglob("__pycache__"):
        if ".venv" in pc.parts:
            continue
        shutil.rmtree(pc, ignore_errors=True)


def main():
    probe = sys.argv[1]
    map_name = sys.argv[2] if len(sys.argv) > 2 else "sprint"
    scrub()
    res = run_game(
        str(ROOT / probe / "main.py"),
        str(ROOT / "bots" / "zoo" / "idle" / "main.py"),
        ENGINE_ROOT,
        str(ROOT / "maps" / (map_name + ".map26")),
        os.devnull, 1, 0,
    )
    scrub()
    print("winner=%s turns=%s cond=%s" % (res["winner"], res["turns"], res["win_condition"]))
    msg = res.get("resign_message")
    print("--- resign_message ---")
    if msg:
        for part in str(msg).split("|"):
            print(part)
    else:
        print("(empty)")


main()
