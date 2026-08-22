"""Report unrated scrimmage results from OUR side, not from seat A's.

`match info` prints the score as A-B, and which seat we get is not ours to choose, so reading the
raw score is a coin-flip on whether it means a win or a loss.
"""
import re
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FCODE = str(ROOT / ".venv" / "Scripts" / "fcode.exe")
US = "Powered by SmartFridge"


def info(match_id):
    return subprocess.run([FCODE, "match", "info", match_id], capture_output=True,
                          text=True, timeout=120).stdout


def report(label, match_id):
    out = info(match_id)
    if "complete" not in out:
        print("  %-22s (still running)" % label)
        return None
    a = re.search(r"Team A:\s+(.*?)\s+\(", out)
    score = re.search(r"Score:\s+(\d+)-(\d+)", out)
    if not a or not score:
        print("  %-22s (unreadable)" % label)
        return None
    we_are_a = US in a.group(1)
    ours = int(score.group(1)) if we_are_a else int(score.group(2))
    theirs = int(score.group(2)) if we_are_a else int(score.group(1))
    verdict = "WIN " if ours > theirs else "loss"
    print("  %-22s %s  %d-%d   (we were %s)" % (label, verdict, ours, theirs,
                                                "A" if we_are_a else "B"))
    return ours, theirs


if __name__ == "__main__":
    won = played = 0
    for arg in sys.argv[1:]:
        label, mid = arg.split("=", 1)
        got = report(label, mid)
        if got:
            played += 1
            won += 1 if got[0] > got[1] else 0
    if played:
        print("  ---- %d of %d matches won" % (won, played))
