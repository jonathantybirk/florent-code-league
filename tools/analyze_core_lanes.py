"""Measure actual mining flows into each core edge from replay files.

Unlike topology-only analyses, this uses observed resource-movement events.  A
lane is a conveyor tile from which at least one resource actually entered one
of the four core tiles.  Harvesters are assigned to lanes by tracing observed
resource moves from a Harvester position to that core-entry tile.

Builder attribution is necessarily inferred: placement events do not contain
an actor id.  We record every Builder at Manhattan distance <= 1 immediately
before the placement.  A placement is exact when that leaves one candidate;
otherwise the candidate set is retained rather than silently guessing.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from analyze_top_mining import DIR_DELTA, Entity, message, parse_entity, pos, scalar, submessages


def initial_state(raw: bytes) -> tuple[int, int, list[list[int]], dict[int, Entity]]:
    map_buf = message(raw, 1) or b""
    width, height = scalar(map_buf, 1), scalar(map_buf, 2)
    rows = []
    for row in submessages(map_buf, 3):
        packed = message(row, 1) or b""
        rows.append(list(packed))
    entities = {}
    # Initial entities have no kind payload; in competition maps these are the
    # two 2x2 cores. All other entities arrive through placement updates.
    for core in submessages(map_buf, 4):
        entity = Entity(scalar(core, 1), scalar(core, 2), pos(message(core, 3)), "core")
        entities[entity.id] = entity
    return width, height, rows, entities


def core_tiles(core: Entity) -> set[tuple[int, int]]:
    return {(core.position[0] + dx, core.position[1] + dy) for dx in (0, 1) for dy in (0, 1)}


def intake_side(core: Entity, source: tuple[int, int]) -> str | None:
    x, y = source
    cx, cy = core.position
    if y == cy - 1 and cx <= x <= cx + 1:
        return "north"
    if x == cx + 2 and cy <= y <= cy + 1:
        return "east"
    if y == cy + 2 and cx <= x <= cx + 1:
        return "south"
    if x == cx - 1 and cy <= y <= cy + 1:
        return "west"
    return None


def blocked_sides(core: Entity, width: int, height: int, rows: list[list[int]]) -> list[str]:
    cx, cy = core.position
    perimeter = {
        "north": [(cx, cy - 1), (cx + 1, cy - 1)],
        "east": [(cx + 2, cy), (cx + 2, cy + 1)],
        "south": [(cx, cy + 2), (cx + 1, cy + 2)],
        "west": [(cx - 1, cy), (cx - 1, cy + 1)],
    }

    def unavailable(p: tuple[int, int]) -> bool:
        x, y = p
        return x < 0 or y < 0 or x >= width or y >= height or (rows and rows[y][x] == 1)

    return [side for side, tiles in perimeter.items() if all(unavailable(p) for p in tiles)]


def reachable_intakes(
    start: tuple[int, int],
    edges: dict[tuple[int, int], set[tuple[int, int]]],
    intakes: set[tuple[int, int]],
    core_positions: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    found, seen, stack = set(), set(), [start]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for nxt in edges.get(current, ()):
            if current in intakes and nxt in core_positions:
                found.add(current)
            elif nxt not in seen:
                stack.append(nxt)
    return found


def analyze_replay(path: Path) -> dict:
    raw = path.read_bytes()
    width, height, rows, entities = initial_state(raw)
    placements = []
    flow_edges = {0: defaultdict(set), 1: defaultdict(set)}
    observed_sources = {0: set(), 1: set()}
    harvester_positions = {0: set(), 1: set()}
    resource_origins = {0: {}, 1: {}}
    actual_lane_harvesters = {0: defaultdict(set), 1: defaultdict(set)}
    peak_physical = {0: {"turn": 0, "intakes": set()}, 1: {"turn": 0, "intakes": set()}}
    initial_cores = {e.team: e for e in entities.values() if e.kind == "core"}

    for turn_number, turn in enumerate(submessages(raw, 3)):
        for update in submessages(turn, 1):
            place = message(update, 1)
            if place is not None and message(place, 1) is not None:
                entity = parse_entity(message(place, 1))
                builders = [
                    bot.id
                    for bot in entities.values()
                    if bot.team == entity.team
                    and bot.kind == "bot"
                    and abs(bot.position[0] - entity.position[0])
                    + abs(bot.position[1] - entity.position[1]) <= 1
                ]
                if entity.kind in {"conveyor", "splitter", "harvester"}:
                    placements.append(
                        {
                            "turn": turn_number,
                            "team": entity.team,
                            "kind": entity.kind,
                            "position": entity.position,
                            "builder_candidates": builders,
                        }
                    )
                if entity.kind == "harvester":
                    harvester_positions[entity.team].add(entity.position)
                entities[entity.id] = entity
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
                continue

            distribute = message(update, 4)
            if distribute is not None:
                for resource_move in submessages(distribute, 1):
                    source, destination = pos(message(resource_move, 1)), pos(message(resource_move, 2))
                    resource_id = scalar(resource_move, 3)
                    # Resource moves are team-labelled only indirectly. The
                    # source is occupied by that team's transport/Harvester at
                    # the instant the move occurs.
                    source_entity = next((e for e in entities.values() if e.position == source), None)
                    if source_entity is None:
                        continue
                    team = source_entity.team
                    flow_edges[team][source].add(destination)
                    observed_sources[team].add(source)
                    if source_entity.kind == "harvester":
                        resource_origins[team][resource_id] = source
                    core = initial_cores.get(team)
                    if core and destination in core_tiles(core) and intake_side(core, source):
                        origin = resource_origins[team].get(resource_id)
                        if origin is not None:
                            actual_lane_harvesters[team][source].add(origin)

        for team, core in initial_cores.items():
            tiles = core_tiles(core)
            physical = set()
            for entity in entities.values():
                if entity.team != team or entity.kind not in {"conveyor", "splitter"}:
                    continue
                delta = DIR_DELTA.get(entity.direction)
                if delta and (entity.position[0] + delta[0], entity.position[1] + delta[1]) in tiles:
                    physical.add(entity.position)
            if len(physical) > len(peak_physical[team]["intakes"]):
                peak_physical[team] = {"turn": turn_number, "intakes": physical}

    result = {"file": path.name, "width": width, "height": height, "teams": []}
    cores = {e.team: e for e in entities.values() if e.kind == "core"}
    # A destroyed core may no longer be in final entities; recover it from map.
    _, _, _, initial_entities = initial_state(raw)
    for e in initial_entities.values():
        cores.setdefault(e.team, e)

    for team in (0, 1):
        core = cores[team]
        tiles = core_tiles(core)
        intakes = set()
        for source, destinations in flow_edges[team].items():
            for destination in destinations:
                if destination in tiles and intake_side(core, source):
                    intakes.add(source)

        lane_harvesters = {
            intake: set(actual_lane_harvesters[team].get(intake, set())) for intake in intakes
        }

        team_placements = [p for p in placements if p["team"] == team]
        builder_lane_objects = defaultdict(lambda: defaultdict(int))
        unassigned = 0
        for placement in team_placements:
            if placement["kind"] not in {"conveyor", "splitter"}:
                continue
            lanes = reachable_intakes(placement["position"], flow_edges[team], intakes, tiles)
            candidates = placement["builder_candidates"]
            if len(candidates) != 1:
                unassigned += 1
                continue
            for lane in lanes:
                builder_lane_objects[str(candidates[0])][str(lane)] += 1

        result["teams"].append(
            {
                "core": core.position,
                "blocked_sides": blocked_sides(core, width, height, rows),
                "peak_physical_lane_count": len(peak_physical[team]["intakes"]),
                "peak_physical_lane_turn": peak_physical[team]["turn"],
                "peak_physical_lanes": [
                    {"intake": p, "side": intake_side(core, p)}
                    for p in sorted(peak_physical[team]["intakes"])
                ],
                "lane_count": len(intakes),
                "sides_used": sorted({intake_side(core, p) for p in intakes}),
                "lanes": [
                    {
                        "intake": intake,
                        "side": intake_side(core, intake),
                        "harvesters": sorted(lane_harvesters[intake]),
                        "harvester_count": len(lane_harvesters[intake]),
                    }
                    for intake in sorted(intakes)
                ],
                "placements": team_placements,
                "exact_builder_attributions": sum(
                    len(p["builder_candidates"]) == 1
                    for p in team_placements
                    if p["kind"] in {"conveyor", "splitter"}
                ),
                "ambiguous_builder_attributions": unassigned,
                "builder_lane_objects": {
                    builder: dict(lanes) for builder, lanes in builder_lane_objects.items()
                },
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("replays", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = [analyze_replay(path) for path in args.replays]
    rendered = json.dumps(results, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
