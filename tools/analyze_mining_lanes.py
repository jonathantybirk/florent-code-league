"""Analyze directed mining lanes, core inputs, flow, and builder ownership.

This is an offline replay-analysis tool.  A lane is one conveyor whose directed
output enters one of the four tiles occupied by a 2x2 core.  Harvesters are
assigned to the lane reached by following conveyor directions downstream.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from analyze_top_mining import (
    DIR_DELTA,
    Entity,
    fields,
    message,
    parse_entity,
    pos,
    scalar,
    submessages,
)


def initial_state(raw: bytes) -> tuple[int, int, list[list[int]], dict[int, Entity]]:
    map_buf = message(raw, 1) or b""
    width, height = scalar(map_buf, 1), scalar(map_buf, 2)
    rows = []
    for row in submessages(map_buf, 3):
        packed = message(row, 1) or b""
        rows.append(list(packed))
    entities = {}
    # Initial cores have only id/team/position; their type is implied by Map.
    for core in submessages(map_buf, 4):
        entity = Entity(
            id=scalar(core, 1),
            team=scalar(core, 2),
            position=pos(message(core, 3)),
            kind="core",
        )
        entities[entity.id] = entity
    return width, height, rows, entities


def core_tiles(core: Entity) -> set[tuple[int, int]]:
    x, y = core.position
    return {(x + dx, y + dy) for dx in (0, 1) for dy in (0, 1)}


def side_of_input(core: Entity, p: tuple[int, int]) -> str:
    x, y = core.position
    if p[0] < x:
        return "west"
    if p[0] > x + 1:
        return "east"
    if p[1] < y:
        return "north"
    return "south"


def side_access(core: Entity, width: int, height: int, rows: list[list[int]]) -> dict[str, dict]:
    x, y = core.position
    perimeter = {
        "north": [(x, y - 1), (x + 1, y - 1)],
        "east": [(x + 2, y), (x + 2, y + 1)],
        "south": [(x, y + 2), (x + 1, y + 2)],
        "west": [(x - 1, y), (x - 1, y + 1)],
    }
    out = {}
    for side, ps in perimeter.items():
        inside = [p for p in ps if 0 <= p[0] < width and 0 <= p[1] < height]
        # Tile value 1 is an impassable wall; value 2 is an ore deposit.
        usable = [p for p in inside if p[1] < len(rows) and p[0] < len(rows[p[1]]) and rows[p[1]][p[0]] != 1]
        out[side] = {"border": len(inside) < 2, "usable_tiles": usable}
    return out


def snapshot_network(
    entities: dict[int, Entity],
    builders: dict[int, int | None],
    team: int,
    width: int,
    height: int,
    rows: list[list[int]],
    observed_harvester_edges: dict[tuple[int, int], Counter],
) -> dict | None:
    cores = [e for e in entities.values() if e.team == team and e.kind == "core"]
    if not cores:
        return None
    core = cores[0]
    tiles = core_tiles(core)
    own = {e.position: e for e in entities.values() if e.team == team}
    conveyors = {p: e for p, e in own.items() if e.kind in {"conveyor", "splitter"}}
    harvesters = [e for e in own.values() if e.kind == "harvester"]

    downstream = {}
    for p, conveyor in conveyors.items():
        delta = DIR_DELTA.get(conveyor.direction)
        downstream[p] = (p[0] + delta[0], p[1] + delta[1]) if delta else None

    inputs = {p: e for p, e in conveyors.items() if downstream.get(p) in tiles}
    lane_for = {p: p for p in inputs}
    for start in conveyors:
        seen, p = set(), start
        while p in conveyors and p not in seen:
            seen.add(p)
            if p in inputs:
                lane_for[start] = p
                break
            p = downstream.get(p)

    lane_harvesters: dict[tuple[int, int], set[int]] = defaultdict(set)
    ambiguous = []
    for harvester in harvesters:
        hp = harvester.position
        observed = [p for p, _ in observed_harvester_edges.get(hp, Counter()).most_common() if p in lane_for]
        adjacent = [
            (hp[0] + dx, hp[1] + dy)
            for dx, dy in DIR_DELTA.values()
            if (hp[0] + dx, hp[1] + dy) in lane_for
        ]
        candidates = observed or adjacent
        lanes = {lane_for[p] for p in candidates}
        if len(lanes) == 1:
            lane_harvesters[next(iter(lanes))].add(harvester.id)
        elif len(lanes) > 1:
            ambiguous.append(harvester.id)

    # Attribute every conveyor in a lane's reverse-connected tree.
    lane_builders: dict[tuple[int, int], set[int]] = defaultdict(set)
    lane_tiles: dict[tuple[int, int], int] = Counter()
    lane_conveyors: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for p, lane in lane_for.items():
        lane_tiles[lane] += 1
        builder = builders.get(conveyors[p].id)
        lane_conveyors[lane].append(
            {"entity_id": conveyors[p].id, "position": list(p), "builder_id": builder}
        )
        if builder is not None:
            lane_builders[lane].add(builder)

    access = side_access(core, width, height, rows)
    lanes = []
    for p, entity in sorted(inputs.items()):
        side = side_of_input(core, p)
        lanes.append(
            {
                "input": list(p),
                "side": side,
                "input_builder": builders.get(entity.id),
                "builders": sorted(lane_builders[p]),
                "conveyor_tiles": lane_tiles[p],
                "conveyors": sorted(lane_conveyors[p], key=lambda item: item["entity_id"]),
                "harvesters": sorted(lane_harvesters[p]),
                "harvester_count": len(lane_harvesters[p]),
            }
        )
    return {
        "core": list(core.position),
        "side_access": access,
        "lane_count": len(lanes),
        "sides_used": sorted({lane["side"] for lane in lanes}),
        "connected_harvesters": sum(lane["harvester_count"] for lane in lanes),
        "unassigned_harvesters": len(harvesters) - sum(lane["harvester_count"] for lane in lanes),
        "ambiguous_harvesters": ambiguous,
        "lanes": lanes,
    }


def analyze(path: Path) -> dict:
    raw = path.read_bytes()
    width, height, rows, entities = initial_state(raw)
    builders: dict[int, int | None] = {entity_id: None for entity_id in entities}
    bot_order: dict[int, list[int]] = {0: [], 1: []}
    observed_harvester_edges: dict[int, dict[tuple[int, int], Counter]] = {
        0: defaultdict(Counter), 1: defaultdict(Counter)
    }
    resource_origins: dict[int, dict[int, int]] = {0: {}, 1: {}}
    observed_lane_harvesters: dict[int, dict[tuple[int, int], set[int]]] = {
        0: defaultdict(set), 1: defaultdict(set)
    }
    arrivals_by_input: dict[int, Counter] = {0: Counter(), 1: Counter()}
    direction_checks = Counter()
    best: dict[int, tuple[tuple, dict] | None] = {0: None, 1: None}

    for turn_number, turn in enumerate(submessages(raw, 3)):
        pending_builders: dict[tuple[int, int], int] = {}
        for update in submessages(turn, 1):
            build_action = message(update, 16)
            if build_action is not None:
                pending_builders[pos(message(build_action, 2))] = scalar(build_action, 1)
                continue

            place = message(update, 1)
            if place is not None:
                entity_buf = message(place, 1)
                if entity_buf is not None:
                    entity = parse_entity(entity_buf)
                    entities[entity.id] = entity
                    builders[entity.id] = pending_builders.get(entity.position)
                    if entity.kind == "bot":
                        bot_order[entity.team].append(entity.id)
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
                by_pos = {e.position: e for e in entities.values()}
                cores = {team: core_tiles(e) for team in (0, 1) for e in entities.values() if e.team == team and e.kind == "core"}
                for resource_move in submessages(distribute, 1):
                    source = pos(message(resource_move, 1))
                    destination = pos(message(resource_move, 2))
                    resource_id = scalar(resource_move, 3)
                    source_entity = by_pos.get(source)
                    if source_entity and source_entity.kind == "harvester":
                        observed_harvester_edges[source_entity.team][source][destination] += 1
                        resource_origins[source_entity.team][resource_id] = source_entity.id
                    if source_entity and source_entity.kind in {"conveyor", "splitter"}:
                        delta = DIR_DELTA.get(source_entity.direction)
                        expected = (source[0] + delta[0], source[1] + delta[1]) if delta else None
                        direction_checks["checked"] += 1
                        direction_checks["matched"] += expected == destination
                    for team, tiles in cores.items():
                        if destination in tiles:
                            arrivals_by_input[team][source] += 1
                            origin = resource_origins[team].get(resource_id)
                            if origin is not None:
                                observed_lane_harvesters[team][source].add(origin)

        for team in (0, 1):
            snap = snapshot_network(
                entities, builders, team, width, height, rows, observed_harvester_edges[team]
            )
            if snap is None:
                continue
            snap["turn"] = turn_number
            score = (snap["connected_harvesters"], snap["lane_count"], turn_number)
            if best[team] is None or score > best[team][0]:
                best[team] = (score, snap)

    results = []
    for team in (0, 1):
        snap = best[team][1] if best[team] else None
        if snap:
            labels = {entity_id: f"builder_{i}" for i, entity_id in enumerate(bot_order[team], 1)}
            for lane in snap["lanes"]:
                lane["observed_core_arrivals"] = arrivals_by_input[team][tuple(lane["input"])]
                lane["observed_harvesters"] = sorted(
                    observed_lane_harvesters[team][tuple(lane["input"])]
                )
                lane["observed_harvester_count"] = len(lane["observed_harvesters"])
                lane["input_builder_label"] = labels.get(lane["input_builder"])
                lane["builder_labels"] = [labels.get(entity_id, f"entity_{entity_id}") for entity_id in lane["builders"]]
                for conveyor in lane["conveyors"]:
                    conveyor["builder_label"] = labels.get(
                        conveyor["builder_id"],
                        f"entity_{conveyor['builder_id']}" if conveyor["builder_id"] is not None else None,
                    )
            snap["builder_ids"] = bot_order[team]
        results.append(snap)
    return {
        "file": path.name,
        "width": width,
        "height": height,
        "turns": len(submessages(raw, 3)),
        "direction_validation": dict(direction_checks),
        "teams": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = []
    for path in args.paths:
        paths.extend(sorted(path.glob("*.replay26")) if path.is_dir() else [path])
    report = [analyze(path) for path in paths]
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
