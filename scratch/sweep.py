"""Parameter sweep: temporarily rewrite a constant, run the arena, restore.

    uv run python scratch/sweep.py MAX_BUILDERS 4,5,6 -- lucas/strat1
    uv run python scratch/sweep.py --bot jon/unfair/vanguard_oracle \
        LAUNCH_HOPS 1,2,3 -- jon/fair/vanguard

A constant that is optimal in one bot is routinely wrong in another -- the
oracle variants see the whole map from round 0 and want different numbers from
the bot that has to scout for them -- so the bot under test is a parameter.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARGV = sys.argv[1:]
if ARGV and ARGV[0] == "--bot":
    BOT_NAME = ARGV[1]
    ARGV = ARGV[2:]
else:
    BOT_NAME = "jon/fair/vanguard"
BOT = ROOT / "bots" / BOT_NAME
FILES = list(BOT.glob("*.py"))


def find(name):
    pattern = re.compile(rf"^{name} = (.+)$", re.M)
    for path in FILES:
        text = path.read_text()
        if pattern.search(text):
            return path, text
    raise SystemExit(f"{name} not found in {BOT}")


def main():
    name = ARGV[0]
    values = ARGV[1].split(",")
    opponents = ARGV[ARGV.index("--") + 1:]
    path, original = find(name)
    pattern = re.compile(rf"^{name} = (.+)$", re.M)
    print(f"{name} lives in {BOT_NAME}/{path.name}, currently "
              f"{pattern.search(original).group(1)}", flush=True)
    try:
        for value in values:
            path.write_text(pattern.sub(f"{name} = {value}", original))
            for opponent in opponents:
                out = subprocess.run(
                    ["uv", "run", "python", "scratch/arena.py",
                     BOT_NAME, opponent],
                    cwd=ROOT, capture_output=True, text=True).stdout
                first = out.splitlines()[0] if out else "(no output)"
                print(f"  {name}={value:>6s}  {first}", flush=True)
    finally:
        path.write_text(original)


main()
