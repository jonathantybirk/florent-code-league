"""One command: score a bot against the whole roster, its own ancestors, and
the purpose-built counters.

    uv run python scratch/gauntlet.py jon/fair/vanguard [--screen] [--gen]

A change is only worth keeping if it holds against all three groups. The
ancestors matter most: beating the field says little once the field is
saturated, while losing to your own previous build is unambiguous.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GROUPS = {
    "roster": ["lucas/strat1", "lucas/claude_challenger_1",
               "lucas/claude_challenger_2", "lucas/claude_challenger_3",
               "jon/unfair/lockin", "jon/fair/jonbot", "common/starter",
               "jon/fair/undertow"],
    "ancestors": ["jon/probes/vg_v1", "jon/probes/vg_v2",
                  "jon/probes/vg_v3", "jon/probes/vg_v4", "jon/probes/vg_v5", "jon/probes/vg_v6"],
    "counters": ["jon/probes/turtle", "jon/probes/nemesis",
                 "jon/probes/reaver", "jon/probes/baiter",
                 "jon/probes/riptide"],
}
SCREEN = "atoll,aurora,duel,pinch,quarry,twins"


def main():
    bot = sys.argv[1]
    flags = sys.argv[2:]
    maps = None
    if "--screen" in flags:
        maps = SCREEN
    if "--gen" in flags:
        maps = ",".join(sorted(p.name[:-6] for p in
                               (ROOT / "maps/generated").glob("*.map26"))
                        ).replace("random", "generated/random")
    grand_w = grand_l = 0
    for group, opponents in GROUPS.items():
        won = lost = 0
        print(f"\n{group}:")
        for opponent in opponents:
            if opponent == bot:
                continue
            command = ["uv", "run", "python", "scratch/arena.py", bot, opponent]
            if maps:
                command += ["--maps", maps]
            out = subprocess.run(command, cwd=ROOT, capture_output=True,
                                 text=True).stdout
            line = out.splitlines()[0] if out else "(no output)"
            print("  " + line)
            found = re.search(r"\s(\d+) - (\d+)\s", line)
            if found:
                won += int(found.group(1))
                lost += int(found.group(2))
        print(f"  -> {group}: {won}-{lost} "
              f"({100 * won / max(won + lost, 1):.1f}%)")
        grand_w, grand_l = grand_w + won, grand_l + lost
    print(f"\nGAUNTLET {bot}: {grand_w}-{grand_l} "
          f"({100 * grand_w / max(grand_w + grand_l, 1):.1f}%)")


main()
