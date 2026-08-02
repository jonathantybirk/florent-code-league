"""Conveyor-line planning shared by the economy and the forward siege.

A line is a list of (tile, facing) pairs ordered from the producer end toward
the consumer end. Tiles are only ever planned through terrain this unit has
actually observed: unknown ground is not permission to spend titanium.
"""

from collections import deque

from .constants import D4_DELTAS, FACING
from . import world
from .world import inside


def plan_line(p, source, sinks, joinable=(), extra_blocked=(), max_length=40):
    """Shortest conveyor chain carrying output from `source` into a sink.

    `source` is the producing tile (harvester or an existing line end) and is
    not part of the result. `joinable` names own conveyors the line may splice
    into. Returns None when no fully observed route exists.
    """
    joinable = set(joinable)
    blocked = (world.known_walls(p) | p.solids | set(extra_blocked)
               | (set(p.conveyors) - joinable)
               | (world.known_ores(p) - {source}))
    open_ground = world.known_seen(p)
    sinks = set(sinks)
    prev = {source: None}
    queue = deque([source])
    goal = None
    while queue and goal is None:
        cur = queue.popleft()
        if len(_trace(prev, cur)) > max_length:
            continue
        for dx, dy in D4_DELTAS:
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in prev or not inside(p, nxt):
                continue
            if nxt in sinks and _accepts(p, nxt, cur):
                prev[nxt], goal = cur, nxt
                break
            if nxt in joinable and _accepts(p, nxt, cur):
                prev[nxt], goal = cur, nxt
                break
            if nxt not in open_ground or nxt in blocked:
                continue
            prev[nxt] = cur
            queue.append(nxt)
    if goal is None:
        return None
    path = _trace(prev, goal)
    tiles = path[1:-1]
    line = []
    for i, tile in enumerate(tiles):
        nxt = tiles[i + 1] if i + 1 < len(tiles) else path[-1]
        line.append((tile, FACING[(nxt[0] - tile[0], nxt[1] - tile[1])]))
    return line


def _trace(prev, node):
    path, cur = [], node
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return path


def _accepts(p, sink, feeder):
    """Can a stack move from `feeder` into `sink` given what we remember?"""
    facing = p.conveyors.get(sink)
    if facing is not None:
        # A conveyor accepts from its three non-output sides.
        dx, dy = facing.delta()
        return (sink[0] + dx, sink[1] + dy) != feeder
    return True


def next_unbuilt(p, line):
    for index, (tile, facing) in enumerate(line):
        if p.conveyors.get(tile) != facing:
            return index
    return None
