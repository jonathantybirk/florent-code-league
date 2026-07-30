#!/usr/bin/env python3
"""Reproducible opening-economy analysis for Florent Code League maps.

The model deliberately separates facts from assumptions:

* Map geometry, ore ownership, shortest cardinal paths, build costs, scaling,
  passive income, and harvester output use the local engine/docs.
* A constructive schedule gives each ore an independent shortest conveyor line
  to the Core. Builders construct a line Core-outward, alternating one build
  round and one movement round, then build the Harvester.
* A Builder returns along that line before beginning its next line.
* Full map knowledge and optimally chosen spawn tiles are assumed. Therefore
  these times are a map-aware planning benchmark, not a claim that a generic
  fog-of-war bot can always achieve them.
* Lines do not merge. This makes the schedule executable in principle and
  avoids hidden capacity assumptions, but can spend more than an optimal
  shared network. Reported line counts are therefore a constructive upper
  bound on infrastructure, while shortest-path lengths are a lower bound for
  independent lines.

For each map and initial Builder count, the script exhaustively searches every
assignment of the safe ores to Builder ids. Within a Builder's assignment,
shortest-line-first is provably optimal for aggregate delivery timing. The
script produces two schedules:

* income: minimize the sum of first-delivery rounds (fast aggregate ramp);
* makespan: minimize the round when all safe ores have their first delivery.

At most eight safe ores occur in the bundled maps, so exhaustive enumeration is
small enough to remain practical.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence


CARDINALS = ((1, 0), (-1, 0), (0, 1), (0, -1))
STARTING_TITANIUM = 500
PASSIVE_AMOUNT = 10
PASSIVE_PERIOD = 4
HARVEST_AMOUNT = 10
HARVEST_PERIOD = 4


@dataclass(frozen=True)
class Core:
    owner: int
    x: int
    y: int

    @property
    def tiles(self) -> frozenset[tuple[int, int]]:
        return frozenset(
            (self.x + dx, self.y + dy) for dx in range(2) for dy in range(2)
        )


@dataclass(frozen=True)
class GameMap:
    name: str
    width: int
    height: int
    rows: tuple[bytes, ...]
    cores: tuple[Core, Core]

    @property
    def ores(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (x, y)
            for y, row in enumerate(self.rows)
            for x, tile in enumerate(row)
            if tile == 2
        )


@dataclass(frozen=True)
class OreJob:
    ore: tuple[int, int]
    line_length: int
    initially_visible: bool


@dataclass(frozen=True)
class ScheduledJob:
    builder: int
    ore: tuple[int, int]
    line_length: int
    chain_start_round: int
    harvester_round: int
    first_delivery_round: int


@dataclass(frozen=True)
class Schedule:
    objective: str
    builders: int
    jobs: tuple[ScheduledJob, ...]
    sum_first_delivery: int
    all_first_delivery_round: int


@dataclass(frozen=True)
class EconomyResult:
    map: str
    ore_scope: str
    objective: str
    builders: int
    safe_ores: int
    initially_visible_safe_ores: int
    conveyor_tiles: int
    first_harvester_round: int
    first_delivery_round: int
    all_harvesters_round: int
    all_first_delivery_round: int
    titanium_mined_100: int
    titanium_mined_250: int
    titanium_mined_500: int
    titanium_mined_1000: int
    titanium_stored_100: int
    titanium_stored_250: int
    titanium_stored_500: int
    titanium_stored_1000: int
    total_builder_cost: int
    total_harvester_cost: int
    total_conveyor_cost: int
    total_capex: int
    resource_delay_rounds: int


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7


def _fields(data: bytes) -> list[tuple[int, int, int | bytes]]:
    result: list[tuple[int, int, int | bytes]] = []
    offset = 0
    while offset < len(data):
        key, offset = _read_varint(data, offset)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, offset = _read_varint(data, offset)
        elif wire == 2:
            length, offset = _read_varint(data, offset)
            value = data[offset : offset + length]
            offset += length
        else:
            raise ValueError(f"Unsupported protobuf wire type {wire}")
        result.append((number, wire, value))
    return result


def _single_varint(fields: Iterable[tuple[int, int, int | bytes]], number: int) -> int:
    return int(next(value for field, _, value in fields if field == number))


def parse_map(path: Path) -> GameMap:
    top = _fields(path.read_bytes())
    width = _single_varint(top, 1)
    height = _single_varint(top, 2)
    rows: list[bytes] = []
    cores: list[Core] = []
    for number, _, value in top:
        if number == 3:
            assert isinstance(value, bytes)
            row_fields = _fields(value)
            row = next(v for n, _, v in row_fields if n == 1)
            assert isinstance(row, bytes)
            rows.append(row)
        elif number == 4:
            assert isinstance(value, bytes)
            core_fields = _fields(value)
            owner = _single_varint(core_fields, 1)
            packed_position = next(v for n, _, v in core_fields if n == 3)
            assert isinstance(packed_position, bytes)
            position_fields = _fields(packed_position)
            cores.append(
                Core(
                    owner=owner,
                    x=_single_varint(position_fields, 1),
                    y=_single_varint(position_fields, 2),
                )
            )
    if len(rows) != height or len(cores) != 2:
        raise ValueError(f"Malformed map {path}")
    return GameMap(
        path.stem,
        width,
        height,
        tuple(rows),
        tuple(sorted(cores, key=lambda core: core.owner)),
    )


def _on_map(game_map: GameMap, position: tuple[int, int]) -> bool:
    x, y = position
    return 0 <= x < game_map.width and 0 <= y < game_map.height


def _neighbors(position: tuple[int, int]) -> Iterator[tuple[int, int]]:
    x, y = position
    for dx, dy in CARDINALS:
        yield x + dx, y + dy


def core_distances(game_map: GameMap, core: Core) -> dict[tuple[int, int], int]:
    """Cardinal passable distance to the ring touching a 2x2 Core."""
    blocked = core.tiles
    starts = {
        neighbor
        for tile in blocked
        for neighbor in _neighbors(tile)
        if _on_map(game_map, neighbor)
        and neighbor not in blocked
        and game_map.rows[neighbor[1]][neighbor[0]] != 1
    }
    distances = {position: 0 for position in starts}
    queue = deque(starts)
    while queue:
        current = queue.popleft()
        for neighbor in _neighbors(current):
            if (
                _on_map(game_map, neighbor)
                and neighbor not in blocked
                and game_map.rows[neighbor[1]][neighbor[0]] != 1
                and neighbor not in distances
            ):
                distances[neighbor] = distances[current] + 1
                queue.append(neighbor)
    return distances


def _visible_from_core(ore: tuple[int, int], core: Core) -> bool:
    return any(
        (ore[0] - tile[0]) ** 2 + (ore[1] - tile[1]) ** 2 <= 36
        for tile in core.tiles
    )


def safe_ore_jobs(game_map: GameMap) -> list[OreJob]:
    own, enemy = game_map.cores
    own_distances = core_distances(game_map, own)
    enemy_distances = core_distances(game_map, enemy)
    jobs = [
        OreJob(
            ore=ore,
            # A target ore at distance d from the Core ring needs d conveyor
            # tiles: every node after leaving the ore, including the ring tile.
            line_length=own_distances[ore],
            initially_visible=_visible_from_core(ore, own),
        )
        for ore in game_map.ores
        if own_distances.get(ore, math.inf) < enemy_distances.get(ore, math.inf)
    ]
    return sorted(jobs, key=lambda job: (job.line_length, job.ore))


def _schedule_sequences(
    sequences: Sequence[Sequence[OreJob]], builders: int, objective: str
) -> Schedule:
    scheduled: list[ScheduledJob] = []
    for builder, sequence in enumerate(sequences):
        # Core spawns Builder i on round i; replay validation shows its first
        # action occurs on the following round.
        available = builder + 1
        previous_length: int | None = None
        for job in sequence:
            if previous_length is None:
                start = available
            else:
                # Following the completed line back to a Core-side staging tile.
                start = available + previous_length + 1
            harvester_round = start + 2 * job.line_length
            first_delivery = harvester_round + job.line_length
            scheduled.append(
                ScheduledJob(
                    builder,
                    job.ore,
                    job.line_length,
                    start,
                    harvester_round,
                    first_delivery,
                )
            )
            available = harvester_round
            previous_length = job.line_length
    scheduled.sort(key=lambda job: (job.harvester_round, job.builder, job.ore))
    deliveries = [job.first_delivery_round for job in scheduled]
    return Schedule(
        objective,
        builders,
        tuple(scheduled),
        sum(deliveries),
        max(deliveries, default=0),
    )


def optimize_schedule(jobs: Sequence[OreJob], builders: int, objective: str) -> Schedule:
    if objective not in {"income", "makespan"}:
        raise ValueError(objective)
    best: Schedule | None = None
    best_key: tuple[int, int, tuple] | None = None
    # For one Builder with spawn round s and route lengths L1..Lk, delivery r is
    # s + 3*sum(L1..Lr) + (r-1). Interchanging adjacent jobs shows that shorter
    # routes first minimizes the sum of delivery rounds. Order does not affect
    # the final delivery round, so the same ordering is also optimal for the
    # makespan objective's secondary sum criterion. We therefore enumerate only
    # the m^n assignments of jobs to Builder ids (at most 4^8 = 65,536).
    n = len(jobs)
    for labels in itertools.product(range(builders), repeat=n):
        sequences = [
            tuple(
                sorted(
                    (jobs[index] for index, label in enumerate(labels) if label == builder),
                    key=lambda job: (job.line_length, job.ore),
                )
            )
            for builder in range(builders)
        ]
        candidate = _schedule_sequences(sequences, builders, objective)
        signature = tuple(
            (job.builder, job.ore, job.harvester_round) for job in candidate.jobs
        )
        if objective == "income":
            candidate_key = (
                candidate.sum_first_delivery,
                candidate.all_first_delivery_round,
                signature,
            )
        else:
            candidate_key = (
                candidate.all_first_delivery_round,
                candidate.sum_first_delivery,
                signature,
            )
        if best_key is None or candidate_key < best_key:
            best, best_key = candidate, candidate_key
    assert best is not None
    return best


def _scaled_cost(base: int, scale_points: int) -> int:
    return math.floor(base * scale_points / 100)


def simulate_economy(
    schedule: Schedule,
    map_name: str,
    ore_scope: str,
    safe_count: int,
    visible: int,
) -> EconomyResult:
    """Simulate global titanium and delay unaffordable construction actions."""
    horizon = 1000
    titanium = STARTING_TITANIUM
    scale_points = 100
    builder_cost = harvester_cost = conveyor_cost = 0
    actual_jobs: list[ScheduledJob] = []
    delays = [0] * schedule.builders

    # Events are mutable per-Builder queues. A resource wait shifts that
    # Builder's remaining construction, retaining movement gaps.
    queues: list[deque[tuple[int, str, ScheduledJob]]] = [deque() for _ in range(schedule.builders)]
    for job in schedule.jobs:
        for index in range(job.line_length):
            queues[job.builder].append(
                (job.chain_start_round + 2 * index, "conveyor", job)
            )
        queues[job.builder].append((job.harvester_round, "harvester", job))

    delivery_starts: list[int] = []
    mined_at: dict[int, int] = {}
    stored_at: dict[int, int] = {}
    snapshots = {100, 250, 500, 1000}
    spawned = 0

    for round_number in range(horizon):
        if round_number % PASSIVE_PERIOD == 0:
            titanium += PASSIVE_AMOUNT

        # Harvest income already connected by completed independent lines.
        for first_delivery in delivery_starts:
            if round_number >= first_delivery and (round_number - first_delivery) % HARVEST_PERIOD == 0:
                titanium += HARVEST_AMOUNT

        if spawned < schedule.builders:
            cost = _scaled_cost(30, scale_points)
            if titanium >= cost:
                titanium -= cost
                builder_cost += cost
                scale_points += 20
                spawned += 1

        for builder in range(spawned):
            if not queues[builder]:
                continue
            planned_round, kind, planned_job = queues[builder][0]
            planned_round += delays[builder]
            if planned_round > round_number:
                continue
            base = 3 if kind == "conveyor" else 20
            cost = _scaled_cost(base, scale_points)
            if titanium < cost:
                delays[builder] += 1
                continue
            titanium -= cost
            scale_points += 1 if kind == "conveyor" else 5
            if kind == "conveyor":
                conveyor_cost += cost
            else:
                harvester_cost += cost
                actual_harvester = round_number
                first_delivery = actual_harvester + planned_job.line_length
                delivery_starts.append(first_delivery)
                actual_jobs.append(
                    ScheduledJob(
                        builder,
                        planned_job.ore,
                        planned_job.line_length,
                        planned_job.chain_start_round + delays[builder],
                        actual_harvester,
                        first_delivery,
                    )
                )
            queues[builder].popleft()

        completed_rounds = round_number + 1
        if completed_rounds in snapshots:
            mined = sum(
                HARVEST_AMOUNT * (1 + (round_number - first) // HARVEST_PERIOD)
                for first in delivery_starts
                if first <= round_number
            )
            mined_at[completed_rounds] = mined
            stored_at[completed_rounds] = titanium

    capex = builder_cost + harvester_cost + conveyor_cost
    return EconomyResult(
        map=map_name,
        ore_scope=ore_scope,
        objective=schedule.objective,
        builders=schedule.builders,
        safe_ores=safe_count,
        initially_visible_safe_ores=visible,
        conveyor_tiles=sum(job.line_length for job in schedule.jobs),
        first_harvester_round=min(job.harvester_round for job in actual_jobs),
        first_delivery_round=min(job.first_delivery_round for job in actual_jobs),
        all_harvesters_round=max(job.harvester_round for job in actual_jobs),
        all_first_delivery_round=max(job.first_delivery_round for job in actual_jobs),
        titanium_mined_100=mined_at[100],
        titanium_mined_250=mined_at[250],
        titanium_mined_500=mined_at[500],
        titanium_mined_1000=mined_at[1000],
        titanium_stored_100=stored_at[100],
        titanium_stored_250=stored_at[250],
        titanium_stored_500=stored_at[500],
        titanium_stored_1000=stored_at[1000],
        total_builder_cost=builder_cost,
        total_harvester_cost=harvester_cost,
        total_conveyor_cost=conveyor_cost,
        total_capex=capex,
        resource_delay_rounds=sum(delays),
    )


def analyze_map(game_map: GameMap) -> tuple[list[dict], list[EconomyResult]]:
    jobs = safe_ore_jobs(game_map)
    metadata = [
        {
            "map": game_map.name,
            "width": game_map.width,
            "height": game_map.height,
            "ore_x": job.ore[0],
            "ore_y": job.ore[1],
            "line_length": job.line_length,
            "initially_visible": job.initially_visible,
        }
        for job in jobs
    ]
    results: list[EconomyResult] = []
    scopes = {
        "all_safe": jobs,
        "initially_visible": [job for job in jobs if job.initially_visible],
    }
    for ore_scope, scoped_jobs in scopes.items():
        for builders in range(1, 5):
            for objective in ("income", "makespan"):
                schedule = optimize_schedule(scoped_jobs, builders, objective)
                results.append(
                    simulate_economy(
                        schedule,
                        game_map.name,
                        ore_scope,
                        len(jobs),
                        sum(job.initially_visible for job in jobs),
                    )
                )
    return metadata, results


def _write_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--maps", type=Path, default=Path("maps"))
    parser.add_argument(
        "--output", type=Path, default=Path("analysis/opening-economy")
    )
    args = parser.parse_args()

    all_metadata: list[dict] = []
    all_results: list[EconomyResult] = []
    for path in sorted(args.maps.glob("*.map26")):
        if path.name.startswith("_"):
            continue
        try:
            game_map = parse_map(path)
        except (ValueError, StopIteration, IndexError) as error:
            print(f"Skipping {path}: {error}")
            continue
        metadata, results = analyze_map(game_map)
        all_metadata.extend(metadata)
        all_results.extend(results)

    result_rows = [asdict(result) for result in all_results]
    _write_csv(args.output / "ore-distances.csv", all_metadata)
    _write_csv(args.output / "opening-results.csv", result_rows)
    (args.output / "opening-results.json").write_text(
        json.dumps(result_rows, indent=2) + "\n"
    )

    print(f"Analyzed {len({row['map'] for row in result_rows})} maps")
    print(f"Wrote {args.output / 'ore-distances.csv'}")
    print(f"Wrote {args.output / 'opening-results.csv'}")


if __name__ == "__main__":
    main()
