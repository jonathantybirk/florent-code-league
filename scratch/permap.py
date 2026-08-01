"""Which opening wins on which map, measured one map at a time.

    uv run python scratch/permap.py ECONOMY_BUILDERS 1,2

Only an unfair bot can act on the answer: the atlas names the map on round 0,
so the opening can be looked up instead of guessed. Fair bots must pick one
number for the whole pool.

Every cell is 8 games (4 frozen opponents, both sides), which is not much, so
treat a 5-3 as noise and only act on the lopsided ones. The caller decides;
this only reports.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOT = "jon/unfair/vanguard_oracle"
FILES = list((ROOT / "bots" / BOT).glob("*.py"))
MAPS = sorted(p.name[:-6] for p in (ROOT / "maps").glob("*.map26"))
OPPONENTS = ["jon/versions/probes/v233_e", "jon/versions/probes/v233_h",
             "jon/versions/probes/v233_i", "jon/versions/probes/uw_v2"]
SCORE = re.compile(r"(\d+) - (\d+)")


def find(name):
    pattern = re.compile(rf"^{name} = (.+)$", re.M)
    for path in FILES:
        text = path.read_text()
        if pattern.search(text):
            return path, text
    raise SystemExit(f"{name} not found in {BOT}")


def main():
    name, values = sys.argv[1], sys.argv[2].split(",")
    path, original = find(name)
    pattern = re.compile(rf"^{name} = (.+)$", re.M)
    table = {}
    try:
        for value in values:
            path.write_text(pattern.sub(f"{name} = {value}", original))
            for mapname in MAPS:
                won = played = 0
                for opponent in OPPONENTS:
                    out = subprocess.run(
                        ["uv", "run", "python", "scratch/arena.py", BOT,
                         opponent, "--maps", mapname],
                        cwd=ROOT, capture_output=True, text=True).stdout
                    hit = SCORE.search(out.splitlines()[0] if out else "")
                    if hit:
                        won += int(hit.group(1))
                        played += int(hit.group(1)) + int(hit.group(2))
                table[(value, mapname)] = (won, played)
                print(f"  {name}={value:>3s} {mapname:<10s} {won}/{played}",
                      flush=True)
    finally:
        path.write_text(original)

    print(f"\n{'map':<12s}" + "".join(f"{v:>8s}" for v in values) + "   pick")
    picks = {}
    for mapname in MAPS:
        cells = [table.get((v, mapname), (0, 0)) for v in values]
        best = max(range(len(values)), key=lambda i: cells[i][0])
        worst = min(cell[0] for cell in cells)
        # Only call it a difference when it is a big one.
        pick = values[best] if cells[best][0] - worst >= 3 else ""
        if pick:
            picks[mapname] = int(pick)
        row = "".join(f"{c[0]:>4d}/{c[1]:<3d}" for c in cells)
        print(f"{mapname:<12s}{row}   {pick}")
    print("\nMAP_OPENING = " + repr(picks))


main()
