"""The single gate every candidate must pass before it is believed or submitted.

Enforces, in one command:
  1. Submission validity   -- the engine's AST validator rules, BOM, __pycache__, main.py entry point.
  2. Known-map strength    -- the 15 published maps, mirrored. This is MEMORISATION, not strength.
  3. Unseen-map strength   -- generated maps, mirrored. This is the number that counts.
  4. Crash freedom         -- no unit may be lost to an exception.

Standing rule (docs/backlog.md): no result is a gain unless it holds on unseen maps too. A candidate that
improves on known maps while regressing on unseen ones has memorised, not learned, and this gate says so.

Noise floor (G/M01): a 30-game mirrored sweep moves +/-2-4 games for anything touching pathing. Deltas
below 5 games are reported as NOISE, not as gains.

Usage:
    python tools/evaluate.py                          # bot vs the standard panel
    python tools/evaluate.py <botdir> [opponents...]
"""

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PANEL = ["bots/zoo/starter_fixed", "bots/rivals/luc1", "bots/rivals/lockin",
         "bots/rivals/jonbot", "bots/rivals/vanguard"]
NOISE_FLOOR = 5


def clean():
    for base in ("bot", "bots"):
        d = ROOT / base
        if d.exists():
            for c in d.rglob("__pycache__"):
                shutil.rmtree(c, ignore_errors=True)


def run(script, *args):
    clean()
    out = subprocess.run([sys.executable, str(ROOT / "tools" / script), *args],
                         capture_output=True, text=True, cwd=ROOT)
    return out.stdout


def record(text):
    for line in text.splitlines():
        if line.startswith("RECORD"):
            parts = line.split()
            w, l = parts[1].split("-")
            kills = int(parts[-1])
            return int(w), int(l), kills
    return None, None, None


def main():
    bot = sys.argv[1] if len(sys.argv) > 1 else "bot"
    opponents = sys.argv[2:] or PANEL

    print(f"=== EVALUATE {bot} ===\n")

    valid = run("check_bot.py", bot)
    print(valid.strip())
    if "PASS" not in valid:
        print("\nGATE: FAIL (submission invalid)")
        return 1

    print(f"\n{'opponent':<22}{'known (memorised)':<22}{'UNSEEN (real)':<22}kills k/u")
    known_total = unseen_total = 0
    unseen_kills_total = 0
    for opp in opponents:
        kw, kl, kk = record(run("quickmatch.py", bot, opp))
        uw, ul, uk = record(run("unseen.py", bot, opp, "12"))
        if kw is None or uw is None:
            print(f"{opp.split('/')[-1]:<22}{'FAILED':<22}{'FAILED':<22}")
            continue
        known_total += kw
        unseen_total += uw
        unseen_kills_total += uk
        print(f"{opp.split('/')[-1]:<22}{f'{kw}-{kl}':<22}{f'{uw}-{ul}':<22}{kk} / {uk}")

    n_known = 30 * len(opponents)
    n_unseen = 24 * len(opponents)
    print(f"\n{'TOTAL':<22}{f'{known_total}/{n_known}':<22}{f'{unseen_total}/{n_unseen}':<22}"
          f"{unseen_kills_total} unseen kills")
    print(f"\nnoise floor is +/-{NOISE_FLOOR} games per pairing (G/M01) -- smaller deltas are not results")
    print("the UNSEEN column is the one that counts; the known column measures memorisation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
