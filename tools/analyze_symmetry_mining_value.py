"""Upper-bound mining value of knowing symmetry at fixed opening turns."""

from __future__ import annotations

import argparse
import json
from collections import Counter, deque
from pathlib import Path
from statistics import median

from analyze_mining_lanes import core_tiles, initial_state
from analyze_symmetry_discovery import (
    SYMMETRIES,
    observe_team,
    transform,
    valid_symmetries,
)
from analyze_top_mining import message, parse_entity, pos, scalar, submessages


CHECKPOINTS = (6, 10, 20, 30)


def distances(width, height, rows, starts):
    result = {p: 0 for p in starts}
    queue = deque(starts)
    while queue:
        x, y = queue.popleft()
        for p in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if not (0 <= p[0] < width and 0 <= p[1] < height):
                continue
            if rows[p[1]][p[0]] == 1 or p in result:
                continue
            result[p] = result[(x, y)] + 1
            queue.append(p)
    return result


def observed_positions(mask, width):
    while mask:
        least = mask & -mask
        index = least.bit_length() - 1
        yield index % width, index // width
        mask ^= least


def territory(tile, own_distance, enemy_distance):
    ours = own_distance.get(tile, 10**9)
    enemy = enemy_distance.get(tile, 10**9)
    margin = enemy - ours
    if margin >= 4:
        return "ours"
    if margin >= -3:
        return "contested"
    return "enemy"


def checkpoint_snapshot(
    team,
    turn,
    width,
    height,
    ores,
    observed,
    entities,
    own_distance,
    enemy_distance,
    axis,
):
    known = ores.intersection(observed_positions(observed, width))
    inferred = {transform(tile, axis, width, height) for tile in known} - known
    inferred &= ores
    occupied_harvesters = {
        entity.position
        for entity in entities.values()
        if entity.kind == "harvester"
    }
    known_open = known - occupied_harvesters
    by_territory = Counter(
        territory(tile, own_distance, enemy_distance) for tile in inferred
    )
    known_by_territory = Counter(
        territory(tile, own_distance, enemy_distance) for tile in known_open
    )
    inferred_distances = sorted(own_distance.get(tile, 10**9) for tile in inferred)
    inferred_useful = {
        tile
        for tile in inferred
        if territory(tile, own_distance, enemy_distance) != "enemy"
    }
    return {
        "turn": turn,
        "known_ores": len(known),
        "known_open_ours": known_by_territory["ours"],
        "known_open_contested": known_by_territory["contested"],
        "inferred_ores": len(inferred),
        "inferred_ours": by_territory["ours"],
        "inferred_contested": by_territory["contested"],
        "inferred_enemy": by_territory["enemy"],
        "inferred_within_8": sum(own_distance.get(tile, 10**9) <= 8 for tile in inferred_useful),
        "inferred_within_12": sum(own_distance.get(tile, 10**9) <= 12 for tile in inferred_useful),
        "inferred_within_16": sum(own_distance.get(tile, 10**9) <= 16 for tile in inferred_useful),
        "nearest_inferred_useful_distance": min(
            (own_distance.get(tile, 10**9) for tile in inferred_useful),
            default=None,
        ),
        "active_builders": sum(
            entity.team == team and entity.kind == "bot"
            for entity in entities.values()
        ),
    }


def analyze_replay(path):
    raw = path.read_bytes()
    width, height, rows, entities = initial_state(raw)
    cores = {entity.team: entity for entity in entities.values() if entity.kind == "core"}
    axes = valid_symmetries(width, height, rows, cores)
    if len(axes) != 1:
        return None
    axis = axes[0]
    ores = {
        (x, y)
        for y, row in enumerate(rows)
        for x, value in enumerate(row)
        if value == 2
    }
    paths = {
        team: (
            distances(width, height, rows, core_tiles(cores[team])),
            distances(width, height, rows, core_tiles(cores[1 - team])),
        )
        for team in (0, 1)
    }
    observed = {0: 0, 1: 0}
    checkpoints = {0: {}, 1: {}}
    discovery = {0: {}, 1: {}}
    turns = submessages(raw, 3)
    for turn_number, turn in enumerate(turns):
        for team in (0, 1):
            observed[team] |= observe_team(entities, team, width, height)
            for ore in ores.intersection(observed_positions(observed[team], width)):
                discovery[team].setdefault(ore, turn_number)
            if turn_number in CHECKPOINTS:
                checkpoints[team][turn_number] = checkpoint_snapshot(
                    team,
                    turn_number,
                    width,
                    height,
                    ores,
                    observed[team],
                    entities,
                    *paths[team],
                    axis,
                )
        for update in submessages(turn, 1):
            place = message(update, 1)
            if place is not None and message(place, 1) is not None:
                entity = parse_entity(message(place, 1))
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
    return {
        "width": width,
        "height": height,
        "teams": checkpoints,
    }


def summarize(records):
    output = {}
    for turn in CHECKPOINTS:
        rows = [record["checkpoints"].get(turn) for record in records]
        rows = [row for row in rows if row is not None]
        if not rows:
            continue
        starved = [
            row
            for row in rows
            if row["known_open_ours"] + row["known_open_contested"] == 0
        ]
        helped = [
            row
            for row in starved
            if row["inferred_ours"] + row["inferred_contested"] > 0
        ]
        useful_distances = [
            row["nearest_inferred_useful_distance"]
            for row in rows
            if row["nearest_inferred_useful_distance"] is not None
        ]
        output[turn] = {
            "team_sides": len(rows),
            "zero_known_open_useful_targets": len(starved),
            "zero_target_rate": round(len(starved) / len(rows), 3),
            "symmetry_helps_zero_target_cases": len(helped),
            "help_rate_among_zero_target": (
                round(len(helped) / len(starved), 3) if starved else 0
            ),
            "any_additional_ours_rate": round(
                sum(row["inferred_ours"] > 0 for row in rows) / len(rows), 3
            ),
            "any_additional_non_enemy_rate": round(
                sum(
                    row["inferred_ours"] + row["inferred_contested"] > 0
                    for row in rows
                )
                / len(rows),
                3,
            ),
            "additional_within_8_rate": round(
                sum(row["inferred_within_8"] > 0 for row in rows) / len(rows), 3
            ),
            "additional_within_12_rate": round(
                sum(row["inferred_within_12"] > 0 for row in rows) / len(rows), 3
            ),
            "median_nearest_additional_useful_distance": (
                median(useful_distances) if useful_distances else None
            ),
            "median_known_open_useful_targets": median(
                [row["known_open_ours"] + row["known_open_contested"] for row in rows]
            ),
        }
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    metadata = json.loads(args.dataset.read_text())
    game_meta = {
        (game["match_id"], game["game_number"]): game
        for game in metadata["games"]
    }
    records = []
    for path in sorted(args.dataset.parent.glob("*.replay26")):
        match_id = path.name.split("_game_")[0]
        game_number = int(path.stem.rsplit("_", 1)[1])
        meta = game_meta.get((match_id, game_number))
        if meta is None:
            continue
        game = analyze_replay(path)
        if game is None:
            continue
        for team in (0, 1):
            records.append(
                {
                    "match_id": match_id,
                    "game_number": game_number,
                    "map_name": meta["map_name"],
                    "team": team,
                    "width": game["width"],
                    "height": game["height"],
                    "checkpoints": game["teams"][team],
                }
            )
    report = {"records": records, "summary": summarize(records)}
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n")
        print(args.output)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
