"""Replay-level opening analysis for Bean counters v68.

Reconstructs exact build ownership/order, per-unit and team ore knowledge from
vision, deposit distance/selection, Launcher use, and Builder heal actions.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

from analyze_mining_lanes import core_tiles, initial_state
from analyze_top_mining import DIR_DELTA, Entity, message, parse_entity, pos, scalar, submessages


VISION_SQ = {
    "core": 36,
    "bot": 20,
    "gunner": 13,
    "sentinel": 32,
    "launcher": 26,
}


def distances(width: int, height: int, rows: list[list[int]], starts: set[tuple[int, int]]):
    result = {p: 0 for p in starts}
    queue = deque(starts)
    while queue:
        x, y = queue.popleft()
        for dx, dy in DIR_DELTA.values():
            p = x + dx, y + dy
            if not (0 <= p[0] < width and 0 <= p[1] < height):
                continue
            if rows[p[1]][p[0]] == 1 or p in result:
                continue
            result[p] = result[(x, y)] + 1
            queue.append(p)
    return result


def visible(entity: Entity, tile: tuple[int, int]) -> bool:
    radius = VISION_SQ.get(entity.kind)
    if radius is None:
        return False
    if entity.kind == "core":
        sources = core_tiles(entity)
    else:
        sources = {entity.position}
    return min((tile[0] - x) ** 2 + (tile[1] - y) ** 2 for x, y in sources) <= radius


def analyze(path: Path, horizon: int = 100) -> dict:
    raw = path.read_bytes()
    width, height, rows, entities = initial_state(raw)
    initial_cores = {e.team: e for e in entities.values() if e.kind == "core"}
    ores = {(x, y) for y, row in enumerate(rows) for x, value in enumerate(row) if value == 2}
    distance = {
        team: distances(width, height, rows, core_tiles(core))
        for team, core in initial_cores.items()
    }
    known = {0: set(), 1: set()}
    known_by_entity: dict[int, set[tuple[int, int]]] = {entity_id: set() for entity_id in entities}
    discovered = {0: {}, 1: {}}
    builds = {0: [], 1: []}
    harvesters = {0: {}, 1: {}}
    heals = {0: [], 1: []}
    pressure_turn = {0: None, 1: None}
    bot_spawn_order = {0: [], 1: []}

    def observe(turn: int):
        for entity in entities.values():
            if entity.kind not in VISION_SQ:
                continue
            seen = {ore for ore in ores if visible(entity, ore)}
            known_by_entity.setdefault(entity.id, set()).update(seen)
            for ore in seen:
                if ore not in known[entity.team]:
                    known[entity.team].add(ore)
                    discovered[entity.team][ore] = turn

    for turn_number, turn in enumerate(submessages(raw, 3)):
        observe(turn_number)
        for team, core in initial_cores.items():
            if pressure_turn[team] is None:
                home = core_tiles(core)
                for entity in entities.values():
                    if entity.team == team or entity.kind not in {"bot", "gunner", "sentinel", "launcher"}:
                        continue
                    if min(abs(entity.position[0] - x) + abs(entity.position[1] - y) for x, y in home) <= 5:
                        pressure_turn[team] = turn_number
                        break

        pending: dict[tuple[int, int], int] = {}
        for update in submessages(turn, 1):
            build_action = message(update, 16)
            if build_action is not None:
                pending[pos(message(build_action, 2))] = scalar(build_action, 1)
                continue

            # Replay update field 15 is Builder heal(actor id, target position).
            heal = message(update, 15)
            if heal is not None:
                actor = scalar(heal, 1)
                entity = entities.get(actor)
                if entity is not None:
                    target = pos(message(heal, 2))
                    heals[entity.team].append(
                        {
                            "turn": turn_number,
                            "builder_id": actor,
                            "target": list(target),
                            "after_pressure": pressure_turn[entity.team] is not None
                            and turn_number >= pressure_turn[entity.team],
                        }
                    )
                continue

            place = message(update, 1)
            if place is not None and message(place, 1) is not None:
                entity = parse_entity(message(place, 1))
                actor = pending.get(entity.position)
                entities[entity.id] = entity
                known_by_entity.setdefault(entity.id, set())
                if entity.kind == "bot":
                    bot_spawn_order[entity.team].append(entity.id)
                if actor is not None:
                    actor_entity = entities.get(actor)
                    actor_known = known_by_entity.get(actor, set())
                    core = initial_cores[entity.team]
                    d = distance[entity.team].get(entity.position)
                    delta = DIR_DELTA.get(entity.direction)
                    output = (
                        (entity.position[0] + delta[0], entity.position[1] + delta[1])
                        if delta else None
                    )
                    record = {
                        "turn": turn_number,
                        "kind": entity.kind,
                        "entity_id": entity.id,
                        "builder_id": actor,
                        "position": list(entity.position),
                        "direction": entity.direction,
                        "core_distance": d,
                        "outputs_into_core": output in core_tiles(core) if output else False,
                        "actor_known_ore_count": len(actor_known),
                        "team_known_ore_count": len(known[entity.team]),
                        "nearest_actor_known_ore": min(
                            (abs(entity.position[0] - x) + abs(entity.position[1] - y) for x, y in actor_known),
                            default=None,
                        ),
                    }
                    builds[entity.team].append(record)
                    if entity.kind == "harvester":
                        harvesters[entity.team][entity.position] = record
                continue

            move = message(update, 2)
            if move is not None:
                entity_id = scalar(move, 1)
                if entity_id in entities:
                    entities[entity_id].position = pos(message(move, 2))
                continue
            remove = message(update, 3)
            if remove is not None:
                entities.pop(scalar(remove, 1), None)

        if turn_number >= horizon:
            # Continue parsing only if needed for full-game Launcher/heal totals.
            pass

    teams = []
    for team in (0, 1):
        labels = {entity_id: f"builder_{i}" for i, entity_id in enumerate(bot_spawn_order[team], 1)}
        for record in builds[team]:
            record["builder_label"] = labels.get(record["builder_id"])
        for record in heals[team]:
            record["builder_label"] = labels.get(record["builder_id"])
        deposit_rows = []
        for ore in sorted(ores):
            deposit_rows.append(
                {
                    "position": list(ore),
                    "core_distance": distance[team].get(ore),
                    "discovered_turn": discovered[team].get(ore),
                    "harvester_turn": harvesters[team].get(ore, {}).get("turn"),
                    "harvester_builder": labels.get(harvesters[team].get(ore, {}).get("builder_id")),
                }
            )
        teams.append(
            {
                "core": list(initial_cores[team].position),
                "initial_core_visible_ores": sum(visible(initial_cores[team], ore) for ore in ores),
                "pressure_turn": pressure_turn[team],
                "builds": builds[team],
                "deposits": deposit_rows,
                "heals": heals[team],
            }
        )
    return {"file": path.name, "width": width, "height": height, "turns": len(submessages(raw, 3)), "teams": teams}


def main():
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
