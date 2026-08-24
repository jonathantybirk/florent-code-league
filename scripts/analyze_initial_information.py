#!/usr/bin/env python3
"""Analyze round-one and early-game information on bundled Florent maps.

This script does not prescribe map-specific play. It uses the current map pool
as test data for generic inferences based on dimensions, Core position, visible
terrain, and the official symmetry guarantee.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from analyze_opening_economy import Core, GameMap, parse_map


Position = tuple[int, int]
Transform = Callable[[Position], Position]


@dataclass(frozen=True)
class InitialInformation:
    map: str
    team: int
    width: int
    height: int
    core_x: int
    core_y: int
    actual_symmetry: str
    visible_tiles: int
    visible_ore: int
    visible_walls: int
    legal_spawn_tiles: int
    generic_symmetry_candidates: str
    generic_enemy_core_candidates: str
    pool_candidates_dimensions: int
    pool_candidates_dimensions_core: int
    pool_candidates_full_observation: int


def transformations(game_map: GameMap) -> dict[str, Transform]:
    width, height = game_map.width, game_map.height
    return {
        "rotate_180": lambda position: (
            width - 1 - position[0],
            height - 1 - position[1],
        ),
        "mirror_x": lambda position: (width - 1 - position[0], position[1]),
        "mirror_y": lambda position: (position[0], height - 1 - position[1]),
    }


def transform_core(core: Core, name: str, game_map: GameMap) -> Core:
    if name == "rotate_180":
        return Core(core.owner, game_map.width - 2 - core.x, game_map.height - 2 - core.y)
    if name == "mirror_x":
        return Core(core.owner, game_map.width - 2 - core.x, core.y)
    if name == "mirror_y":
        return Core(core.owner, core.x, game_map.height - 2 - core.y)
    raise ValueError(name)


def actual_symmetries(game_map: GameMap) -> list[str]:
    first, second = game_map.cores
    result: list[str] = []
    for name, transform in transformations(game_map).items():
        terrain_matches = all(
            game_map.rows[y][x] == game_map.rows[transform((x, y))[1]][transform((x, y))[0]]
            for y in range(game_map.height)
            for x in range(game_map.width)
        )
        predicted = transform_core(first, name, game_map)
        cores_match = (predicted.x, predicted.y) == (second.x, second.y)
        if terrain_matches and cores_match:
            result.append(name)
    return result


def visible_tiles(game_map: GameMap, core: Core, radius_sq: int = 36) -> set[Position]:
    return {
        (x, y)
        for y in range(game_map.height)
        for x in range(game_map.width)
        if any(
            (x - core_x) ** 2 + (y - core_y) ** 2 <= radius_sq
            for core_x, core_y in core.tiles
        )
    }


def legal_spawn_ring(game_map: GameMap, core: Core) -> set[Position]:
    result: set[Position] = set()
    for x, y in core.tiles:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                position = x + dx, y + dy
                if (
                    position not in core.tiles
                    and 0 <= position[0] < game_map.width
                    and 0 <= position[1] < game_map.height
                    and game_map.rows[position[1]][position[0]] != 1
                ):
                    result.add(position)
    return result


def observation_fingerprint(game_map: GameMap, team: int) -> tuple:
    core = game_map.cores[team - 1]
    visible = visible_tiles(game_map, core)
    terrain = tuple(
        sorted((x - core.x, y - core.y, game_map.rows[y][x]) for x, y in visible)
    )
    # This is exactly information, not a recommendation to switch on a map id.
    return game_map.width, game_map.height, core.x, core.y, terrain


def generic_symmetry_candidates(game_map: GameMap, team: int) -> list[str]:
    """Candidates consistent with only round-one facts and symmetry.

    A transformation is rejected if it predicts the enemy Core overlapping our
    Core, predicts it in visible space where no enemy Core exists, or conflicts
    with a pair of terrain tiles that are both currently visible.
    """
    own = game_map.cores[team - 1]
    enemy = game_map.cores[1 - (team - 1)]
    visible = visible_tiles(game_map, own)
    candidates: list[str] = []
    for name, transform in transformations(game_map).items():
        predicted = transform_core(own, name, game_map)
        if predicted.tiles & own.tiles:
            continue
        predicted_visible = bool(predicted.tiles & visible)
        actual_enemy_visible_there = predicted.tiles == enemy.tiles
        if predicted_visible and not actual_enemy_visible_there:
            continue
        contradiction = False
        for position in visible:
            counterpart = transform(position)
            if counterpart in visible:
                x, y = position
                tx, ty = counterpart
                if game_map.rows[y][x] != game_map.rows[ty][tx]:
                    contradiction = True
                    break
        if not contradiction:
            candidates.append(name)
    return candidates


def format_core_candidates(game_map: GameMap, team: int, candidates: list[str]) -> str:
    own = game_map.cores[team - 1]
    values = {
        (transform_core(own, name, game_map).x, transform_core(own, name, game_map).y)
        for name in candidates
    }
    return ";".join(f"{x}:{y}" for x, y in sorted(values))


def analyze_pool(maps: list[GameMap]) -> list[InitialInformation]:
    dimension_groups: dict[tuple[int, int], list[GameMap]] = {}
    core_groups: dict[tuple[int, int, int, int, int], list[GameMap]] = {}
    fingerprints: dict[tuple, list[tuple[GameMap, int]]] = {}
    for game_map in maps:
        dimension_groups.setdefault((game_map.width, game_map.height), []).append(game_map)
        for team in (1, 2):
            core = game_map.cores[team - 1]
            core_groups.setdefault(
                (game_map.width, game_map.height, team, core.x, core.y), []
            ).append(game_map)
            fingerprints.setdefault(observation_fingerprint(game_map, team), []).append(
                (game_map, team)
            )

    rows: list[InitialInformation] = []
    for game_map in maps:
        symmetries = actual_symmetries(game_map)
        for team in (1, 2):
            core = game_map.cores[team - 1]
            visible = visible_tiles(game_map, core)
            candidates = generic_symmetry_candidates(game_map, team)
            rows.append(
                InitialInformation(
                    map=game_map.name,
                    team=team,
                    width=game_map.width,
                    height=game_map.height,
                    core_x=core.x,
                    core_y=core.y,
                    actual_symmetry=";".join(symmetries),
                    visible_tiles=len(visible),
                    visible_ore=sum(game_map.rows[y][x] == 2 for x, y in visible),
                    visible_walls=sum(game_map.rows[y][x] == 1 for x, y in visible),
                    legal_spawn_tiles=len(legal_spawn_ring(game_map, core)),
                    generic_symmetry_candidates=";".join(candidates),
                    generic_enemy_core_candidates=format_core_candidates(
                        game_map, team, candidates
                    ),
                    pool_candidates_dimensions=len(
                        dimension_groups[(game_map.width, game_map.height)]
                    ),
                    pool_candidates_dimensions_core=len(
                        core_groups[(game_map.width, game_map.height, team, core.x, core.y)]
                    ),
                    pool_candidates_full_observation=len(
                        fingerprints[observation_fingerprint(game_map, team)]
                    ),
                )
            )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--maps", type=Path, default=Path("maps"))
    parser.add_argument(
        "--output", type=Path, default=Path("analysis/initial-information")
    )
    args = parser.parse_args()

    maps: list[GameMap] = []
    for path in sorted(args.maps.glob("*.map26")):
        if path.name.startswith("_"):
            continue
        try:
            maps.append(parse_map(path))
        except (ValueError, StopIteration, IndexError) as error:
            print(f"Skipping {path}: {error}")

    information = analyze_pool(maps)
    rows = [asdict(row) for row in information]
    write_csv(args.output / "round-one-observations.csv", rows)
    (args.output / "round-one-observations.json").write_text(
        json.dumps(rows, indent=2) + "\n"
    )
    print(f"Analyzed {len(maps)} maps from both team perspectives")
    print(f"Wrote {args.output / 'round-one-observations.csv'}")


if __name__ == "__main__":
    main()
