"""Builders that stood still while being shot.

A Builder that takes damage on consecutive rounds and does not move is either
finishing something worth more than its life or failing to notice. The second
case is free to fix and costs a body plus the +20% cost scale it was holding,
so it is worth measuring rather than eyeballing in the visualiser.

Reports, per team: how many Builders died, and of those how many were stationary
for the whole run of damage that killed them.

    uv run python benchmarks/underfire.py <replay...>
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from benchmarks.replay import decode  # noqa: E402

# Rounds of unanswered damage before standing still counts as a failure rather
# than as one unlucky shot.
FATAL_RUN = 3


def damage_rounds(replay, entity_id):
    """Rounds on which this entity lost HP."""
    out = defaultdict(int)
    for rnd, eid, delta in replay.hp_events:
        if eid == entity_id and delta < 0:
            out[rnd] += -delta
    return out


def report(path):
    replay = decode(path)
    rows = {}
    for team in ("a", "b"):
        died = stood = 0
        for e in replay.team_entities(team, "builder"):
            if e.death_round is None:
                continue
            died += 1
            hits = damage_rounds(replay, e.entity_id)
            if not hits:
                continue
            # The unbroken run of damage ending at death.
            run, rnd = [], e.death_round
            while rnd in hits:
                run.append(rnd)
                rnd -= 1
            if len(run) < FATAL_RUN:
                continue
            first, last = min(run), max(run)
            if e.pos_at(first) == e.pos_at(last):
                stood += 1
        rows[team] = (stood, died)
    return replay, rows


if __name__ == "__main__":
    totals = defaultdict(lambda: [0, 0])
    for arg in sys.argv[1:]:
        replay, rows = report(arg)
        for team, (stood, died) in rows.items():
            totals[team][0] += stood
            totals[team][1] += died
        if len(sys.argv) <= 4:
            for team, (stood, died) in sorted(rows.items()):
                print(f"{Path(arg).stem:24s} team {team}: {stood}/{died} "
                      f"dead Builders were stationary under fire")
    if len(sys.argv) > 4:
        for team, (stood, died) in sorted(totals.items()):
            share = stood / died if died else 0
            print(f"team {team}: {stood}/{died} dead Builders stationary "
                  f"under fire = {share:.1%}")
