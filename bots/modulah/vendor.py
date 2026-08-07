#!/usr/bin/env python3
"""Copy lib/ into a bot directory.

The engine loads a bot as a flat directory of modules -- `import comms`, not
`from ..lib import comms` -- and a submission has to be self-contained. So
shared code must physically live in every bot that uses it.

That is exactly how the repo ended up with the same helper diverging across a
dozen bots. The fix is not to stop copying, it is to make copying mechanical
and one-directional: lib/ is the only place anyone edits, vendored copies are
generated and carry a header saying so.

    uv run python bots/modulah/vendor.py bots/modulah/beacon
    uv run python bots/modulah/vendor.py --all
    uv run python bots/modulah/vendor.py --check      # CI-style drift check
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "lib"
BANNER = "# GENERATED from bots/modulah/lib/{name} -- edit that file, not this copy.\n"


def _rendered(src: Path) -> str:
    return BANNER.format(name=src.name) + src.read_text()


def _bot_dirs() -> list[Path]:
    return [
        p
        for p in sorted(ROOT.iterdir())
        if p.is_dir() and p.name != "lib" and (p / "main.py").exists()
    ]


def vendor(target: Path, check: bool = False) -> list[str]:
    drift = []
    for src in sorted(LIB.glob("*.py")):
        want = _rendered(src)
        dst = target / src.name
        if check:
            have = dst.read_text() if dst.exists() else ""
            if hashlib.sha256(have.encode()).digest() != hashlib.sha256(want.encode()).digest():
                drift.append(f"{target.name}/{src.name}")
        else:
            dst.write_text(want)
    return drift


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bot", nargs="?", help="bot directory to vendor into")
    ap.add_argument("--all", action="store_true", help="every bot under bots/modulah/")
    ap.add_argument("--check", action="store_true", help="report drift, change nothing")
    args = ap.parse_args()

    targets = _bot_dirs() if (args.all or args.check) else [Path(args.bot).resolve()]
    if not targets:
        print("no bot directories found", file=sys.stderr)
        return 1

    drift: list[str] = []
    for t in targets:
        if not t.is_dir():
            print(f"not a directory: {t}", file=sys.stderr)
            return 1
        drift += vendor(t, check=args.check)

    if args.check:
        if drift:
            print("vendored copies are stale:\n  " + "\n  ".join(drift), file=sys.stderr)
            return 1
        print(f"all {len(targets)} bot(s) up to date with lib/")
    else:
        names = ", ".join(t.name for t in targets)
        print(f"vendored {len(list(LIB.glob('*.py')))} module(s) into: {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
