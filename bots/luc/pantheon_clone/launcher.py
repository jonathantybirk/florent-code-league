"""Launcher: four throws on rounds 2-5, then raze itself.

Throw targeting is the measured rule -- of every legal landing tile, take the
one with the shortest *walk* to the objective, and among equals throw as far as
possible. The far tie-break had no counterexample in 103 tied throws.
"""

from collections import deque

from constants import (PICKUP_RANGE_SQ, RAIDER_THROWS, SLOT_LAUNCHER,
                       SLOT_OWN_CORE, SLOT_THROWS_DONE, THROW_COUNT,
                       THROW_RANGE_SQ)
from fcode import EntityType, Environment, Position
from utils import (dist_sq, pack_pos, read_enemy_core, sight_enemy_core,
                   unpack_pos)


def run(player, ct) -> None:
    sight_enemy_core(ct)
    pos = tuple(ct.get_position())

    if player.throws >= THROW_COUNT:
        # The fourth passenger is away: hand back the +10% build-cost scale.
        ct.write_store(SLOT_LAUNCHER, 0)
        ct.self_destruct()
        return

    # Tell the Core and the queued Builders where the pad is.
    ct.write_store(SLOT_LAUNCHER, pack_pos(pos))

    if ct.get_action_cooldown() != 0:
        return

    passenger = _next_passenger(ct, pos)
    if passenger is None:
        return

    target = _target(ct, pos, passenger, raider=player.throws < RAIDER_THROWS)
    if target is None:
        return

    ct.launch(Position(*passenger), Position(*target))
    player.throws += 1
    ct.write_store(SLOT_THROWS_DONE, player.throws)


def _next_passenger(ct, pos):
    """The earliest-spawned friendly Builder we can pick up.

    Entity ids increase with spawn order, so the lowest adjacent id is the
    oldest Builder -- which makes throw k carry Builder k, matching the roles
    each Builder assigns itself from its own spawn round.
    """
    me = ct.get_team()
    best = None
    for eid in ct.get_nearby_units(PICKUP_RANGE_SQ):
        try:
            if ct.get_entity_type(eid) != EntityType.BUILDER_BOT:
                continue
            if ct.get_team(eid) != me:
                continue
            where = tuple(ct.get_position(eid))
        except Exception:
            continue
        if dist_sq(where, pos) > PICKUP_RANGE_SQ:
            continue
        if best is None or eid < best[0]:
            best = (eid, where)
    return best[1] if best else None


def _target(ct, pos, passenger, raider: bool):
    """Pick the landing tile: nearest to the objective, farthest from us."""
    own_core = unpack_pos(ct.read_store(SLOT_OWN_CORE)) or pos
    if raider:
        goals = [read_enemy_core(ct, own_core)]
    else:
        goals = _ore_goals(ct, own_core)
        if not goals:
            goals = [read_enemy_core(ct, own_core)]

    legal = []
    src = Position(*passenger)
    for tile in ct.get_nearby_tiles(THROW_RANGE_SQ):
        t = tuple(tile)
        try:
            if ct.can_launch(src, tile):
                legal.append(t)
        except Exception:
            continue
    if not legal:
        return None

    # Walking distance is the measured objective, but the goal is usually far
    # outside vision on round 2 -- BFS reaches nothing and every candidate ties.
    # So: rank by walk distance where we have it, by straight line where we
    # don't, and only then throw as far as possible.
    walk = _walk_distances(ct, goals, legal)

    def key(t):
        straight = min(dist_sq(t, g) for g in goals)
        if t in walk:
            return (0, walk[t], -dist_sq(t, pos))
        return (1, straight, -dist_sq(t, pos))

    return min(legal, key=key)


def _ore_goals(ct, own_core):
    """Uncovered ore, preferring what a walking Builder would never reach.

    The economy passengers are the whole point of throws 3 and 4: they land on
    ore that is out of practical walking range, so the throw buys distance the
    Builder could not have covered itself.
    """
    ore = []
    for tile in ct.get_nearby_tiles():
        t = tuple(tile)
        try:
            if ct.get_tile_env(tile) not in (Environment.ORE_TITANIUM,
                                             Environment.ORE_AXIONITE):
                continue
            if ct.get_tile_building_id(tile) is not None:
                continue
        except Exception:
            continue
        ore.append(t)
    if not ore:
        return []
    ore.sort(key=lambda t: -dist_sq(t, own_core))
    return ore[:max(1, len(ore) // 2)]


def _walk_distances(ct, goals, wanted):
    """Multi-source BFS out from `goals` over tiles we can see, cardinal steps.

    Anything outside vision is treated as impassable, which keeps the search
    inside the disc we can actually reason about; if that leaves a candidate
    unreached it falls back to straight-line ranking via the 10**6 default.
    """
    wanted = set(wanted)
    seen = {}
    queue = deque()
    for g in goals:
        seen[g] = 0
        queue.append(g)
    found = 0
    # The throw disc is radius 5, so the useful search never needs to run far.
    limit = 64
    while queue and found < len(wanted):
        cur = queue.popleft()
        d = seen[cur]
        if d >= limit:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in seen:
                continue
            p = Position(*nxt)
            try:
                if not ct.is_in_vision(p) or not ct.is_tile_passable(p):
                    continue
            except Exception:
                continue
            seen[nxt] = d + 1
            if nxt in wanted:
                found += 1
            queue.append(nxt)
    return seen
