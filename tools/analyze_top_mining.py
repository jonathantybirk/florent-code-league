"""Download and summarize recent top-vs-top Florent Code League replays.

This is an offline analysis utility, not bot code. It intentionally implements
only the small subset of the replay protobuf needed for mining/logistics study.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from fcode.api import api_get


def varint(buf: bytes, i: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = buf[i]
        i += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, i
        shift += 7


def fields(buf: bytes):
    i = 0
    while i < len(buf):
        key, i = varint(buf, i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, i = varint(buf, i)
        elif wire == 1:
            value, i = buf[i : i + 8], i + 8
        elif wire == 2:
            length, i = varint(buf, i)
            value, i = buf[i : i + length], i + length
        elif wire == 5:
            value, i = buf[i : i + 4], i + 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        yield number, value


def submessages(buf: bytes, number: int) -> list[bytes]:
    return [v for n, v in fields(buf) if n == number and isinstance(v, bytes)]


def scalar(buf: bytes, number: int, default: int = 0) -> int:
    for n, value in fields(buf):
        if n == number and isinstance(value, int):
            return value
    return default


def message(buf: bytes, number: int) -> bytes | None:
    values = submessages(buf, number)
    return values[-1] if values else None


def pos(buf: bytes | None) -> tuple[int, int]:
    return (scalar(buf or b"", 1), scalar(buf or b"", 2))


KIND_FIELDS = {
    10: "bot",
    11: "conveyor",
    12: "splitter",
    15: "harvester",
    18: "barrier",
    20: "core",
    21: "gunner",
    22: "sentinel",
    24: "launcher",
}


@dataclass
class Entity:
    id: int
    team: int
    position: tuple[int, int]
    kind: str
    direction: int = 0


def parse_entity(buf: bytes) -> Entity:
    values = list(fields(buf))
    by_number = defaultdict(list)
    for number, value in values:
        by_number[number].append(value)
    kind_field = next(number for number in KIND_FIELDS if number in by_number)
    kind_payload = by_number[kind_field][-1]
    direction = scalar(kind_payload, 1) if isinstance(kind_payload, bytes) else 0
    return Entity(
        id=scalar(buf, 1),
        team=scalar(buf, 2),
        position=pos(message(buf, 3)),
        kind=KIND_FIELDS[kind_field],
        direction=direction,
    )


DIR_DELTA = {1: (0, -1), 3: (1, 0), 5: (0, 1), 7: (-1, 0)}


def size_bin(width: int, height: int) -> str:
    area = width * height
    if area <= 400:
        return "small (<=400)"
    if area <= 600:
        return "medium (401-600)"
    return "large (>600)"


def network_sharing(entities: dict[int, Entity]) -> dict[int, tuple[int, int]]:
    """Return team -> (largest harvester fan-in, shared conveyor tiles)."""
    by_team_pos: dict[int, dict[tuple[int, int], Entity]] = {0: {}, 1: {}}
    for entity in entities.values():
        by_team_pos[entity.team][entity.position] = entity

    result = {}
    for team in (0, 1):
        largest = shared_tiles = 0
        grid = by_team_pos[team]
        conveyors = {p: e for p, e in grid.items() if e.kind == "conveyor"}
        reached_by: dict[tuple[int, int], set[int]] = defaultdict(set)
        harvesters = [e for e in grid.values() if e.kind == "harvester"]
        for harvester in harvesters:
            frontier = []
            hx, hy = harvester.position
            for dx, dy in DIR_DELTA.values():
                start = (hx + dx, hy + dy)
                if start in conveyors:
                    frontier.append(start)
            seen = set()
            while frontier:
                current = frontier.pop()
                if current in seen:
                    continue
                seen.add(current)
                reached_by[current].add(harvester.id)
                conveyor = conveyors[current]
                delta = DIR_DELTA.get(conveyor.direction)
                if delta:
                    nxt = (current[0] + delta[0], current[1] + delta[1])
                    if nxt in conveyors:
                        frontier.append(nxt)
        if reached_by:
            largest = max(len(ids) for ids in reached_by.values())
            shared_tiles = sum(len(ids) > 1 for ids in reached_by.values())
        result[team] = (largest, shared_tiles)
    return result


def parse_replay(path: Path) -> dict:
    raw = path.read_bytes()
    map_buf = message(raw, 1) or b""
    width, height = scalar(map_buf, 1), scalar(map_buf, 2)
    turns = submessages(raw, 3)
    entities: dict[int, Entity] = {}
    built = {team: Counter() for team in (0, 1)}
    build_turns = {team: defaultdict(list) for team in (0, 1)}
    first = {team: {} for team in (0, 1)}
    peak = {team: Counter() for team in (0, 1)}
    titanium_collected = {0: 0, 1: 0}
    first_titanium_collected = {0: None, 1: None}
    checkpoints = {0: {}, 1: {}}
    resource_arrivals_at_core = {0: 0, 1: 0}
    max_fanin = {0: 0, 1: 0}
    max_shared_tiles = {0: 0, 1: 0}

    def update_network_metrics():
        for team, (fanin, shared) in network_sharing(entities).items():
            max_fanin[team] = max(max_fanin[team], fanin)
            max_shared_tiles[team] = max(max_shared_tiles[team], shared)

    for turn_number, turn in enumerate(turns):
        topology_changed = False
        for update in submessages(turn, 1):
            place = message(update, 1)
            if place is not None:
                entity_buf = message(place, 1)
                if entity_buf is not None:
                    entity = parse_entity(entity_buf)
                    entities[entity.id] = entity
                    if entity.kind != "core":
                        built[entity.team][entity.kind] += 1
                        build_turns[entity.team][entity.kind].append(turn_number)
                        first[entity.team].setdefault(entity.kind, turn_number)
                    topology_changed |= entity.kind in {"conveyor", "splitter", "harvester"}
                continue

            move = message(update, 2)
            if move is not None:
                entity_id = scalar(move, 1)
                if entity_id in entities:
                    entities[entity_id].position = pos(message(move, 2))
                continue

            remove = message(update, 3)
            if remove is not None:
                entity_id = scalar(remove, 1)
                removed = entities.pop(entity_id, None)
                topology_changed |= bool(removed and removed.kind in {"conveyor", "splitter", "harvester"})
                continue

            distribute = message(update, 4)
            if distribute is not None:
                core_tiles = {
                    team: {
                        (e.position[0] + dx, e.position[1] + dy)
                        for e in entities.values()
                        if e.team == team and e.kind == "core"
                        for dx in (0, 1)
                        for dy in (0, 1)
                    }
                    for team in (0, 1)
                }
                for resource_move in submessages(distribute, 1):
                    destination = pos(message(resource_move, 2))
                    for team in (0, 1):
                        if destination in core_tiles[team]:
                            resource_arrivals_at_core[team] += 1
                continue

            players_update = message(update, 6)
            if players_update is not None:
                players = message(players_update, 1) or b""
                for team, field_number in ((0, 1), (1, 2)):
                    player = message(players, field_number)
                    if player is not None:
                        titanium_collected[team] = scalar(player, 4)
                        if titanium_collected[team] > 0 and first_titanium_collected[team] is None:
                            first_titanium_collected[team] = turn_number

        live = {team: Counter(e.kind for e in entities.values() if e.team == team) for team in (0, 1)}
        for team in (0, 1):
            for kind, count in live[team].items():
                peak[team][kind] = max(peak[team][kind], count)
            if turn_number in {10, 25, 50, 100, 200}:
                checkpoints[team][str(turn_number)] = {
                    "live": dict(live[team]),
                    "titanium_collected": titanium_collected[team],
                }
        if topology_changed:
            update_network_metrics()

    final = {team: Counter(e.kind for e in entities.values() if e.team == team) for team in (0, 1)}
    return {
        "file": path.name,
        "width": width,
        "height": height,
        "area": width * height,
        "size_bin": size_bin(width, height),
        "turns": len(turns),
        "teams": [
            {
                "built": dict(built[team]),
                "build_turns": {kind: turns for kind, turns in build_turns[team].items()},
                "first": first[team],
                "peak": dict(peak[team]),
                "final": dict(final[team]),
                "titanium_collected": titanium_collected[team],
                "first_titanium_collected": first_titanium_collected[team],
                "checkpoints": checkpoints[team],
                "core_arrival_events": resource_arrivals_at_core[team],
                "max_harvester_fanin": max_fanin[team],
                "max_shared_conveyor_tiles": max_shared_tiles[team],
            }
            for team in (0, 1)
        ],
    }


def collect_top_matches(top_n: int, wanted: int, match_types: list[str]) -> tuple[list[dict], dict[str, dict]]:
    ladder_response = api_get("/api/ladder", {"limit": str(top_n)})
    if isinstance(ladder_response, list):
        ladder = ladder_response[:top_n]
    else:
        ladder = (ladder_response.get("teams") or ladder_response.get("rankings") or [])[:top_n]
    top = {row.get("teamId") or row.get("id"): row for row in ladder}
    matches = []
    cursors = {match_type: None for match_type in match_types}
    exhausted = set()
    while len(matches) < wanted:
        candidates = []
        for match_type in match_types:
            if match_type in exhausted:
                continue
            params = {"limit": "100", "type": match_type}
            if cursors[match_type]:
                params["cursor"] = cursors[match_type]
            page = api_get("/api/matches", params)
            candidates.extend(
                row for row in page.get("matches", [])
                if row.get("teamAId") in top and row.get("teamBId") in top
            )
            cursors[match_type] = page.get("nextCursor")
            if not cursors[match_type]:
                exhausted.add(match_type)
        known = {row["id"] for row in matches}
        matches.extend(row for row in candidates if row["id"] not in known)
        matches.sort(key=lambda row: row.get("completedAt") or row.get("createdAt") or "", reverse=True)
        if len(matches) >= wanted:
            matches = matches[:wanted]
            break
        if len(exhausted) == len(match_types):
            break
    return matches, top


def download_matches(matches: list[dict], output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = []
    for match_row in matches:
        match_id = match_row["id"]
        detail = api_get(f"/api/matches/{match_id}")
        for key, value in match_row.items():
            if value is not None and detail["match"].get(key) is None:
                detail["match"][key] = value
        metadata.append(detail)
        for game in detail.get("games", []):
            number = game["gameNumber"]
            target = output_dir / f"{match_id}_game_{number}.replay26"
            if target.exists():
                continue
            replay = api_get("/api/matches/replay", {"matchId": match_id, "game": str(number)})
            urllib.request.urlretrieve(replay["url"], target)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=30)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--types", default="ladder,unrated")
    parser.add_argument("--output", type=Path, default=Path("scratch/top_mining_dataset"))
    args = parser.parse_args()

    match_types = [value.strip() for value in args.types.split(",") if value.strip()]
    matches, top = collect_top_matches(args.top, args.matches, match_types)
    metadata = download_matches(matches, args.output)
    by_id = {item["match"]["id"]: item for item in metadata}
    analyses = []
    selected_ids = set(by_id)
    replay_paths = sorted(
        path for path in args.output.glob("*.replay26")
        if path.name.split("_game_")[0] in selected_ids
    )
    for replay_path in replay_paths:
        match_id = replay_path.name.split("_game_")[0]
        game_number = int(replay_path.stem.rsplit("_", 1)[1])
        result = parse_replay(replay_path)
        detail = by_id[match_id]
        match_row = detail["match"]
        game = next(g for g in detail["games"] if g["gameNumber"] == game_number)
        result.update(
            match_id=match_id,
            game_number=game_number,
            map_name=game.get("mapName"),
            team_a=match_row.get("teamAName"),
            team_b=match_row.get("teamBName"),
            winner_side=game.get("winnerSide"),
            win_condition=game.get("winCondition"),
        )
        analyses.append(result)

    report = {
        "top_n": args.top,
        "requested_matches": args.matches,
        "match_types": match_types,
        "downloaded_matches": len(metadata),
        "downloaded_games": len(analyses),
        "teams": top,
        "matches": metadata,
        "games": analyses,
    }
    report_path = args.output / "analysis.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Downloaded {len(metadata)} matches / analyzed {len(analyses)} games")
    print(report_path)


if __name__ == "__main__":
    main()
