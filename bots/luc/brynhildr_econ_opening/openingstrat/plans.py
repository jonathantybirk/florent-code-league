"""Data-only opening plans, kept independent from the game controller."""

from dataclasses import dataclass, replace
from collections import deque

from .terrain_catalog import TERRAIN_CATALOG

Tile = tuple[int, int]


@dataclass(frozen=True)
class BuildTask:
    kind: str
    tile: Tile
    output: Tile | None = None


@dataclass(frozen=True)
class OpeningPlan:
    size: Tile
    core: Tile
    spawns: tuple[Tile, ...]
    tasks: tuple[tuple[BuildTask, ...], ...]
    benchmarks: tuple["LaneBenchmark", ...] = ()
    walls: frozenset[Tile] = frozenset()


@dataclass(frozen=True)
class LaneBenchmark:
    name: str
    required_tiles: frozenset[Tile]
    optimal_round: int


def _rot(tile: Tile, size: Tile) -> Tile:
    return size[0] - 1 - tile[0], size[1] - 1 - tile[1]


def _rotate(plan: OpeningPlan) -> OpeningPlan:
    size = plan.size
    return OpeningPlan(
        size,
        _rot(plan.core, size),
        tuple(_rot(tile, size) for tile in plan.spawns),
        tuple(tuple(BuildTask(t.kind, _rot(t.tile, size), _rot(t.output, size) if t.output else None)
                    for t in tasks) for tasks in plan.tasks),
        tuple(LaneBenchmark(b.name, frozenset(_rot(t, size) for t in b.required_tiles), b.optimal_round)
              for b in plan.benchmarks),
        frozenset(_rot(tile, size) for tile in plan.walls),
    )


# Sprint's first two lanes.  The schedule deliberately separates deposits
# from transport: Builders 0/2 construct conveyors while Builders 1/3 can
# approach the ore, minimizing the round on which each full lane activates.
SPRINT_NW = OpeningPlan(
    size=(10, 10),
    core=(1, 1),
    spawns=((3, 1), (1, 3), (3, 2), (0, 3)),
    tasks=(
        (
            BuildTask("conveyor", (5, 1), (4, 1)),
            BuildTask("harvester", (6, 1)),
            BuildTask("harvester", (4, 4)),
            BuildTask("conveyor", (4, 5), (4, 4)),
            BuildTask("harvester", (5, 5)),
        ),
        (
            BuildTask("conveyor", (1, 5), (1, 4)),
            BuildTask("harvester", (1, 6)),
            BuildTask("conveyor", (3, 2), (2, 2)),
            BuildTask("conveyor", (4, 2), (3, 2)),
            BuildTask("conveyor", (4, 3), (4, 2)),
        ),
        (
            BuildTask("conveyor", (3, 1), (2, 1)),
            BuildTask("conveyor", (4, 1), (3, 1)),
        ),
        (
            BuildTask("conveyor", (1, 3), (1, 2)),
            BuildTask("conveyor", (1, 4), (1, 3)),
        ),
    ),
    benchmarks=(
        LaneBenchmark("east", frozenset({(3, 1), (4, 1), (5, 1), (6, 1)}), 5),
        LaneBenchmark("south", frozenset({(1, 3), (1, 4), (1, 5), (1, 6)}), 6),
    ),
)

PLANS = {
    (SPRINT_NW.size, SPRINT_NW.core): SPRINT_NW,
    ((_p := _rotate(SPRINT_NW)).size, _p.core): _p,
}


def _neighbors(tile, width, height):
    x, y = tile
    for nxt in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
        if 0 <= nxt[0] < width and 0 <= nxt[1] < height:
            yield nxt


def _core_tiles(core):
    x, y = core
    return {(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)}


def _spawn_ring(core, width, height, blocked):
    footprint = _core_tiles(core)
    out = set()
    for tile in footprint:
        for nxt in _neighbors(tile, width, height):
            if nxt not in footprint and nxt not in blocked:
                out.add(nxt)
        x, y = tile
        for nxt in ((x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1), (x + 1, y + 1)):
            if 0 <= nxt[0] < width and 0 <= nxt[1] < height and nxt not in footprint and nxt not in blocked:
                out.add(nxt)
    return tuple(sorted(out))


def _core_inputs(core, width, height, blocked):
    footprint = _core_tiles(core)
    return tuple(sorted({nxt for tile in footprint for nxt in _neighbors(tile, width, height)
                         if nxt not in footprint and nxt not in blocked}))


def _core_output(core, core_input):
    return next(tile for tile in _core_tiles(core)
                if abs(tile[0] - core_input[0]) + abs(tile[1] - core_input[1]) == 1)


def _route(width, height, core, goal, walls, ores):
    footprint = _core_tiles(core)
    starts = _core_inputs(core, width, height, walls | (ores - {goal}))
    blocked = walls | footprint | (ores - {goal})
    queue = deque(starts)
    previous = {tile: None for tile in starts}
    while queue:
        tile = queue.popleft()
        if tile == goal:
            path = []
            while tile is not None:
                path.append(tile)
                tile = previous[tile]
            return tuple(reversed(path))
        for nxt in _neighbors(tile, width, height):
            if nxt not in blocked and nxt not in previous:
                previous[nxt] = tile
                queue.append(nxt)
    return None


def _distance(width, height, core, goal, walls, ores):
    route = _route(width, height, core, goal, walls, ores)
    return 10_000 if route is None else len(route) - 1


def _spawn_for(target, candidates, reserved, avoid_target=True):
    choices = [tile for tile in candidates if tile not in reserved and (not avoid_target or tile != target)]
    if not choices:
        choices = list(candidates)
    return min(choices, key=lambda tile: (abs(tile[0] - target[0]) + abs(tile[1] - target[1]), tile))


def _extend_lanes(core, candidates, chosen, tasks, capacity=4):
    """Add compatible deposits to selected lanes without duplicating network."""
    workers = [list(work) for work in tasks]
    extensions = [[] for _ in workers]
    outputs = {task.tile: task.output for work in workers for task in work
               if task.kind == "conveyor"}
    inputs = {candidate[3][0] for candidate in chosen}
    counts = {core_input: 1 for core_input in inputs}
    selected = {candidate[2] for candidate in chosen}

    def last_tile(index):
        return (extensions[index][-1][-1] if extensions[index] else workers[index][-1]).tile

    for _, _, ore, route in candidates:
        core_input, conveyors = route[0], route[:-1]
        if ore in selected or core_input not in inputs or counts[core_input] >= capacity:
            continue
        route_outputs = {
            tile: _core_output(core, tile) if index == 0 else conveyors[index - 1]
            for index, tile in enumerate(conveyors)
        }
        if any(outputs.get(tile, output) != output for tile, output in route_outputs.items()):
            continue
        package = [BuildTask("conveyor", tile, route_outputs[tile])
                   for tile in conveyors if tile not in outputs]
        package.append(BuildTask("harvester", ore))
        worker = min(range(len(workers)), key=lambda index: (
            abs(last_tile(index)[0] - package[0].tile[0])
            + abs(last_tile(index)[1] - package[0].tile[1]),
            len(workers[index]) + sum(map(len, extensions[index])),
            index,
        ))
        extensions[worker].append(package)
        outputs.update(route_outputs)
        selected.add(ore)
        counts[core_input] += 1
    for index, packages in enumerate(extensions):
        packages.sort(
            key=lambda package: -(
                abs(package[-1].tile[0] - core[0]) + abs(package[-1].tile[1] - core[1])
            )
        )
        for package in packages:
            workers[index].extend(package)
    return tuple(tuple(work) for work in workers)


def _catalog_plan(name, width, height, cores, walls_raw, ores_raw, side):
    core, enemy = cores[side], cores[1 - side]
    # Both Cores are impassable terrain for Builder routing.
    walls, ores = set(walls_raw) | _core_tiles(enemy), set(ores_raw)
    candidates = []
    for ore in ores:
        route = _route(width, height, core, ore, walls, ores)
        if route is None or len(route) < 2:
            continue
        ours = len(route) - 1
        theirs = _distance(width, height, enemy, ore, walls, ores)
        if ours <= theirs + 2:
            candidates.append((ours, ours - theirs, ore, route))
    candidates.sort()
    # Prefer different Core inputs so the opening lanes do not collide.
    chosen, inputs = [], set()
    for candidate in candidates:
        core_input = candidate[3][0]
        if core_input not in inputs:
            chosen.append(candidate)
            inputs.add(core_input)
        if len(chosen) == 4:
            break
    if not chosen:
        return None

    # Builders may legally spawn on ore.  Keeping ore in the candidate ring
    # is necessary on cramped starts where walls leave fewer than four empty
    # ground tiles around the Core.
    spawn_candidates = _spawn_ring(core, width, height, walls)
    tasks = []
    spawns = []
    reserved = set()
    if len(chosen) == 1:
        _, _, ore, route = chosen[0]
        conveyors = route[:-1]
        worker_count = min(4, len(conveyors) + 1)
        # Contiguous inner-to-outer chunks; workers are spawned outer-first so
        # the earliest unit walks through the future lane while later units
        # backfill behind it.
        if worker_count > len(conveyors):
            chunks = [(i, i + 1) for i in range(len(conveyors))] + [(len(conveyors), len(conveyors))]
        else:
            chunks = []
            for worker in range(worker_count):
                lo = len(conveyors) * worker // worker_count
                hi = len(conveyors) * (worker + 1) // worker_count
                chunks.append((lo, hi))
        workers = []
        for worker, (lo, hi) in reversed(tuple(enumerate(chunks))):
            work = [BuildTask("conveyor", conveyors[i],
                              _core_output(core, conveyors[i]) if i == 0 else conveyors[i - 1])
                    for i in range(lo, hi)]
            if worker == worker_count - 1:
                work.append(BuildTask("harvester", ore))
            target = work[0].tile
            spawn = _spawn_for(target, spawn_candidates, reserved, avoid_target=False)
            reserved.add(spawn)
            workers.append((spawn, tuple(work)))
        for spawn, work in workers:
            spawns.append(spawn)
            tasks.append(work)
    elif len(chosen) in (2, 3):
        leads, trailers = [], []
        for lane_index, (_, _, ore, route) in enumerate(chosen):
            conveyors = route[:-1]
            if len(chosen) == 3 and lane_index > 0:
                work = [BuildTask("conveyor", tile, _core_output(core, tile) if i == 0 else conveyors[i - 1])
                        for i, tile in enumerate(conveyors)]
                work.append(BuildTask("harvester", ore))
                spawn = _spawn_for(ore, spawn_candidates, reserved, avoid_target=False)
                reserved.add(spawn)
                leads.append((spawn, tuple(work)))
                continue
            cut = (len(conveyors) + 1) // 2
            lead_steps = conveyors[cut:]
            lead_tasks = [BuildTask("conveyor", tile, conveyors[i - 1])
                          for i, tile in enumerate(conveyors[cut:], start=cut)]
            lead_tasks.append(BuildTask("harvester", ore))
            trailer_tasks = [BuildTask("conveyor", tile, _core_output(core, tile) if i == 0 else conveyors[i - 1])
                             for i, tile in enumerate(conveyors[:cut])]
            lead_target = lead_steps[0] if lead_steps else ore
            lead_spawn = _spawn_for(lead_target, spawn_candidates, reserved, avoid_target=False)
            reserved.add(lead_spawn)
            trailer_spawn = _spawn_for(conveyors[0], spawn_candidates, reserved)
            reserved.add(trailer_spawn)
            leads.append((lead_spawn, tuple(lead_tasks)))
            trailers.append((trailer_spawn, tuple(trailer_tasks)))
        for spawn, work in leads + trailers:
            spawns.append(spawn)
            tasks.append(work)
    else:
        for _, _, ore, route in chosen[:4]:
            conveyors = route[:-1]
            work = [BuildTask("conveyor", tile, _core_output(core, tile) if i == 0 else conveyors[i - 1])
                    for i, tile in enumerate(conveyors)]
            work.append(BuildTask("harvester", ore))
            spawn = _spawn_for(ore, spawn_candidates, reserved, avoid_target=False)
            reserved.add(spawn)
            spawns.append(spawn)
            tasks.append(tuple(work))
    return OpeningPlan(
        (width, height), core, tuple(spawns),
        _extend_lanes(core, candidates, chosen, tasks),
        walls=frozenset(walls),
    )


CATALOG_PLANS = {}
for _name, _width, _height, _cores, _walls, _ores in TERRAIN_CATALOG:
    for _side in range(2):
        _plan = _catalog_plan(_name, _width, _height, _cores, _walls, _ores, _side)
        if _plan is not None:
            CATALOG_PLANS.setdefault(((_width, _height), _cores[_side]), []).append(
                (_name, frozenset(_walls), frozenset(_ores), _plan)
            )


def resize_plan(plan: OpeningPlan, builder_count: int) -> OpeningPlan:
    """Scale lane capacity and merge the original coherent worker schedules."""
    if not 1 <= builder_count <= 4:
        raise ValueError("builder_count must be between 1 and 4")
    if builder_count >= len(plan.tasks):
        return plan

    unique = {task.tile: task for work in plan.tasks for task in work}
    conveyors = {tile: task for tile, task in unique.items() if task.kind == "conveyor"}
    core_tiles = _core_tiles(plan.core)

    def depth(tile):
        value, seen = 0, set()
        while tile in conveyors and tile not in seen:
            seen.add(tile)
            value += 1
            tile = conveyors[tile].output
        return value if tile in core_tiles else 10_000 + value

    def lane(harvester):
        adjacent = [tile for tile in _neighbors(harvester.tile, *plan.size)
                    if tile in conveyors and depth(tile) < 10_000]
        if not adjacent:
            return None, ()
        tile = min(adjacent, key=depth)
        path = []
        while tile in conveyors:
            path.append(tile)
            tile = conveyors[tile].output
        return path[-1], tuple(path)

    lanes = {}
    for task in unique.values():
        if task.kind == "harvester":
            root, path = lane(task)
            lanes.setdefault(root, []).append((len(path), task, path))
    selected = [item for deposits in lanes.values()
                for item in sorted(deposits, key=lambda item: (item[0], item[1].tile))[:builder_count]]
    keep = {task.tile for _, task, _ in selected}
    keep.update(tile for _, _, path in selected for tile in path)

    filtered = [[task for task in work if task.tile in keep] for work in plan.tasks]
    if builder_count == 1:
        work = sorted((conveyors[tile] for tile in keep if tile in conveyors),
                      key=lambda task: (depth(task.tile), task.tile))
        work.extend(task for _, task, _ in sorted(
            selected, key=lambda item: (-item[0], item[1].tile)
        ))
        tasks = (tuple(work),)
        return replace(plan, spawns=plan.spawns[:1], tasks=tasks, benchmarks=())

    # Retain coherent schedules; attach surplus packages to the nearest worker.
    workers = [[] for _ in range(builder_count)]
    for index, work in enumerate(filtered):
        if not work:
            continue
        owner = index if index < builder_count else min(
            range(builder_count),
            key=lambda worker: (
                abs(workers[worker][-1].tile[0] - work[0].tile[0])
                + abs(workers[worker][-1].tile[1] - work[0].tile[1])
                if workers[worker] else 0,
                len(workers[worker]), worker,
            ),
        )
        workers[owner].extend(work)
    tasks = tuple(tuple(work) for work in workers)
    return replace(plan, spawns=plan.spawns[:builder_count], tasks=tasks, benchmarks=())
