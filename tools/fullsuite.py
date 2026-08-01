"""Sweep one bot against EVERY rival we hold, on both map sets, and print one table.

Known  = the 21 published competition maps, both side assignments (42 games/pairing).
Unseen = the generated corpus, both sides (48 games/pairing) -- the number that predicts ladder strength.

Usage:  python tools/fullsuite.py [botdir] [--known-only]
"""

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def clean():
    for base in ("bot", "bots"):
        d = ROOT / base
        if d.exists():
            for c in d.rglob("__pycache__"):
                shutil.rmtree(c, ignore_errors=True)


def rivals():
    out = []
    for d in sorted((ROOT / "bots" / "rivals").iterdir()):
        if (d / "main.py").is_file():
            out.append((d.name, f"bots/rivals/{d.name}"))
    for name in ("starter_fixed", "idle"):
        p = ROOT / "bots" / "zoo" / name
        if (p / "main.py").is_file():
            out.append((name, f"bots/zoo/{name}"))
    return out


def record(script, bot, opp, extra=()):
    clean()
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / script), bot, opp, *extra],
        capture_output=True, text=True, cwd=ROOT,
    ).stdout
    for line in out.splitlines():
        if line.startswith("RECORD"):
            parts = line.split()
            w, l = parts[1].split("-")
            return int(w), int(l), int(parts[-1])
    return None, None, None


def main():
    bot = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "bot"
    known_only = "--known-only" in sys.argv

    print(f"{bot} vs the full suite\n")
    header = f"{'opponent':<20}{'KNOWN (21x2)':<16}{'kills':<7}"
    if not known_only:
        header += f"{'UNSEEN':<14}{'kills':<7}"
    print(header)
    print("-" * len(header))

    kw = kl = uw = ul = 0
    rows = []
    for name, path in rivals():
        k = record("quickmatch.py", bot, path)
        u = (None, None, None) if known_only else record("unseen.py", bot, path, ("12",))
        if k[0] is None:
            print(f"{name:<20}FAILED")
            continue
        kw += k[0]
        kl += k[1]
        line = f"{name:<20}{f'{k[0]}-{k[1]}':<16}{k[2]:<7}"
        if not known_only and u[0] is not None:
            uw += u[0]
            ul += u[1]
            line += f"{f'{u[0]}-{u[1]}':<14}{u[2]:<7}"
        rows.append((name, k, u))
        print(line)

    print("-" * len(header))
    total = f"{'TOTAL':<20}{f'{kw}-{kl}':<16}{'':<7}"
    if not known_only:
        total += f"{f'{uw}-{ul}':<14}"
    print(total)
    print("\nnoise floor +/-2-4 games per pairing (M01); UNSEEN predicts ladder strength")


if __name__ == "__main__":
    main()
