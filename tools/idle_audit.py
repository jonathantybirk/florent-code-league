"""How many Builder-turns actually accomplish anything, and what the rest wanted.

Win rate says a bot lost; it does not say that one of its five Builders stood
beside the Core for 999 of 999 rounds, or that another spent 120 turns walking
home from inside an enemy Launcher's ring and never moved. Both of those were
real, both cost more than any parameter on the bot, and neither is visible in
a replay -- a Builder failing to do something looks exactly like a Builder
doing nothing.

This runs matches with `BROKKR_DEBUG` set and tallies `debug.intent` lines by
unit and by outcome, so the question "is anybody idle, and why" has a number.

    uv run python tools/idle_audit.py bots/jon/brokkr --vs bots/rivals/steward
    uv run python tools/idle_audit.py bots/jon/brokkr --maps midgard,helheim
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sweep import POOL, ROOT  # noqa: E402

LINE = re.compile(r"r\s*(\d+) (\w+)\s+(\d+) at\([\d, ]+\) (.+)")

# Intents that move the game forward.
#
# HOLD is in here, and that is the correction this tool cost to learn. It
# reads "a mender that cannot afford to heal", which looks like the purest
# waste on the board -- 34.5% of every unit-turn brokkr spent over the pool.
# Sending those Builders back to mine measured 21/90 -> 15/90 against steward,
# and releasing only the ones with no route home measured 18/90. Standing
# beside the Core is not idleness: the tile is occupied so the enemy cannot
# build on it, and passive income is 10 Ti every 4 rounds, so a Builder
# waiting there heals the moment the tick lands. A Builder that walks away to
# earn misses both.
#
# What this tool is actually good at is the other kind: a unit at 100% of one
# intent for a whole match. That found the guard idling 999 of 999 rounds and
# the Builder thrown by a Launcher walking home for 120 turns without moving,
# both of which cost more than any parameter on the bot.
PRODUCTIVE = {"CONV", "HARV", "HEAL", "SENTINEL", "DIG", "WALK", "STEPOFF",
              "HOLD"}
# WALK is counted separately: a walk toward a real job is an investment, but a
# walk that never arrives is the livelock above, so it is reported apart from
# both the productive and the idle totals.
TRAVEL = {"WALK", "STEPOFF"}


def play(task):
    bot, opponent, map_name = task
    handle, path = tempfile.mkstemp(suffix=".log")
    os.close(handle)
    env = dict(os.environ, BROKKR_DEBUG=path)
    subprocess.run(
        ["uv", "run", "fcode", "run", bot, opponent, map_name, "--seed", "1",
         "--json", "--mark", "0", "--tle", "0",
         "--replay", f"/tmp/idle_{map_name}.replay26"],
        cwd=ROOT, capture_output=True, text=True, timeout=600, env=env)
    per_unit = collections.Counter()
    per_action = collections.Counter()
    reasons = collections.Counter()
    with open(path) as handle:
        for line in handle:
            match = LINE.match(line)
            if not match:
                continue
            _round, _role, unit, action = match.groups()
            head = action.split("->")[0].split()[0]
            per_unit[(map_name, unit, head)] += 1
            per_action[head] += 1
            if "<- " in action:
                reasons[(head, action.split("<- ", 1)[1][:52])] += 1
    os.unlink(path)
    return per_unit, per_action, reasons


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bot")
    parser.add_argument("--vs", default="bots/common/donothingbot")
    parser.add_argument("--maps", default=",".join(POOL))
    parser.add_argument("--jobs", type=int, default=10)
    args = parser.parse_args()

    maps = [m.strip() for m in args.maps.split(",") if m.strip()]
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(play, [(args.bot, args.vs, m) for m in maps]))

    per_unit = collections.Counter()
    per_action = collections.Counter()
    reasons = collections.Counter()
    for unit, action, reason in results:
        per_unit.update(unit)
        per_action.update(action)
        reasons.update(reason)

    total = sum(per_action.values())
    if not total:
        print("no intent lines -- is debug.intent wired into this bot?")
        return
    travel = sum(v for k, v in per_action.items() if k in TRAVEL)
    productive = sum(v for k, v in per_action.items()
                     if k in PRODUCTIVE and k not in TRAVEL)
    idle = total - productive - travel

    print(f"{args.bot} vs {args.vs}  --  {len(maps)} maps, {total} unit-turns")
    print(f"  productive {productive:>7} ({productive / total:>5.1%})   "
          f"travelling {travel:>7} ({travel / total:>5.1%})   "
          f"idle {idle:>7} ({idle / total:>5.1%})")
    print()
    print("intents:")
    for action, count in per_action.most_common(12):
        print(f"  {action:<12}{count:>8} ({count / total:>5.1%})")

    print("\nworst-idle units (per map):")
    by_unit = collections.defaultdict(collections.Counter)
    for (map_name, unit, head), count in per_unit.items():
        by_unit[(map_name, unit)][head] += count
    rows = []
    for key, counter in by_unit.items():
        turns = sum(counter.values())
        good = sum(v for k, v in counter.items() if k in PRODUCTIVE)
        rows.append((1 - good / turns, turns, key, counter))
    rows.sort(key=lambda r: (-r[0] * r[1]))
    for share, turns, (map_name, unit), counter in rows[:8]:
        top = ", ".join(f"{k}:{v}" for k, v in counter.most_common(4))
        print(f"  {map_name:<13} unit {unit:>4}  {turns:>5} turns  "
              f"{share:>5.0%} idle   {top}")

    print("\ncommonest reasons a turn achieved nothing:")
    for (head, why), count in reasons.most_common(10):
        if head in PRODUCTIVE and head not in TRAVEL:
            continue
        print(f"  {count:>7}  {head:<10} {why}")


if __name__ == "__main__":
    main()
