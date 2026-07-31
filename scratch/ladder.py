"""Score one bot against the whole opposing field.

Matches are deterministic, so a 30-game head-to-head is a single sample of a
chaotic system: a one-line change can swing it by four games without being
better. Only the pooled record across every opponent and both sides is worth
reading.

    uv run python scratch/ladder.py jon/fair/vanguard
"""
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIELD = ["lucas/strat1", "lucas/claude_challenger_1", "lucas/claude_challenger_2",
         "lucas/claude_challenger_3", "jon/unfair/lockin", "common/starter"]

# Now that the bot survives, many matches run the full thousand rounds and a
# complete pass costs about ten minutes. Screen ideas on a spread of map sizes
# and shapes first, then confirm the survivors on the whole field.
SCREEN_MAPS = "atoll,aurora,duel,pinch,quarry,twins"


def main():
    args = [a for a in sys.argv[1:] if a != "--screen"]
    screen = "--screen" in sys.argv
    bot = args[0]
    field = args[1:] or FIELD
    won = lost = 0
    for opponent in field:
        command = ["uv", "run", "python", "scratch/arena.py", bot, opponent]
        if screen:
            command += ["--maps", SCREEN_MAPS]
        out = subprocess.run(command, cwd=ROOT, capture_output=True,
                             text=True).stdout
        line = out.splitlines()[0] if out else "(no output)"
        print("  " + line)
        try:
            parts = line.split()
            won += int(parts[1])
            lost += int(parts[3])
        except (IndexError, ValueError):
            pass
    total = won + lost
    print(f"TOTAL {bot}: {won}-{lost}  ({100 * won / max(total, 1):.1f}%)")


main()
