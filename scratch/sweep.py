"""Parameter sweep: temporarily rewrite a constant, run the arena, restore.

    uv run python scratch/sweep.py MAX_BUILDERS 4,5,6 -- lucas/strat1
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOT = ROOT / "bots/jon/fair/vanguard"
FILES = list(BOT.glob("*.py"))


def find(name):
    pattern = re.compile(rf"^{name} = (.+)$", re.M)
    for path in FILES:
        text = path.read_text()
        if pattern.search(text):
            return path, text
    raise SystemExit(f"{name} not found in {BOT}")


def main():
    name = sys.argv[1]
    values = sys.argv[2].split(",")
    opponents = sys.argv[sys.argv.index("--") + 1:]
    path, original = find(name)
    pattern = re.compile(rf"^{name} = (.+)$", re.M)
    print(f"{name} lives in {path.name}, currently "
              f"{pattern.search(original).group(1)}", flush=True)
    try:
        for value in values:
            path.write_text(pattern.sub(f"{name} = {value}", original))
            for opponent in opponents:
                out = subprocess.run(
                    ["uv", "run", "python", "scratch/arena.py",
                     "jon/fair/vanguard", opponent],
                    cwd=ROOT, capture_output=True, text=True).stdout
                first = out.splitlines()[0] if out else "(no output)"
                print(f"  {name}={value:>6s}  {first}", flush=True)
    finally:
        path.write_text(original)


main()
