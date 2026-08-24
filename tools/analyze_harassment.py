"""Extract observable harassment and responses from replay26 files.

The analyzer records actions rather than claiming hidden intent.  A Builder is
an economic harasser when it reaches the enemy region and attacks economic
entities or places obstructions on historically valuable enemy tiles.  Core
damage and weapon construction are retained separately so later analysis can
distinguish disruption from conversion into a full attack.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from analyze_mining_lanes import core_tiles, initial_state
from analyze_top_mining import message, parse_entity, pos, scalar, submessages


ECONOMY = {"conveyor", "splitter", "harvester"}
WEAPONS = {"gunner", "sentinel", "launcher"}


def distance(position: tuple[int, int], region: set[tuple[int, int]]) -> int:
    return min(abs(position[0] - x) + abs(position[1] - y) for x, y in region)


def analyze(path: Path, enemy_radius: int = 7) -> dict:
    raw = path.read_bytes()
    width, height, _, entities = initial_state(raw)
    cores = {e.team: e for e in entities.values() if e.kind == "core"}
    regions = {team: core_tiles(core) for team, core in cores.items()}
    known_economy_tiles = {0: set(), 1: set()}
    spawned: dict[int, dict] = {}
    builder_index = Counter()
    tracks: dict[int, dict] = {}
    pending_builders: dict[tuple[int, tuple[int, int]], int] = {}
    recent_builder_hits: dict[tuple[int, tuple[int, int]], tuple[int, int]] = {}
    core_damage = {0: [], 1: []}
    team_response_builds = {0: [], 1: []}
    economy_losses = {0: [], 1: []}
    unresolved_losses: dict[tuple[int, tuple[int, int]], list[dict]] = defaultdict(list)
    launches = []

    def ensure_builder(entity, turn: int) -> dict:
        if entity.id not in tracks:
            builder_index[entity.team] += 1
            label = f"builder_{builder_index[entity.team]}"
            spawned[entity.id] = {"team": entity.team, "turn": turn, "label": label}
            tracks[entity.id] = {
                "id": entity.id,
                "label": label,
                "team": entity.team,
                "spawn_turn": turn,
                "removed_turn": None,
                "first_enemy_region_turn": None,
                "turns_enemy_region": 0,
                "moves_enemy_region": 0,
                "direct_attacks": [],
                "economy_attacks": [],
                "enemy_builder_attacks": [],
                "core_attacks": [],
                "builds_enemy_region": [],
                "obstructions": [],
                "confirmed_economy_kills": [],
                "launched_count": 0,
            }
        return tracks[entity.id]

    for turn_number, turn in enumerate(submessages(raw, 3)):
        positions_before = {e.position: e for e in entities.values()}
        for entity in list(entities.values()):
            if entity.kind == "bot":
                track = ensure_builder(entity, turn_number)
                enemy = regions[1 - entity.team]
                if distance(entity.position, enemy) <= enemy_radius:
                    track["turns_enemy_region"] += 1
                    if track["first_enemy_region_turn"] is None:
                        track["first_enemy_region_turn"] = turn_number

        for update in submessages(turn, 1):
            attack = message(update, 13)
            if attack is not None:
                actor_id = scalar(attack, 1)
                target = pos(message(attack, 2))
                actor = entities.get(actor_id)
                if actor is not None and actor.kind == "bot":
                    track = ensure_builder(actor, turn_number)
                    victim = positions_before.get(target)
                    event = {
                        "turn": turn_number,
                        "target": list(target),
                        "target_kind": victim.kind if victim else None,
                        "target_team": victim.team if victim else None,
                    }
                    track["direct_attacks"].append(event)
                    if victim is not None and victim.team != actor.team:
                        recent_builder_hits[(victim.team, target)] = (turn_number, actor_id)
                        if victim.kind in ECONOMY:
                            track["economy_attacks"].append(event)
                        elif victim.kind == "bot":
                            track["enemy_builder_attacks"].append(event)
                        elif victim.kind == "core":
                            track["core_attacks"].append(event)
                continue

            build = message(update, 16)
            if build is not None:
                pending_builders[(turn_number, pos(message(build, 2)))] = scalar(build, 1)
                continue

            place = message(update, 1)
            if place is not None and message(place, 1) is not None:
                entity = parse_entity(message(place, 1))
                entities[entity.id] = entity
                if entity.kind == "bot":
                    ensure_builder(entity, turn_number)
                if entity.kind in ECONOMY:
                    known_economy_tiles[entity.team].add(entity.position)
                    waiting = unresolved_losses[(entity.team, entity.position)]
                    if waiting:
                        loss = waiting.pop(0)
                        loss["replacement_turn"] = turn_number
                        loss["replacement_kind"] = entity.kind
                        loss["downtime"] = turn_number - loss["turn"]
                actor_id = pending_builders.get((turn_number, entity.position))
                actor = entities.get(actor_id) if actor_id is not None else None
                if actor is not None and actor.kind == "bot":
                    track = ensure_builder(actor, turn_number)
                    enemy_team = 1 - actor.team
                    in_enemy_region = distance(entity.position, regions[enemy_team]) <= enemy_radius
                    if in_enemy_region:
                        event = {
                            "turn": turn_number,
                            "kind": entity.kind,
                            "position": list(entity.position),
                        }
                        track["builds_enemy_region"].append(event)
                        historically_valuable = entity.position in known_economy_tiles[enemy_team]
                        near_enemy_core = distance(entity.position, regions[enemy_team]) <= 2
                        if entity.kind == "barrier" and (historically_valuable or near_enemy_core):
                            event["historical_economy_tile"] = historically_valuable
                            event["near_core"] = near_enemy_core
                            track["obstructions"].append(event)
                if entity.kind in WEAPONS | {"barrier"}:
                    team_response_builds[entity.team].append(
                        {"turn": turn_number, "kind": entity.kind, "position": list(entity.position)}
                    )
                continue

            move = message(update, 2)
            if move is not None:
                entity = entities.get(scalar(move, 1))
                if entity is not None:
                    old_position = entity.position
                    new_position = pos(message(move, 2))
                    if entity.kind == "bot" and (
                        abs(old_position[0] - new_position[0])
                        + abs(old_position[1] - new_position[1])
                        > 1
                    ):
                        launcher = next(
                            (
                                candidate
                                for candidate in entities.values()
                                if candidate.kind == "launcher"
                                and abs(candidate.position[0] - old_position[0])
                                + abs(candidate.position[1] - old_position[1])
                                == 1
                            ),
                            None,
                        )
                        launches.append(
                            {
                                "turn": turn_number,
                                "source": list(old_position),
                                "target": list(new_position),
                                "bot_id": entity.id,
                                "bot_team": entity.team,
                                "launcher_team": launcher.team if launcher else None,
                            }
                        )
                        ensure_builder(entity, turn_number)["launched_count"] += 1
                    entity.position = new_position
                    if entity.kind == "bot" and distance(entity.position, regions[1 - entity.team]) <= enemy_radius:
                        ensure_builder(entity, turn_number)["moves_enemy_region"] += 1
                continue

            health = message(update, 5)
            if health is not None:
                entity = entities.get(scalar(health, 1))
                raw_delta = scalar(health, 2)
                delta = raw_delta - (1 << 64) if raw_delta >= (1 << 63) else raw_delta
                if entity is not None and entity.kind == "core" and delta < 0:
                    core_damage[1 - entity.team].append(
                        {"turn": turn_number, "damage": -delta}
                    )
                continue

            remove = message(update, 3)
            if remove is not None:
                entity = entities.pop(scalar(remove, 1), None)
                if entity is None:
                    continue
                if entity.kind == "bot" and entity.id in tracks:
                    tracks[entity.id]["removed_turn"] = turn_number
                if entity.kind in ECONOMY:
                    hit = recent_builder_hits.get((entity.team, entity.position))
                    loss = {
                        "turn": turn_number,
                        "kind": entity.kind,
                        "position": list(entity.position),
                        "attacker_builder_id": None,
                        "replacement_turn": None,
                        "replacement_kind": None,
                        "downtime": None,
                    }
                    if hit is not None and turn_number - hit[0] <= 1 and hit[1] in tracks:
                        loss["attacker_builder_id"] = hit[1]
                        tracks[hit[1]]["confirmed_economy_kills"].append(
                            {"turn": turn_number, "kind": entity.kind, "position": list(entity.position)}
                        )
                    economy_losses[entity.team].append(loss)
                    unresolved_losses[(entity.team, entity.position)].append(loss)

    teams = []
    for team in (0, 1):
        builders = [track for track in tracks.values() if track["team"] == team]
        builders.sort(key=lambda b: (b["spawn_turn"], b["id"]))
        first_damage = min((x["turn"] for x in core_damage[team]), default=None)
        for track in builders:
            economic_actions = len(track["economy_attacks"]) + len(track["obstructions"])
            track["observable_harassment"] = economic_actions > 0
            track["converted_to_core_attack"] = bool(
                track["first_enemy_region_turn"] is not None
                and first_damage is not None
                and first_damage >= track["first_enemy_region_turn"]
            )
        teams.append(
            {
                "builders": builders,
                "first_core_damage": first_damage,
                "gross_core_damage": sum(x["damage"] for x in core_damage[team]),
                "response_builds": team_response_builds[team],
                "economy_losses": economy_losses[team],
            }
        )
    return {
        "file": path.name,
        "width": width,
        "height": height,
        "turns": len(submessages(raw, 3)),
        "launches": launches,
        "teams": teams,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = []
    for path in args.paths:
        paths.extend(sorted(path.glob("*.replay26")) if path.is_dir() else [path])
    rendered = json.dumps([analyze(path) for path in paths], indent=2)
    if args.output:
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
