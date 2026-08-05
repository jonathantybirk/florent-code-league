"""Copy common/toolbox.py into every bot directory listed in TARGETS.

Run this after editing common/toolbox.py so each bots/<name>/toolbox.py
stays byte-identical to the canonical source. The game engine only puts
main.py's own directory on sys.path, and a submitted zip only contains
that bot's own directory, so every bot that imports toolbox needs a
physical copy sitting next to its main.py -- see common/toolbox.py's
module docstring for why.

    uv run scripts/sync_toolbox.py          # copy canonical -> all targets
    uv run scripts/sync_toolbox.py --check  # exit 1 if any target has drifted
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "common" / "toolbox.py"

# Bot directories that use the shared toolbox. Add a bot here once its
# main.py imports toolbox -- this script only copies the file in, it
# doesn't wire up the import for you.
TARGETS = [
    ROOT / "bots" / "green",
    ROOT / "bots" / "warden_",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Don't write anything; exit 1 if any target copy has drifted from the source.",
    )
    args = parser.parse_args()

    if not SOURCE.is_file():
        print(f"error: canonical source not found at {SOURCE}", file=sys.stderr)
        return 1

    drifted = []
    for target_dir in TARGETS:
        dest = target_dir / "toolbox.py"
        if args.check:
            if not dest.is_file() or not filecmp.cmp(SOURCE, dest, shallow=False):
                drifted.append(dest)
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE, dest)
        print(f"synced {dest.relative_to(ROOT)}")

    if args.check:
        if drifted:
            print("drifted from common/toolbox.py:", file=sys.stderr)
            for d in drifted:
                print(f"  {d.relative_to(ROOT)}", file=sys.stderr)
            return 1
        print("all toolbox.py copies match common/toolbox.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
