"""Economy model: what is connected, what is worth connecting, and how full it is.

Two engine facts drive every decision here.

**A trunk is a pipe with a fixed bore.** A conveyor holds one stack and advances
it one tile per round, so a single chain delivers at most one stack per round. A
Harvester emits one stack per four rounds. Four Harvesters therefore saturate a
trunk exactly, and the fifth is dead titanium -- it mines into a jam.

**Only delivery scores.** The round-1000 tiebreak counts titanium *collected*,
which means stacks that physically reached a Core tile. Passive income does not
count and neither does titanium sitting on a belt. A Harvester with no route home
is worth nothing at all, which is why `route` outranks `harvest` in the ceiling
table: connecting what we have beats mining into the ground.
"""
from __future__ import annotations

from fcode import Controller, Direction, EntityType, GameError, Position

import config
import geom
import nav

CARRIERS = (EntityType.CONVEYOR, EntityType.SPLITTER)


def core_tiles(wm):
    """The Core's 2x2 footprint -- any of the four is a valid delivery target."""
    if wm.my_core is None:
        return set()
    cx, cy = wm.my_core.x, wm.my_core.y
    return {(cx, cy), (cx + 1, cy), (cx, cy + 1), (cx + 1, cy + 1)}


def delivers_to_core(ct: Controller, wm, start: Position, limit=40) -> bool:
    """Follow the conveyor graph forward from `start` and see if it reaches home.

    Walks output directions rather than adjacency, because a conveyor pointing
    the wrong way is not a route -- it is a leak. A chain that loops or runs off
    into unseen territory counts as *not* delivering, which is the safe answer:
    the cost of re-routing a working belt is three titanium.
    """
    home = core_tiles(wm)
    if not home:
        return False
    seen = set()
    cur = (start.x, start.y)
    for _ in range(limit):
        s = wm.buildings.get(cur)
        if s is None:
            return False
        if cur in seen:
            return False
        seen.add(cur)
        if s.etype == EntityType.CORE and s.team == wm.team:
            return True
        if s.etype == EntityType.HARVESTER or s.etype in CARRIERS:
            try:
                d = ct.get_direction(s.eid)
            except GameError:
                return False
            if d is None:
                return False
            dx, dy = d.delta()
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in home:
                return True
            cur = nxt
            continue
        return False
    return False


def my_harvesters(wm):
    return [s for s in wm.my_buildings(EntityType.HARVESTER)]


def orphan_harvesters(ct: Controller, wm):
    """Ours, built, and not yet delivering. These are the route module's work."""
    out = []
    for s in my_harvesters(wm):
        if not delivers_to_core(ct, wm, s.pos):
            out.append(s)
    return out


def trunk_load(ct: Controller, wm) -> int:
    """How many Harvesters are already delivering, i.e. how full the pipe is."""
    n = 0
    for s in my_harvesters(wm):
        if delivers_to_core(ct, wm, s.pos):
            n += 1
    return n


def ore_candidates(ct: Controller, wm):
    """Ore tiles worth taking: unoccupied, reachable, and not under enemy guns.

    Landlocked ore -- every cardinal neighbour also ore or wall -- is excluded,
    because a Harvester there has nowhere to put a conveyor and cannot deliver.
    """
    out = []
    home = wm.my_core
    if home is None:
        return out
    for key in wm.ore:
        s = wm.buildings.get(key)
        if s is not None:
            continue                     # already has a Harvester (or anything)
        if key in wm.threat:
            continue
        p = Position(key[0], key[1])
        openings = 0
        for nb in geom.orth_neighbours(p, wm.w, wm.h):
            nk = (nb.x, nb.y)
            if nk in wm.walls:
                continue
            if nk in wm.ore and wm.buildings.get(nk) is None:
                continue
            openings += 1
        if openings == 0:
            continue
        out.append(key)
    # Nearest first: a close Harvester is cheaper to connect and cheaper to hold.
    out.sort(key=lambda k: abs(k[0] - home.x) + abs(k[1] - home.y))
    return out


def plan_route(ct: Controller, wm, src: Position):
    """A conveyor path from `src` back to the Core, or None if not worth it.

    Returns the list of tiles that still need a carrier built on them, in order
    from the source outward, plus the full path so the caller can work out
    facings.
    """
    home = core_tiles(wm)
    if not home:
        return None, None
    path = nav.route_path(wm, src, home)
    if path is None or len(path) > config.MAX_TRUNK_LENGTH + 2:
        return None, None
    missing = []
    for p in path[1:-1] if len(path) > 2 else []:
        key = (p.x, p.y)
        s = wm.buildings.get(key)
        if s is None:
            missing.append(p)
        elif s.team == wm.team and s.etype in CARRIERS:
            continue                      # reuse an existing belt tile
        else:
            return None, None             # blocked by something we won't remove
    return missing, path


def facing_along(path, idx) -> Direction:
    """Which way a carrier at path[idx] must point to pass the stack onward."""
    if idx + 1 >= len(path):
        return Direction.CENTRE
    return geom.facing_from_to(path[idx], path[idx + 1])
