"""Print eitri's opening plan for a map, without running the engine."""

import sys
import time

sys.path.insert(0, "bots/jon/eitri")

import atlas_data                                          # noqa: E402
import board as board_mod                                  # noqa: E402
import crew                                                # noqa: E402
import network                                             # noqa: E402


def make(name, seat=0):
    width, height, rows, seats = atlas_data.MAPS[name]
    return board_mod.Board(name, width, height, rows,
                           seats[seat], seats[1 - seat])


def show(name, seat=0, draw=False):
    board = make(name, seat)
    start = time.perf_counter()
    lanes, home = network.plan(board)
    work, spawns = crew.assign(board, lanes)
    took = (time.perf_counter() - start) * 1000
    print(f"{name} {board.width}x{board.height} core{board.home} "
          f"ore {len(board.ore)} lanes {len(lanes)}  plan {took:.1f}ms")
    for who, jobs in enumerate(work):
        if not jobs:
            continue
        parts = " ".join(f"{lanes[j].deposit}/{len(lanes[j].tiles)}t"
                         for j in jobs)
        print(f"  seat {who} spawn {spawns[who]}  {parts}")
    if draw:
        grid = [list(row) for row in board.rows]
        for tile in board.home_tiles:
            grid[tile[1]][tile[0]] = "C"
        for tile in board.away_tiles:
            grid[tile[1]][tile[0]] = "E"
        for lane in lanes:
            for tile, _ in lane.tiles:
                grid[tile[1]][tile[0]] = "="
            grid[lane.deposit[1]][lane.deposit[0]] = "H"
        for who, spot in enumerate(spawns):
            if spot:
                grid[spot[1]][spot[0]] = str(who)
        print("\n".join("".join(r) for r in grid))


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(atlas_data.MAPS)
    draw = len(names) == 1
    for name in names:
        show(name, draw=draw)
