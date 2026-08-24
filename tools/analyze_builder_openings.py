"""Measure observable Builder behavior during replay openings.

Labels are deliberately behavioral rather than intentional: economy construction,
defensive construction, reaching the enemy-core region, and returning toward home
after an enemy first enters the home-core region.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from analyze_mining_lanes import core_tiles, initial_state
from analyze_top_mining import Entity, message, parse_entity, pos, scalar, submessages


DEFENSE_KINDS = {"barrier", "gunner", "sentinel", "launcher"}
ECON_KINDS = {"conveyor", "splitter", "harvester"}


def tile_distance(position: tuple[int, int], tiles: set[tuple[int, int]]) -> int:
    return min(abs(position[0] - x) + abs(position[1] - y) for x, y in tiles)


def analyze(path: Path, horizon: int = 50, danger_radius: int = 5) -> dict:
    raw = path.read_bytes()
    width, height, _, entities = initial_state(raw)
    cores = {e.team: e for e in entities.values() if e.kind == "core"}
    core_regions = {team: core_tiles(core) for team, core in cores.items()}
    spawned: dict[int, dict] = {}
    removed_turn: dict[int, int] = {}
    builds: dict[int, list[dict]] = defaultdict(list)
    attacks: dict[int, list[dict]] = defaultdict(list)
    history: dict[int, list[tuple[int, tuple[int, int]]]] = defaultdict(list)
    pressure_turn: dict[int, int | None] = {0: None, 1: None}

    for turn_number, turn in enumerate(submessages(raw, 3)):
        pending_builders: dict[tuple[int, int], int] = {}
        for update in submessages(turn, 1):
            attack_action = message(update, 13)
            if attack_action is not None:
                actor = scalar(attack_action, 1)
                if actor in spawned:
                    attacks[actor].append(
                        {"turn": turn_number, "target": list(pos(message(attack_action, 2)))}
                    )
                continue
            build_action = message(update, 16)
            if build_action is not None:
                pending_builders[pos(message(build_action, 2))] = scalar(build_action, 1)
                continue
            place = message(update, 1)
            if place is not None and message(place, 1) is not None:
                entity = parse_entity(message(place, 1))
                entities[entity.id] = entity
                if entity.kind == "bot":
                    spawned[entity.id] = {"team": entity.team, "turn": turn_number}
                actor = pending_builders.get(entity.position)
                if actor is not None and turn_number <= horizon:
                    builds[actor].append(
                        {"turn": turn_number, "kind": entity.kind, "position": list(entity.position)}
                    )
                continue
            move = message(update, 2)
            if move is not None:
                entity_id = scalar(move, 1)
                if entity_id in entities:
                    entities[entity_id].position = pos(message(move, 2))
                continue
            remove = message(update, 3)
            if remove is not None:
                removed_id = scalar(remove, 1)
                if removed_id in spawned:
                    removed_turn[removed_id] = turn_number
                entities.pop(removed_id, None)

        if turn_number <= horizon:
            for entity in entities.values():
                if entity.kind == "bot":
                    history[entity.id].append((turn_number, entity.position))
            for team in (0, 1):
                if pressure_turn[team] is None and any(
                    entity.team != team
                    and entity.kind in {"bot", "gunner", "sentinel", "launcher"}
                    and tile_distance(entity.position, core_regions[team]) <= danger_radius
                    for entity in entities.values()
                ):
                    pressure_turn[team] = turn_number

    teams = []
    for team in (0, 1):
        own, enemy = core_regions[team], core_regions[1 - team]
        team_ids = [entity_id for entity_id, data in spawned.items() if data["team"] == team and data["turn"] <= horizon]
        team_ids.sort(key=lambda entity_id: (spawned[entity_id]["turn"], entity_id))
        builders = []
        for index, entity_id in enumerate(team_ids, 1):
            track = history.get(entity_id, [])
            own_dist = [(turn, tile_distance(position, own)) for turn, position in track]
            enemy_dist = [(turn, tile_distance(position, enemy)) for turn, position in track]
            actor_builds = builds.get(entity_id, [])
            kinds = Counter(item["kind"] for item in actor_builds)
            pressure = pressure_turn[team]
            returned = False
            if pressure is not None:
                before = [distance for turn, distance in own_dist if turn <= pressure]
                after = [distance for turn, distance in own_dist if pressure < turn <= min(horizon, pressure + 12)]
                returned = bool(before and after and before[-1] - min(after) >= 4)
            builders.append(
                {
                    "label": f"builder_{index}",
                    "entity_id": entity_id,
                    "spawn_turn": spawned[entity_id]["turn"],
                    "removed_turn": removed_turn.get(entity_id),
                    "builds": actor_builds,
                    "attacks": attacks.get(entity_id, []),
                    "build_counts": dict(kinds),
                    "built_economy": any(kind in ECON_KINDS for kind in kinds),
                    "built_defense": any(kind in DEFENSE_KINDS for kind in kinds),
                    "reached_enemy_region": bool(enemy_dist and min(distance for _, distance in enemy_dist) <= danger_radius),
                    "first_enemy_region_turn": next(
                        (turn for turn, distance in enemy_dist if distance <= danger_radius), None
                    ),
                    "max_home_distance": max((distance for _, distance in own_dist), default=0),
                    "min_enemy_distance": min((distance for _, distance in enemy_dist), default=None),
                    "returned_after_pressure": returned,
                }
            )
        teams.append(
            {
                "pressure_turn": pressure_turn[team],
                "builder_count_by_horizon": len(builders),
                "builders": builders,
            }
        )
    return {"file": path.name, "width": width, "height": height, "horizon": horizon, "teams": teams}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--horizon", type=int, default=50)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = []
    for path in args.paths:
        paths.extend(sorted(path.glob("*.replay26")) if path.is_dir() else [path])
    rendered = json.dumps([analyze(path, args.horizon) for path in paths], indent=2)
    if args.output:
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
