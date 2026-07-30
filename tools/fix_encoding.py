"""Repair mojibake introduced by PowerShell Set-Content round-trips.

PS 5.1's -Encoding ascii replaces every non-ASCII char with '?', and -Encoding utf8 writes a BOM that
the engine rejects outright. Never edit bot source from PowerShell; this undoes the damage when it happens.
"""

import pathlib
import sys

REPLACEMENTS = (
    ("???", "--"),
    ("??", "--"),
    ("﻿", ""),
)


def main(path):
    p = pathlib.Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    original = text
    for bad, good in REPLACEMENTS:
        text = text.replace(bad, good)
    if text != original:
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"repaired {p}")
    else:
        print(f"clean {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
