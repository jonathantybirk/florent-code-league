"""Mechanic metrics computed from a decoded replay.

Everything is reported per team so one match yields a benchmark row for both
sides. Checkpoints are end-of-round counts.
"""

from __future__ import annotations

from benchmarks.replay import Replay

CHECKPOINTS = (50, 100, 150, 200, 300, 500, 750, 999)
# A builder with no movement and no adjacent friendly construction for this
# many consecutive rounds, while the game is still running, counts as stalled.
STALL_WINDOW = 30


def compute(replay: Replay) -> dict:
    out: dict = {"rounds": replay.rounds, "win_condition": replay.win_condition}
    for team in ("a", "b"):
        other = "b" if team == "a" else "a"
        prefix = f"{team}_"
        harvest_rounds = replay.build_rounds(team, "harvester")
        builder_rounds = replay.build_rounds(team, "builder")
        out[prefix + "first_harvester"] = harvest_rounds[0] if harvest_rounds else None
        out[prefix + "harvesters_built"] = len(harvest_rounds)
        out[prefix + "builders_spawned"] = len(builder_rounds)
        out[prefix + "conveyors_built"] = len(replay.build_rounds(team, "conveyor"))
        out[prefix + "barriers_built"] = len(replay.build_rounds(team, "barrier"))
        for kind in ("gunner", "sentinel", "launcher"):
            rounds = replay.build_rounds(team, kind)
            out[prefix + f"{kind}s_built"] = len(rounds)
            out[prefix + f"first_{kind}"] = rounds[0] if rounds else None
        out[prefix + "harvesters_at"] = {
            str(cp): replay.count_at(team, "harvester", cp) for cp in CHECKPOINTS
        }
        out[prefix + "builders_alive_at"] = {
            str(cp): replay.count_at(team, "builder", cp) for cp in CHECKPOINTS
        }

        # Aggression: damage on the opposing Core.
        enemy_core_hits = replay.core_damage_rounds(other)
        out[prefix + "first_core_hit"] = (
            enemy_core_hits[0][0] if enemy_core_hits else None
        )
        out[prefix + "core_damage_dealt"] = sum(d for _, d in enemy_core_hits)
        enemy_core = replay.entities[replay.core_id[other]]
        out[prefix + "enemy_core_killed_round"] = enemy_core.death_round

        # Survival: own Core HP at end.
        out[prefix + "core_hp_end"] = replay.core_hp_at(team, replay.rounds)
        own_hits = replay.core_damage_rounds(team)
        out[prefix + "first_core_damage_taken"] = own_hits[0][0] if own_hits else None

        out.update(_stall_metrics(replay, team, prefix))
    return out


def _stall_metrics(replay: Replay, team: str, prefix: str) -> dict:
    """Detect builders that stop moving and stop producing while alive."""
    # Activity credit: any friendly build event within Chebyshev distance 1 of
    # the builder's position at that round counts as builder activity.
    friendly_builds = [
        (e.spawn_round, e.pos)
        for e in replay.entities.values()
        if e.team == team and e.kind not in ("core", "builder") and e.spawn_round >= 0
    ]
    worst_stall = 0
    stalled_builders = 0
    builders = replay.team_entities(team, "builder")
    for builder in builders:
        start = builder.spawn_round
        end = builder.death_round if builder.death_round is not None else replay.rounds - 1
        if end - start < STALL_WINDOW:
            continue
        activity = sorted(
            set(builder.move_rounds)
            | {
                r for r, pos in friendly_builds
                if start <= r <= end
                and max(abs(pos[0] - builder.pos_at(r)[0]),
                        abs(pos[1] - builder.pos_at(r)[1])) <= 1
            }
        )
        gaps = []
        previous = start
        for r in activity:
            gaps.append(r - previous)
            previous = r
        gaps.append(end - previous)
        longest = max(gaps) if gaps else end - start
        worst_stall = max(worst_stall, longest)
        if longest >= STALL_WINDOW:
            stalled_builders += 1
    return {
        prefix + "worst_builder_stall": worst_stall,
        prefix + "stalled_builders": stalled_builders,
        prefix + "builders_tracked": len(builders),
    }
