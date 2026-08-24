"""Movement and route search on the Builder's 4-neighbour graph.

Every search here runs **backwards, from the target set toward the unit**, which
removes the need to store parent pointers or reconstruct a path: once the wave
reaches a tile the unit can step onto this turn, that step is the answer. It also
means one search answers "which of these many targets is nearest", which is the
question the economy and siege modules actually ask.

Threat is a soft cost rather than a wall. A tile covered by an enemy turret is
passable at a penalty, because refusing to ever enter one strands the bot on maps
where the only route to the ore runs through a covered corridor.
"""
from __future__ import annotations

from collections import deque

from fcode import Controller, Direction, GameError, Position

import geom

THREAT_PENALTY = 8          # extra steps a covered tile is "worth" avoiding


def bfs_step(ct: Controller, wm, targets, avoid_threat=True, max_nodes=900):
    """One cardinal step from the unit toward the nearest tile in `targets`.

    Returns (direction, distance) or (None, -1) if nothing is reachable. The
    unit's own tile counts as arrival, so a caller standing on its goal gets
    (Direction.CENTRE, 0).
    """
    if wm.me is None or not targets:
        return None, -1
    start = (wm.me.x, wm.me.y)
    goal = set(targets)
    if start in goal:
        return Direction.CENTRE, 0

    # Two uniform-cost sweeps rather than one weighted search. The first refuses
    # to enter any tile an enemy turret covers; only if that finds nothing do we
    # allow it, which keeps the common case cheap and still leaves the bot able
    # to cross a covered corridor when it is the only way through.
    for pass_avoids_threat in (True, False) if avoid_threat else (False,):
        res = _sweep(wm, start, goal, pass_avoids_threat, max_nodes)
        if res[0] is not None:
            return res
    return None, -1


def _sweep(wm, start, goal, avoid_threat, max_nodes):
    w, h = wm.w, wm.h
    threat = wm.threat if avoid_threat else ()
    dist = {}
    q = deque()
    for t in goal:
        if 0 <= t[0] < w and 0 <= t[1] < h and t not in threat:
            q.append(t)
            dist[t] = 0
    if not q:
        return None, -1

    visited = 0
    while q:
        node = q.popleft()
        visited += 1
        if visited > max_nodes:
            break
        d = dist[node]
        nx, ny = node
        for dx, dy in geom.CARD_DELTAS:
            ax, ay = nx + dx, ny + dy
            if not (0 <= ax < w and 0 <= ay < h):
                continue
            akey = (ax, ay)
            if akey == start:
                # The wave reached the unit: step from the unit *into* `node`.
                return _step_to(wm.me, Position(nx, ny)), d + 1
            if akey in dist or akey in wm.walls or akey in threat:
                continue
            s = wm.buildings.get(akey)
            if s is not None and s.etype in _BLOCKERS:
                continue
            dist[akey] = d + 1
            q.append(akey)
    return None, -1


def _step_to(src: Position, dst: Position) -> Direction:
    return src.cardinal_direction_to(dst)


from fcode import EntityType as _ET  # noqa: E402  (kept local to the blocker set)

_BLOCKERS = (_ET.CORE, _ET.HARVESTER, _ET.BARRIER,
             _ET.GUNNER, _ET.SENTINEL, _ET.LAUNCHER)


def try_move(ct: Controller, direction) -> bool:
    """Move if legal. Never raises; a blocked step is a normal outcome."""
    if direction is None or direction == Direction.CENTRE:
        return False
    try:
        if ct.can_move(direction):
            ct.move(direction)
            return True
    except GameError:
        pass
    return False


def step_toward(ct: Controller, wm, targets, avoid_threat=True) -> bool:
    d, _ = bfs_step(ct, wm, targets, avoid_threat)
    if d is None:
        return False
    if try_move(ct, d):
        return True
    # Blocked this round -- try the other axis so a queue of our own Builders
    # does not deadlock a corridor.
    if wm.me is not None and targets:
        for alt in geom.CARDINALS:
            if alt is d:
                continue
            if try_move(ct, alt):
                return True
    return False


def route_path(wm, start: Position, targets, max_nodes=900):
    """Shortest 4-neighbour path from `start` to the nearest target tile.

    Used by the economy planner to price a conveyor trunk before committing to
    it, so it returns the whole path rather than one step. Buildings block, but
    our *own* conveyors do not -- a trunk may legitimately join an existing one.
    """
    if not targets:
        return None
    goal = set(targets)
    w, h = wm.w, wm.h
    prev = {}
    seen = {(start.x, start.y)}
    q = deque([(start.x, start.y)])
    found = None
    nodes = 0
    while q and nodes < max_nodes:
        nodes += 1
        node = q.popleft()
        if node in goal:
            found = node
            break
        nx, ny = node
        for dx, dy in geom.CARD_DELTAS:
            ax, ay = nx + dx, ny + dy
            akey = (ax, ay)
            if akey in seen or not (0 <= ax < w and 0 <= ay < h):
                continue
            if akey in wm.walls:
                continue
            s = wm.buildings.get(akey)
            if s is not None and s.etype in _BLOCKERS and akey not in goal:
                continue
            seen.add(akey)
            prev[akey] = node
            q.append(akey)
    if found is None:
        return None
    path = [found]
    while path[-1] != (start.x, start.y):
        nxt = prev.get(path[-1])
        if nxt is None:
            return None
        path.append(nxt)
    path.reverse()
    return [Position(x, y) for x, y in path]
