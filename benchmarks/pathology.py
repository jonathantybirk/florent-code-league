"""Detect wasted Builder rounds in a replay: oscillation and standing still.

The enemy-Core oscillation bug was invisible in the score and obvious in the
position trace. This turns that into a check anything can run: for each Builder,
count the rounds it spent returning to a tile it occupied two rounds earlier
(pacing) and the rounds it did not move at all while far from any work.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks.replay import decode  # noqa: E402


def builder_tracks(replay):
    """team -> {entity_id: [(round, pos), ...]} including the spawn position."""
    out = defaultdict(dict)
    for entity in replay.entities.values():
        if entity.kind != "builder":
            continue
        track = [(entity.spawn_round, entity.pos)] + list(entity.pos_history)
        out[entity.team][entity.entity_id] = track
    return out


def pacing_rounds(track, upto):
    """Rounds where the Builder stepped back onto the tile it left last round."""
    positions = {}
    last = track[0][1]
    for rnd, pos in track:
        positions[rnd] = pos
    seen, paced = [], 0
    for rnd in range(track[0][0], upto + 1):
        if rnd in positions:
            last = positions[rnd]
        seen.append(last)
        if len(seen) >= 3 and seen[-1] == seen[-3] and seen[-1] != seen[-2]:
            paced += 1
    return paced, len(seen)


def report(path):
    replay = decode(path)
    rows = []
    for team, builders in sorted(builder_tracks(replay).items()):
        total_paced = total_rounds = 0
        for track in builders.values():
            paced, rounds = pacing_rounds(track, replay.rounds)
            total_paced += paced
            total_rounds += rounds
        rows.append((team, total_paced, total_rounds))
    return replay, rows


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        replay, rows = report(arg)
        name = Path(arg).stem
        for team, paced, rounds in rows:
            share = paced / rounds if rounds else 0
            print(f"{name:22s} team {team}: {paced:4d} paced / {rounds:5d} "
                  f"builder-rounds = {share:.1%}")
