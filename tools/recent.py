"""The last N ladder matches, read from OUR side, with per-game detail.

`fcode match list` prints the score as A-B and which seat we drew is not ours to choose, so the raw
score is a coin-flip on whether it means a win. This resolves that, and shows each game's map,
result and length -- because a 3-2 says nothing about the two games that were thrown away, which is
the whole question.
"""

import json
import re
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FCODE = str(ROOT / ".venv" / "Scripts" / "fcode.exe")
US = "Powered by SmartFridge"


def run(*args, timeout=150):
    try:
        return subprocess.run([FCODE] + list(args), capture_output=True,
                              text=True, timeout=timeout).stdout
    except Exception as exc:
        return "ERROR %s" % exc


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    raw = run("match", "list", "--mine", "--limit", str(n), "--json")
    try:
        rows = json.loads(raw)
    except Exception:
        print("could not read match list")
        return
    if isinstance(rows, dict):
        rows = rows.get("matches", [])
    for m in rows[:n]:
        mid = m.get("id")
        out = run("match", "info", mid)
        a = re.search(r"Team A:\s+(.*?)\s+\(", out)
        b = re.search(r"Team B:\s+(.*?)\s+\(", out)
        score = re.search(r"Score:\s+(\d+)-(\d+)", out)
        kind = "ladder" if "ladder" in out else "unrated"
        if not (a and b and score):
            print("  (match %s unreadable)" % (mid or "?")[:8])
            continue
        we_a = US in a.group(1)
        foe = (b if we_a else a).group(1)
        ours = int(score.group(1)) if we_a else int(score.group(2))
        theirs = int(score.group(2)) if we_a else int(score.group(1))
        print("  %-4s %-22s %d-%d  (%s, seat %s)" % (
            "WIN" if ours > theirs else "LOSS", foe[:22], ours, theirs, kind,
            "A" if we_a else "B"))
        for line in out.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != 5 or not cells[0].isdigit() or not cells[4].isdigit():
                continue
            won = (cells[2].startswith("A ")) == we_a
            print("        %-12s %-4s %-15s %s turns" % (
                cells[1], "won" if won else "lost", cells[3], cells[4]))


main()
