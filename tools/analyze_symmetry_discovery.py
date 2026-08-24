"""Measure when team vision can prove map symmetry in replay files.

Only static terrain and the three possible enemy-Core footprints are evidence.
Dynamic buildings are deliberately ignored.  The targeted benchmark finds a
shortest two-waypoint walk by one scout whose endpoint observations, together
with initial Core vision, identify the symmetry. It uses the replay's hidden
terrain to choose those waypoints, so it is an oracle-assisted best case for
the value of active scouting, not a directly implementable policy.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from functools import lru_cache
from pathlib import Path
from statistics import median

from analyze_bean_openings import VISION_SQ
from analyze_mining_lanes import core_tiles, initial_state
from analyze_top_mining import Entity, message, parse_entity, pos, scalar, submessages


SYMMETRIES = ("MIRROR_X", "MIRROR_Y", "ROT_180")


def transform(p: tuple[int, int], kind: str, width: int, height: int):
    x, y = p
    if kind == "MIRROR_X":
        return width - 1 - x, y
    if kind == "MIRROR_Y":
        return x, height - 1 - y
    return width - 1 - x, height - 1 - y


def valid_symmetries(width, height, rows, cores):
    target = core_tiles(cores[1])
    matches = []
    for kind in SYMMETRIES:
        if {
            transform(p, kind, width, height) for p in core_tiles(cores[0])
        } != target:
            continue
        if all(
            rows[y][x] == rows[transform((x, y), kind, width, height)[1]][
                transform((x, y), kind, width, height)[0]
            ]
            for y in range(height)
            for x in range(width)
        ):
            matches.append(kind)
    if not matches:
        raise ValueError("no Core/terrain-compatible symmetry")
    return tuple(matches)


def identified(remaining, valid):
    """Strict inference: observations leave exactly one possible axis."""
    return len(remaining) == 1 and remaining[0] in valid


def core_compatible_symmetries(width: int, height: int, cores: dict[int, Entity]):
    """Useful diagnostic: axes possible from known dimensions/Core alone."""
    target = core_tiles(cores[1])
    return tuple(
        kind
        for kind in SYMMETRIES
        if {transform(p, kind, width, height) for p in core_tiles(cores[0])}
        == target
    )


@lru_cache(maxsize=None)
def vision_mask_at(kind, position, width, height):
    radius = VISION_SQ[kind]
    x, y = position
    sources = (
        ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1))
        if kind == "core"
        else ((x, y),)
    )
    mask = 0
    for tile_y in range(height):
        for tile_x in range(width):
            if min(
                (tile_x - source_x) ** 2 + (tile_y - source_y) ** 2
                for source_x, source_y in sources
            ) <= radius:
                mask |= 1 << (tile_y * width + tile_x)
    return mask


def vision_mask(entity: Entity, width: int, height: int) -> int:
    return vision_mask_at(entity.kind, entity.position, width, height)


def candidate_evidence(width, height, rows, cores, team):
    own = cores[team]
    enemy_tiles = core_tiles(cores[1 - team])
    mismatch_pairs = {}
    false_core_masks = {}
    for kind in SYMMETRIES:
        pairs = set()
        for y in range(height):
            for x in range(width):
                q = transform((x, y), kind, width, height)
                if rows[y][x] != rows[q[1]][q[0]]:
                    a, b = y * width + x, q[1] * width + q[0]
                    pairs.add((min(a, b), max(a, b)))
        mismatch_pairs[kind] = tuple(sorted(pairs))
        predicted = {
            transform(p, kind, width, height) for p in core_tiles(own)
        }
        disproving_tiles = predicted - enemy_tiles
        # Seeing the real enemy Core also disproves every hypothesis that
        # predicts its sole enemy Core somewhere else.
        if predicted != enemy_tiles:
            disproving_tiles |= enemy_tiles
        false_core_masks[kind] = sum(
            1 << (y * width + x) for x, y in disproving_tiles
        )
    return mismatch_pairs, false_core_masks


def remaining_candidates(observed, mismatch_pairs, false_core_masks):
    remaining = []
    for kind in SYMMETRIES:
        if observed & false_core_masks[kind]:
            continue
        if any(
            observed & (1 << a) and observed & (1 << b)
            for a, b in mismatch_pairs[kind]
        ):
            continue
        remaining.append(kind)
    return tuple(remaining)


def observe_team(entities, team, width, height):
    mask = 0
    for entity in entities.values():
        if entity.team == team and entity.kind in VISION_SQ:
            mask |= vision_mask(entity, width, height)
    return mask


def transformed_mask(observed, kind, width, height):
    result = 0
    bits = observed
    while bits:
        least = bits & -bits
        index = least.bit_length() - 1
        p = index % width, index // width
        x, y = transform(p, kind, width, height)
        result |= 1 << (y * width + x)
        bits ^= least
    return result


def analyze_replay(path: Path) -> dict:
    raw = path.read_bytes()
    width, height, rows, entities = initial_state(raw)
    cores = {entity.team: entity for entity in entities.values() if entity.kind == "core"}
    valid = valid_symmetries(width, height, rows, cores)
    evidence = {
        team: candidate_evidence(width, height, rows, cores, team)
        for team in (0, 1)
    }
    observed = {0: 0, 1: 0}
    inferred = {0: None, 1: None}
    inference_stats = {0: None, 1: None}
    local_observed = {entity_id: 0 for entity_id in entities}
    local_inferred = {0: None, 1: None}
    local_inferred_by = {0: None, 1: None}
    first_builder = {0: None, 1: None}

    turns = submessages(raw, 3)
    for turn_number, turn in enumerate(turns):
        for team in (0, 1):
            if inferred[team] is None:
                observed[team] |= observe_team(entities, team, width, height)
                candidates = remaining_candidates(observed[team], *evidence[team])
                if identified(candidates, valid):
                    inferred[team] = turn_number
                    gains = [
                        (transformed_mask(observed[team], kind, width, height)
                        & ~observed[team]).bit_count()
                        for kind in candidates
                    ]
                    inference_stats[team] = {
                        "observed_tiles": observed[team].bit_count(),
                        "newly_inferred_tiles_min": min(gains),
                        "newly_inferred_tiles_max": max(gains),
                    }
        for entity in entities.values():
            if entity.kind not in VISION_SQ or local_inferred[entity.team] is not None:
                continue
            local_observed.setdefault(entity.id, 0)
            local_observed[entity.id] |= vision_mask(entity, width, height)
            candidates = remaining_candidates(
                local_observed[entity.id], *evidence[entity.team]
            )
            if identified(candidates, valid):
                local_inferred[entity.team] = turn_number
                local_inferred_by[entity.team] = {
                    "entity_id": entity.id,
                    "kind": entity.kind,
                }

        for update in submessages(turn, 1):
            place = message(update, 1)
            if place is not None and message(place, 1) is not None:
                entity = parse_entity(message(place, 1))
                entities[entity.id] = entity
                local_observed[entity.id] = 0
                if entity.kind == "bot" and first_builder[entity.team] is None:
                    first_builder[entity.team] = {
                        "spawn_turn": turn_number,
                        "active_turn": turn_number + 1,
                        "position": entity.position,
                    }
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
        "valid_symmetries": valid,
        "core_compatible_symmetries": core_compatible_symmetries(
            width, height, cores
        ),
        "turns": len(turns),
        "rows": rows,
        "cores": {team: cores[team].position for team in (0, 1)},
        "teams": [
            {
                "team": team,
                "actual_inference_turn": inferred[team],
                "inference_stats": inference_stats[team],
                "local_inference_turn": local_inferred[team],
                "local_inferred_by": local_inferred_by[team],
                "first_builder": first_builder[team],
            }
            for team in (0, 1)
        ],
    }


def neighbours(p, width, height, blocked):
    x, y = p
    for q in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
        if 0 <= q[0] < width and 0 <= q[1] < height and q not in blocked:
            yield q


def bfs_distances(start, width, height, blocked):
    distance = {start: 0}
    queue = deque([start])
    while queue:
        p = queue.popleft()
        for q in neighbours(p, width, height, blocked):
            if q not in distance:
                distance[q] = distance[p] + 1
                queue.append(q)
    return distance


def targeted_scout_turns(game: dict, team: int) -> int | None:
    builder = game["teams"][team]["first_builder"]
    if builder is None:
        return None
    width, height, rows = game["width"], game["height"], game["rows"]
    cores = {
        side: Entity(side, side, tuple(game["cores"][side]), "core")
        for side in (0, 1)
    }
    mismatch_pairs, false_core_masks = candidate_evidence(
        width, height, rows, cores, team
    )
    valid = set(game["valid_symmetries"])
    if len(valid) != 1:
        return None
    core_seen = vision_mask(cores[team], width, height)
    if identified(
        remaining_candidates(core_seen, mismatch_pairs, false_core_masks), valid
    ):
        return 0

    blocked = {
        (x, y)
        for y, row in enumerate(rows)
        for x, value in enumerate(row)
        if value == 1
    }
    blocked |= core_tiles(cores[0]) | core_tiles(cores[1])
    start = tuple(builder["position"])
    blocked.discard(start)
    from_start = bfs_distances(start, width, height, blocked)
    positions = sorted(from_start, key=lambda p: (from_start[p], p))
    scout_masks = {
        p: vision_mask_at("bot", p, width, height)
        for p in positions
    }

    false_kinds = tuple(kind for kind in SYMMETRIES if kind not in valid)

    def eliminated(observed, kind):
        if observed & false_core_masks[kind]:
            return True
        return any(
            observed & (1 << a) and observed & (1 << b)
            for a, b in mismatch_pairs[kind]
        )

    base_eliminated = {
        p: {kind for kind in false_kinds if eliminated(core_seen | scout_masks[p], kind)}
        for p in positions
    }

    best = None
    for p in positions:
        known = core_seen | scout_masks[p]
        if len(base_eliminated[p]) == len(false_kinds):
            best = from_start[p] if best is None else min(best, from_start[p])
    if best == 0:
        return 0

    # Two observation waypoints. Distances are computed lazily per first point.
    for p in positions:
        if best is not None and from_start[p] >= best:
            break
        known_p = core_seen | scout_masks[p]
        cross_needed = {}
        for kind in false_kinds:
            needed = 0
            for a, b in mismatch_pairs[kind]:
                if known_p & (1 << a):
                    needed |= 1 << b
                if known_p & (1 << b):
                    needed |= 1 << a
            cross_needed[kind] = needed
        distances = bfs_distances(p, width, height, blocked)
        for q in positions:
            cost = from_start[p] + distances.get(q, 10**9)
            if best is not None and cost >= best:
                continue
            eliminated_kinds = base_eliminated[p] | base_eliminated[q]
            if all(
                kind in eliminated_kinds
                or bool(cross_needed[kind] & scout_masks[q])
                for kind in false_kinds
            ):
                best = cost
    return best


def size_bin(width, height):
    area = width * height
    if area <= 400:
        return "small (<=400)"
    if area <= 600:
        return "medium (401-600)"
    return "large (>600)"


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def summarize(records):
    groups = {"all": records}
    for field in ("size_bin", "symmetry", "map_name"):
        for value in sorted({record[field] for record in records}):
            groups[f"{field}:{value}"] = [r for r in records if r[field] == value]
    output = {}
    for label, rows in groups.items():
        actual = [r["actual_turn"] for r in rows if r["actual_turn"] is not None]
        local = [r["local_turn"] for r in rows if r["local_turn"] is not None]
        targeted = [r["targeted_absolute_turn"] for r in rows if r["targeted_absolute_turn"] is not None]
        gains = [
            r["actual_inference_stats"]["newly_inferred_tiles_max"]
            for r in rows
            if r["actual_inference_stats"] is not None
        ]
        output[label] = {
            "team_sides": len(rows),
            "actual_inferred": len(actual),
            "actual_inferred_rate": round(len(actual) / len(rows), 3),
            "actual_by_10": round(sum(v <= 10 for v in actual) / len(rows), 3),
            "actual_by_20": round(sum(v <= 20 for v in actual) / len(rows), 3),
            "actual_by_30": round(sum(v <= 30 for v in actual) / len(rows), 3),
            "actual_median_inferred_only": median(actual) if actual else None,
            "actual_p75_inferred_only": percentile(actual, 0.75),
            "local_inferred_rate": round(len(local) / len(rows), 3),
            "local_median_inferred_only": median(local) if local else None,
            "local_p75_inferred_only": percentile(local, 0.75),
            "targeted_median_absolute": median(targeted) if targeted else None,
            "targeted_p75_absolute": percentile(targeted, 0.75),
            "median_new_tiles_revealed_at_actual_inference": (
                median(gains) if gains else None
            ),
        }
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path, help="analysis.json from analyze_top_mining.py")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    metadata = json.loads(args.dataset.read_text())
    directory = args.dataset.parent
    game_meta = {
        (game["match_id"], game["game_number"]): game
        for game in metadata["games"]
    }
    cache = {}
    records = []
    for path in sorted(directory.glob("*.replay26")):
        match_id = path.name.split("_game_")[0]
        number = int(path.stem.rsplit("_", 1)[1])
        meta = game_meta.get((match_id, number))
        if meta is None:
            continue
        game = analyze_replay(path)
        for team in (0, 1):
            builder = game["teams"][team]["first_builder"]
            key = (
                tuple(map(tuple, game["rows"])),
                tuple(game["cores"][team]),
                tuple(builder["position"]) if builder else None,
            )
            if key not in cache:
                cache[key] = targeted_scout_turns(game, team)
            relative = cache[key]
            active = builder["active_turn"] if builder else None
            records.append(
                {
                    "match_id": match_id,
                    "game_number": number,
                    "map_name": meta.get("map_name") or "unknown",
                    "width": game["width"],
                    "height": game["height"],
                    "size_bin": size_bin(game["width"], game["height"]),
                    "symmetry": "+".join(game["valid_symmetries"]),
                    "valid_symmetry_count": len(game["valid_symmetries"]),
                    "core_compatible_count": len(game["core_compatible_symmetries"]),
                    "team": team,
                    "team_name": meta.get("team_a") if team == 0 else meta.get("team_b"),
                    "game_turns": game["turns"],
                    "actual_turn": game["teams"][team]["actual_inference_turn"],
                    "actual_inference_stats": game["teams"][team]["inference_stats"],
                    "local_turn": game["teams"][team]["local_inference_turn"],
                    "local_inferred_by": game["teams"][team]["local_inferred_by"],
                    "first_builder_active_turn": active,
                    "targeted_scout_moves": relative,
                    "targeted_absolute_turn": (
                        0
                        if relative == 0
                        else active + relative
                        if active is not None and relative is not None
                        else None
                    ),
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
