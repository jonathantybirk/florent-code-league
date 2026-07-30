"""Full round-robin over every bot, mirrored and exhaustive.

Each pairing is 15 maps x both side assignments = 30 games. The engine is deterministic given RNG-free
bots, and Team A wins ~58-60% of identical-bot mirrors (G27), so mirroring is mandatory and replicates
are waste.

Usage:  python tools/roundrobin.py [name=path ...]
"""

import itertools
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

DEFAULT = {
    "AutistimusPrime": "bot",
    "luc1": "bots/rivals/luc1",
    "lockin": "bots/rivals/lockin",
    "frontier": "bots/rivals/frontier",
    "starter_fixed": "bots/zoo/starter_fixed",
}


def clean():
    for base in ("bot", "bots"):
        for d in (ROOT / base).rglob("__pycache__"):
            shutil.rmtree(d, ignore_errors=True)


def play(path_x, path_y):
    """Return (wins_for_x, kills_by_x) over the mirrored 30-game sweep."""
    clean()
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "quickmatch.py"), path_x, path_y],
        capture_output=True, text=True, cwd=ROOT,
    ).stdout
    for line in out.splitlines():
        if line.startswith("RECORD"):
            parts = line.split()
            wins, losses = parts[1].split("-")
            kills = parts[-1]
            return int(wins), int(losses), int(kills)
    return None, None, None


def main():
    bots = dict(DEFAULT)
    for arg in sys.argv[1:]:
        name, _, path = arg.partition("=")
        bots[name] = path

    names = list(bots)
    table = {n: {} for n in names}
    print(f"round-robin over {len(names)} bots, {len(list(itertools.combinations(names, 2)))} pairings "
          f"x 30 games\n")

    for x, y in itertools.combinations(names, 2):
        w, l, k = play(bots[x], bots[y])
        if w is None:
            print(f"{x} vs {y}: FAILED")
            continue
        table[x][y] = (w, l, k)
        table[y][x] = (l, w, None)
        print(f"{x:<16} vs {y:<16} {w:>2}-{l:<2}   (kills by {x}: {k})")

    print("\n" + "=" * 78)
    print(f"{'bot':<18}" + "".join(f"{n[:11]:>13}" for n in names) + f"{'total':>9}")
    for x in names:
        row = f"{x:<18}"
        total = 0
        for y in names:
            if x == y:
                row += f"{'-':>13}"
            else:
                w, l, _ = table[x][y]
                row += f"{f'{w}-{l}':>13}"
                total += w
        print(row + f"{total:>9}")
    print("\ntotal = games won across all pairings (max = 30 x (n-1))")


if __name__ == "__main__":
    main()
