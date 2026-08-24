"""How close eitri's opening comes to the best that opening could go.

Three numbers per map, all in titanium delivered to the Core by round 1000,
which is exactly what the engine reports as `a_titanium_collected` -- passive
income and the starting 500 are excluded from it, so every titanium counted
here came out of a Harvester we built.

    mined    what actually happened, playing a bot that does nothing
    perfect  the same plan executed without a single wasted round: no waiting
             on a blocked tile, no re-routing, no Builder in another's way
    ceiling  the most titanium the *map* can deliver: as many deposits as the
             terrain can drain at once, each dug the moment a Builder could
             walk to it, with the conveyors free

`mined` against `perfect` measures the executor.  `perfect` against `ceiling`
measures the planner -- which deposits it picks and how it routes them.
Collapsing the two into one ratio hides which half is at fault, which is what
made the previous benchmark hard to act on.

The ceiling counts throughput because on several maps throughput, not build
time, is what caps the economy.  A conveyor tile passes 10 Ti a round and a
Harvester makes 10 Ti every four, so four Harvesters saturate a tile; the most
deposits a map can drain at once is a maximum flow from the ore to the Core
with every tile capped at four.  Ignoring that made bifrost look like a 39%
failure when its terrain admits eight lanes and the planner had found eight.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bots" / "jon" / "eitri"))
sys.path.insert(0, str(ROOT / "tools"))

import atlas_data                                          # noqa: E402
import board as board_mod                                  # noqa: E402
import crew as crew_mod                                    # noqa: E402
import network                                             # noqa: E402
import orders                                              # noqa: E402
import walk                                                # noqa: E402
from gcs_viz import _fields, _unwrap                       # noqa: E402

IDLE = "bots/common/donothingbot"
ROUNDS = 1000
PER_STACK = 10
EVERY = 4


def _best(board):
    """The exact stored or runtime-searched plan Eitri will execute."""
    picks, field = network.survey(board)
    preferred = orders.get(board.name, board.home)
    if preferred is not None and frozenset(preferred) == frozenset(picks):
        return network.lay(board, preferred, field)
    best = None
    baseline = None
    for index, order in enumerate(network.insertion_orders(picks)):
        if index == 2:
            baseline = best[0]
        lanes = network.lay(board, order, field)
        work, spawns, done = crew_mod.assign(board, lanes)
        worth = crew_mod.value(lanes, done)
        eligible = index < 2 or worth > baseline + network.ORDER_GAIN_MIN
        if (best is None or worth > best[0]) and eligible:
            best = (worth, lanes)
    return best[1]


def make(name, seat=0):
    width, height, rows, seats = atlas_data.MAPS[name]
    return board_mod.Board(name, width, height, rows,
                           seats[seat], seats[1 - seat])


def yield_from(built, chain, rounds=ROUNDS):
    """Titanium a Harvester finished on round `built` lands at the Core.

    The first stack leaves on the build round itself and one leaves every four
    rounds after, and each takes one round per conveyor tile to arrive.
    """
    first = built + chain
    if first > rounds:
        return 0
    return PER_STACK * ((rounds - first) // EVERY + 1)


def perfect(board, lanes, work, spawns, rounds=ROUNDS, starts=None):
    """The plan run by Builders that never wait for anything."""
    blocked = frozenset(lane.deposit for lane in lanes)
    total = 0
    for who, jobs in enumerate(work):
        if not jobs:
            continue
        clock, here = (starts[who] if starts and who < len(starts) else who), spawns[who]
        for index in jobs:
            lane = lanes[index]
            route = walk.route(board, here, lane.entry, blocked)
            if route is None:
                route = walk.route(board, here, lane.entry) or []
            clock += len(route) + 2 * len(lane.tiles) + 1
            here = lane.stand
            total += yield_from(clock, _chain(lanes, index), rounds)
    return total


def ceiling(board, rounds=ROUNDS):
    """The most the map can deliver: the nearest drainable deposits, dug at once.

    Optimistic on time -- it ignores conveyor build cost and lets one Builder
    be everywhere -- but honest about terrain, which is the half that was
    misleading before.
    """
    home = board_mod.flood(board, board.home_tiles, blocked=board.ore)
    reach = []
    for deposit in sorted(board.ore):
        near = network._approach(board, deposit, home)
        if near is not None:
            reach.append((home[near] + 1, deposit))
    reach.sort()
    room = drainable(board)
    return sum(yield_from(when, 0, rounds) for when, _ in reach[:room])


def drainable(board):
    """How many deposits the terrain can drain at once.

    A maximum flow from the ore to the Core with every tile carrying at most
    `network.CAPACITY` Harvesters. Tiles are split in two so the cap sits on
    the tile rather than on the step between tiles, which is where the engine
    puts it: it is the conveyor that holds one stack, not the gap.
    """
    cap = network.CAPACITY
    graph = {}

    def link(a, b, size):
        graph.setdefault(a, {})[b] = graph.setdefault(a, {}).get(b, 0) + size
        graph.setdefault(b, {}).setdefault(a, 0)

    big = 1 << 20
    for tile in sorted(board.ore):
        link("source", ("ore", tile), 1)
        for spot in board.neighbours(tile):
            if spot not in board.ore:
                link(("ore", tile), ("in", spot), big)
    for y in range(board.height):
        for x in range(board.width):
            tile = (x, y)
            if tile in board.ore or not board.walkable(tile):
                continue
            link(("in", tile), ("out", tile), cap)
            for spot in board.neighbours(tile):
                if spot not in board.ore:
                    link(("out", tile), ("in", spot), big)
            if any((x + dx, y + dy) in board.home_tiles
                   for dx, dy in board_mod.STEPS):
                link(("out", tile), "sink", big)
    return _flow(graph, "source", "sink")


def _flow(graph, source, sink):
    total = 0
    while True:
        came = {source: None}
        frontier = [source]
        while frontier and sink not in came:
            nxt = []
            for node in frontier:
                for spot, room in graph[node].items():
                    if room > 0 and spot not in came:
                        came[spot] = node
                        nxt.append(spot)
            frontier = nxt
        if sink not in came:
            return total
        room, node = 1 << 30, sink
        while came[node] is not None:
            room = min(room, graph[came[node]][node])
            node = came[node]
        node = sink
        while came[node] is not None:
            graph[came[node]][node] -= room
            graph[node][came[node]] += room
            node = came[node]
        total += room


def _chain(lanes, index):
    """Conveyor tiles between this lane's Harvester and the Core."""
    return len(lanes[index].tiles)


def measure(bot, name, seat=0, seed=1):
    players = [bot, IDLE] if seat == 0 else [IDLE, bot]
    handle, replay = tempfile.mkstemp(suffix=".replay26")
    os.close(handle)
    Path(replay).unlink(missing_ok=True)
    proc = subprocess.run(
        ["uv", "run", "--active", "fcode", "run", *players, name,
         "--seed", str(seed), "--json", "--mark", "0", "--tle", "0",
         "--replay", replay], cwd=ROOT, capture_output=True, text=True,
        timeout=900)
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        return result, _builder_starts(Path(replay), seat)
    except Exception:
        return None
    finally:
        Path(replay).unlink(missing_ok=True)


def _builder_starts(replay, team):
    """Actual creation rounds, so the ideal does not assume a free spawn tile."""
    starts = []
    for round_no, round_data in enumerate(v for f, _, v in _fields(replay.read_bytes())
                                          if f == 3):
        for _, _, event in _fields(round_data):
            fields = _unwrap(event)
            data = {field: value for field, _, value in fields}
            if {1, 3, 4}.issubset(data) and data.get(2, 0) == team and 10 in data:
                starts.append(round_no)
    return starts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot", default="bots/jon/eitri")
    parser.add_argument("--maps", default="")
    parser.add_argument("--seat", type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    names = ([m.strip() for m in args.maps.split(",") if m.strip()]
             or sorted(atlas_data.MAPS))

    print(f"{'map':<14}{'mined':>8}{'perfect':>9}{'exec':>6}"
          f"{'ceiling':>9}{'plan':>6}{'ore':>5}{'lanes':>6}{'flow':>6}")
    rows = []
    for name in names:
        board = make(name, args.seat)
        lanes = _best(board)
        work, spawns, _ = crew_mod.assign(board, lanes)
        top = ceiling(board)
        measured = measure(args.bot, name, args.seat)
        if measured is None:
            print(f"{name:<14} failed")
            continue
        result, starts = measured
        want = perfect(board, lanes, work, spawns, starts=starts)
        mined = result[f"{'a' if args.seat == 0 else 'b'}_titanium_collected"]
        ex = mined / want if want else 0.0
        pl = want / top if top else 0.0
        rows.append((ex, pl))
        print(f"{name:<14}{mined:>8}{want:>9}{ex:>5.0%}{top:>9}{pl:>5.0%}"
              f"{len(board.ore):>5}{len(lanes):>6}{drainable(board):>6}")
    if rows:
        print(f"\nexecution {sum(r[0] for r in rows) / len(rows):.0%} of plan   "
              f"plan {sum(r[1] for r in rows) / len(rows):.0%} of ceiling")


if __name__ == "__main__":
    main()
