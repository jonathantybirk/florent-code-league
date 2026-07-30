"""Sweep a module-level constant in bot/main.py and report the mirrored 30-game record.

Usage:  python tools/sweep_param.py BUILDERS 3 4 5 6
Restores the original value on exit. Deletes __pycache__ between runs (a stray one makes the engine
silently run the bot as inert -- G30).
"""

import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOT = ROOT / "bot" / "main.py"
OPPONENTS = ["bots/zoo/starter_fixed", "bots/rivals/luc1"]


def set_const(name, value):
    text = BOT.read_text(encoding="utf-8")
    new, n = re.subn(rf"^{name} = .*$", f"{name} = {value}", text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"could not find constant {name}")
    BOT.write_text(new, encoding="utf-8", newline="\n")


def clean():
    for d in (ROOT / "bot").rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def record(opponent):
    clean()
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "quickmatch.py"), "bot", opponent],
        capture_output=True, text=True, cwd=ROOT,
    ).stdout
    for line in out.splitlines():
        if line.startswith("RECORD"):
            return line.strip()
    return "NO RESULT"


def main():
    name, values = sys.argv[1], sys.argv[2:]
    original = re.search(rf"^{name} = (.*)$", BOT.read_text(encoding="utf-8"), re.M).group(1)
    print(f"sweeping {name} (original {original})\n")
    try:
        for v in values:
            set_const(name, v)
            rows = [f"{name}={v:<4}"]
            for opp in OPPONENTS:
                rows.append(f"{opp.split('/')[-1]:<14}{record(opp)}")
            print("  ".join(rows))
    finally:
        set_const(name, original)
        clean()
        print(f"\nrestored {name} = {original}")


if __name__ == "__main__":
    main()
