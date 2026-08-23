"""Measure when a team commits to its rush (first aggression) across replays.

Offline analysis utility, not bot code. Reuses the minimal replay protobuf
reader from analyze_top_mining.py.
"""

from __future__ import annotations

import argparse
import json
import statistics
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

# Turrets that deal damage. Launchers throw builder bots and do no damage,
# but are a rush enabler, so they are tracked separately.
DAMAGE_TURRETS = {"gunner", "sentinel"}
COMBAT_KINDS = DAMAGE_TURRETS | {"launcher"}


@dataclass
class Entity:
    id: int
    team: int
    position: tuple[int, int]
    kind: str
    direction: int = 0


def parse_entity(buf: bytes) -> Entity:
    by_number = defaultdict(list)
    for number, value in fields(buf):
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


def dist2(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def parse_map(map_buf: bytes) -> tuple[int, int, dict[int, tuple[int, int]], dict[int, int]]:
    """Return width, height, team -> core position, and entity_id -> team for cores.

    Cores are implicit: they never appear as place updates. Their spawn position
    comes from the map's player-spawn records, and their entity ids are the
    spawn record ids (1 and 2).
    """
    width, height = scalar(map_buf, 1), scalar(map_buf, 2)
    cores: dict[int, tuple[int, int]] = {}
    core_ids: dict[int, int] = {}
    for spawn in submessages(map_buf, 4):
        entity_id = scalar(spawn, 1)
        team = scalar(spawn, 2)
        cores[team] = pos(message(spawn, 3))
        core_ids[entity_id] = team
    return width, height, cores, core_ids


def parse_replay(path: Path) -> dict:
    raw = path.read_bytes()
    width, height, cores, core_ids = parse_map(message(raw, 1) or b"")
    turns = submessages(raw, 3)
    winner_field = scalar(raw, 4, -1)
    win_condition = next(
        (v.decode() for n, v in fields(raw) if n == 6 and isinstance(v, bytes)), None
    )

    teams = (0, 1)
    entities: dict[int, Entity] = {
        eid: Entity(id=eid, team=team, position=cores[team], kind="core")
        for eid, team in core_ids.items()
    }

    first_build = {t: {} for t in teams}
    first_damage_turret = {t: None for t in teams}
    first_forward_turret = {t: None for t in teams}
    first_bot_enemy_half = {t: None for t in teams}
    first_bot_leaves_home = {t: None for t in teams}
    first_turret_near_core = {t: None for t in teams}
    first_kill = {t: None for t in teams}
    turret_builds = {t: [] for t in teams}
    state_at_rush = {t: None for t in teams}
    titanium = {t: 350 for t in teams}
    peak_bots = {t: 0 for t in teams}
    core_lost = {t: None for t in teams}

    def side_frac(p: tuple[int, int], team: int) -> float | None:
        """0.0 on own core, 1.0 on enemy core: projection onto the core-to-core axis."""
        own, enemy = cores.get(team), cores.get(1 - team)
        if own is None or enemy is None:
            return None
        vx, vy = enemy[0] - own[0], enemy[1] - own[1]
        span = vx * vx + vy * vy
        if span == 0:
            return None
        return ((p[0] - own[0]) * vx + (p[1] - own[1]) * vy) / span

    def enemy_core_dist(p: tuple[int, int], team: int) -> float | None:
        enemy = cores.get(1 - team)
        return None if enemy is None else dist2(p, enemy) ** 0.5

    for turn_number, turn in enumerate(turns):
        for update in submessages(turn, 1):
            for number, payload in fields(update):
                if not isinstance(payload, bytes):
                    continue

                if number == 1:  # place entity
                    entity_buf = message(payload, 1)
                    if entity_buf is None:
                        continue
                    e = parse_entity(entity_buf)
                    entities[e.id] = e
                    t = e.team
                    first_build[t].setdefault(e.kind, turn_number)
                    frac = side_frac(e.position, t)
                    dist = enemy_core_dist(e.position, t)
                    if e.kind in COMBAT_KINDS:
                        turret_builds[t].append(
                            (turn_number, e.kind, None if frac is None else round(frac, 3),
                             None if dist is None else round(dist, 1))
                        )
                    if e.kind in DAMAGE_TURRETS:
                        if first_damage_turret[t] is None:
                            first_damage_turret[t] = turn_number
                            counts = Counter(
                                x.kind for x in entities.values() if x.team == t
                            )
                            state_at_rush[t] = {
                                "counts": dict(counts),
                                "titanium": titanium[t],
                                "frac": None if frac is None else round(frac, 3),
                                "enemy_core_dist": None if dist is None else round(dist, 1),
                            }
                        if frac is not None and frac > 0.5 and first_forward_turret[t] is None:
                            first_forward_turret[t] = turn_number
                        if dist is not None and dist <= 5 and first_turret_near_core[t] is None:
                            first_turret_near_core[t] = turn_number

                elif number == 2:  # move
                    e = entities.get(scalar(payload, 1))
                    if e is None:
                        continue
                    e.position = pos(message(payload, 2))
                    if e.kind != "bot":
                        continue
                    frac = side_frac(e.position, e.team)
                    if frac is None:
                        continue
                    if frac > 0.5 and first_bot_enemy_half[e.team] is None:
                        first_bot_enemy_half[e.team] = turn_number
                    if frac > 0.25 and first_bot_leaves_home[e.team] is None:
                        first_bot_leaves_home[e.team] = turn_number

                elif number == 3:  # remove
                    removed = entities.pop(scalar(payload, 1), None)
                    if removed is None:
                        continue
                    victim = removed.team
                    if removed.kind == "core":
                        core_lost[victim] = turn_number
                    # Builder bots also expire naturally, so only buildings count as kills.
                    if removed.kind != "bot" and first_kill[1 - victim] is None:
                        first_kill[1 - victim] = turn_number

                elif number == 6:  # player state
                    players = message(payload, 1) or b""
                    for t, num in ((0, 1), (1, 2)):
                        player = message(players, num)
                        if player is None:
                            continue
                        titanium[t] = scalar(player, 1)

        for t in teams:
            bots = sum(1 for x in entities.values() if x.team == t and x.kind == "bot")
            peak_bots[t] = max(peak_bots[t], bots)

    final = {t: dict(Counter(x.kind for x in entities.values() if x.team == t)) for t in teams}
    return {
        "file": path.name,
        "width": width,
        "height": height,
        "area": width * height,
        "cores": {str(t): list(p) for t, p in cores.items()},
        "core_separation": round(dist2(cores[0], cores[1]) ** 0.5, 2) if len(cores) == 2 else None,
        "turns": len(turns),
        "replay_winner": winner_field,
        "replay_win_condition": win_condition,
        "teams": [
            {
                "first_build": first_build[t],
                "first_damage_turret": first_damage_turret[t],
                "first_forward_turret": first_forward_turret[t],
                "first_turret_near_enemy_core": first_turret_near_core[t],
                "first_bot_leaves_home": first_bot_leaves_home[t],
                "first_bot_enemy_half": first_bot_enemy_half[t],
                "first_kill": first_kill[t],
                "turret_builds": turret_builds[t],
                "state_at_rush": state_at_rush[t],
                "titanium_end": titanium[t],
                "peak_bots": peak_bots[t],
                "core_lost_round": core_lost[t],
                "final": final[t],
            }
            for t in teams
        ],
    }


def team_matches(team_id: str, wanted: int, match_types: list[str]) -> list[dict]:
    matches: list[dict] = []
    for match_type in match_types:
        cursor = None
        while len(matches) < wanted:
            params = {"limit": "100", "type": match_type, "teamId": team_id}
            if cursor:
                params["cursor"] = cursor
            page = api_get("/api/matches", params)
            rows = [
                r for r in page.get("matches", [])
                if team_id in (r.get("teamAId"), r.get("teamBId"))
                and r.get("status") == "complete"
            ]
            matches.extend(rows)
            cursor = page.get("nextCursor")
            if not cursor:
                break
    seen, unique = set(), []
    for row in matches:
        if row["id"] not in seen:
            seen.add(row["id"])
            unique.append(row)
    unique.sort(key=lambda r: r.get("completedAt") or r.get("createdAt") or "", reverse=True)
    return unique[:wanted]


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


def describe(values: list[int], label: str) -> dict:
    values = [v for v in values if v is not None]
    if not values:
        return {"label": label, "n": 0}
    values_sorted = sorted(values)
    return {
        "label": label,
        "n": len(values),
        "mean": round(statistics.mean(values), 1),
        "median": statistics.median(values),
        "stdev": round(statistics.stdev(values), 1) if len(values) > 1 else 0.0,
        "min": values_sorted[0],
        "p25": values_sorted[len(values_sorted) // 4],
        "p75": values_sorted[(3 * len(values_sorted)) // 4],
        "max": values_sorted[-1],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--team-name", default="")
    parser.add_argument("--matches", type=int, default=20)
    parser.add_argument("--types", default="ladder")
    parser.add_argument("--output", type=Path, default=Path("scratch/rush_dataset"))
    args = parser.parse_args()

    match_types = [v.strip() for v in args.types.split(",") if v.strip()]
    matches = team_matches(args.team_id, args.matches, match_types)
    metadata = download_matches(matches, args.output)
    by_id = {item["match"]["id"]: item for item in metadata}

    games = []
    for path in sorted(args.output.glob("*.replay26")):
        match_id = path.name.split("_game_")[0]
        if match_id not in by_id:
            continue
        game_number = int(path.stem.rsplit("_", 1)[1])
        detail = by_id[match_id]
        match_row = detail["match"]
        game = next((g for g in detail["games"] if g["gameNumber"] == game_number), None)
        if game is None:
            continue
        result = parse_replay(path)
        side = 0 if match_row.get("teamAId") == args.team_id else 1
        result.update(
            match_id=match_id,
            game_number=game_number,
            map_name=game.get("mapName"),
            team_a=match_row.get("teamAName"),
            team_b=match_row.get("teamBName"),
            subject_side=side,
            opponent=match_row.get("teamBName") if side == 0 else match_row.get("teamAName"),
            winner_side=game.get("winnerSide"),
            win_condition=game.get("winCondition"),
        )
        games.append(result)

    report = {
        "team_id": args.team_id,
        "team_name": args.team_name,
        "match_types": match_types,
        "matches": len(metadata),
        "games": games,
        "match_meta": metadata,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / "rush_analysis.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"matches={len(metadata)} games={len(games)} -> {report_path}")


if __name__ == "__main__":
    main()
