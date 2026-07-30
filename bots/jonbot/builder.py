"""Map-agnostic online economy planner and explorer."""

from collections import deque
import os
import sys
from typing import TYPE_CHECKING

from fcode import Controller, EntityType, Environment, GameError, Position

from constants import (
    CLAIM_SLOTS,
    D4_DELTAS,
    D8,
    FACING,
    SLOT_BUILDER_TICKET,
    SLOT_ENEMY_CORE,
    SLOT_SYMMETRY_REJECT_START,
    WALKABLE_BUILDINGS,
)
from utils import pack_pos, unpack_pos

if TYPE_CHECKING:
    from main import Player


def run(p: "Player", ct: Controller) -> None:
    try:
        _run(p, ct)
    except GameError as error:
        if os.environ.get("JONBOT_DEBUG"):
            print("GameError", ct.get_current_round(), error, file=sys.stderr, flush=True)
        # An escaping GameError permanently destroys this unit.
        return


def _run(p, ct):
    if not hasattr(p, "builder_index"):
        p.builder_index = ct.read_store(SLOT_BUILDER_TICKET)
        ct.write_store(SLOT_BUILDER_TICKET, p.builder_index + 1)
        p.w, p.h = ct.get_map_width(), ct.get_map_height()
        p.seen, p.terrain = set(), {}
        p.walls, p.ores, p.solids, p.conveyors = set(), set(), set(), {}
        p.core, p.foot = None, set()
        p.task, p.route, p.route_i, p.phase = None, [], 0, "scout"
        p.explored = set()
        p.rejected_symmetries = 0
    _sense(p, ct)
    _update_enemy_core_inference(p, ct)
    if p.core is None:
        return
    if p.phase == "scout":
        _pick(p, ct)
    if p.phase == "goto":
        _goto(p, ct)
    elif p.phase == "lay":
        _lay(p, ct)
    else:
        _explore(p, ct)


def _sense(p, ct):
    for tile in ct.get_nearby_tiles():
        key = tuple(tile)
        p.seen.add(key)
        env = ct.get_tile_env(tile)
        p.terrain[key] = env
        if env == Environment.WALL:
            p.walls.add(key)
            continue
        if env == Environment.ORE_TITANIUM:
            p.ores.add(key)
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            p.solids.discard(key)
            p.conveyors.pop(key, None)
            continue
        kind = ct.get_entity_type(bid)
        if kind == EntityType.CORE and ct.get_team(bid) != ct.get_team():
            ct.write_store(SLOT_ENEMY_CORE, pack_pos(ct.get_position(bid)))
        if kind == EntityType.CORE:
            if ct.get_team(bid) == ct.get_team():
                p.core = tuple(ct.get_position(bid))
            p.solids.add(key)
        elif kind in WALKABLE_BUILDINGS:
            p.solids.discard(key)
            if ct.get_team(bid) == ct.get_team():
                p.conveyors[key] = ct.get_direction(bid)
        else:
            p.solids.add(key)
    if p.core and not p.foot:
        x, y = p.core
        p.foot = {(x + dx, y + dy) for dx in (0, 1) for dy in (0, 1)}


def _pick(p, ct):
    claimed = {x for x in (unpack_pos(ct.read_store(s)) for s in CLAIM_SLOTS) if x}
    claimed |= p.ores & p.solids
    me, best = tuple(ct.get_position()), None
    candidates = sorted(
        p.ores - claimed,
        key=lambda ore: max(abs(ore[0] - me[0]), abs(ore[1] - me[1])),
    )
    for ore in candidates:
        route = _route(p, ore)
        travel = _distance(p, me, _adjacent(p, ore))
        if route is None or travel is None:
            continue
        # Nearest-first is robust under fog; route length breaks ties. The
        # offline planner supplies the upper bound for later score tuning.
        best = (travel, len(route), ore, route)
        break
    if best is None:
        return
    _, _, ore, route = best
    for slot in CLAIM_SLOTS:
        if ct.read_store(slot) == 0:
            ct.write_store(slot, pack_pos(ore))
            p.task, p.route, p.route_i, p.phase = ore, route, 0, "goto"
            return


def _route(p, ore):
    """Shortest cardinal ore-to-Core line, keeping trunks independent."""
    blocked = p.walls | p.foot | (p.ores - {ore}) | p.solids | set(p.conveyors)
    prev, queue, goal = {ore: None}, deque([ore]), None
    while queue and goal is None:
        cur = queue.popleft()
        for dx, dy in D4_DELTAS:
            nxt = cur[0] + dx, cur[1] + dy
            if nxt in prev or not _inside(p, nxt):
                continue
            # An orthogonally adjacent Harvester feeds the Core directly.
            if nxt in p.foot:
                prev[nxt], goal = cur, nxt
                break
            if nxt in blocked:
                continue
            prev[nxt] = cur
            queue.append(nxt)
    if goal is None:
        return None
    path, cur = [], goal
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    tiles, result = path[1:-1], []
    for i, tile in enumerate(tiles):
        nxt = tiles[i + 1] if i + 1 < len(tiles) else path[-1]
        result.append((tile, FACING[(nxt[0] - tile[0], nxt[1] - tile[1])]))
    return result


def _goto(p, ct):
    me, target = ct.get_position(), Position(*p.task)
    if 0 < me.distance_squared(target) <= 2:
        if ct.can_build_harvester(target):
            ct.build_harvester(target)
            p.solids.add(p.task)
            p.route, p.route_i, p.phase = _route(p, p.task) or [], 0, "lay"
            if not p.route:
                _done(p, ct)
        elif ct.get_tile_building_id(target) is not None:
            _done(p, ct)
        return
    _step(p, ct, target, False)


def _lay(p, ct):
    if p.route_i >= len(p.route):
        _done(p, ct)
        return
    tile, facing = p.route[p.route_i]
    me, target = ct.get_position(), Position(*tile)
    if me != target:
        _step(p, ct, target, True)
        return
    if ct.can_build_conveyor(target, facing):
        ct.build_conveyor(target, facing)
        p.conveyors[tile] = facing
    elif ct.get_tile_building_id(target) is None:
        return
    p.route_i += 1
    if p.route_i < len(p.route):
        _step(p, ct, Position(*p.route[p.route_i][0]), True)
    else:
        _done(p, ct)


def _done(p, ct):
    if p.task:
        value = pack_pos(p.task)
        for slot in CLAIM_SLOTS:
            if ct.read_store(slot) == value:
                ct.write_store(slot, 0)
                break
    p.task, p.route, p.route_i, p.phase = None, [], 0, "scout"


def _step(p, ct, target, exact):
    source = ct.get_position()
    nxt = _bfs_step(p, tuple(source), tuple(target), exact)
    if nxt:
        for direction in D8:
            if source.add(direction) == Position(*nxt) and ct.can_move(direction):
                ct.move(direction)
                return


def _bfs_step(p, source, target, exact):
    goals = {target} if exact else _adjacent(p, target)
    if source in goals:
        return None
    blocked, prev, queue = p.walls | p.foot | p.solids, {source: None}, deque([source])
    found = None
    while queue:
        cur = queue.popleft()
        if cur in goals:
            found = cur
            break
        for direction in D8:
            dx, dy = direction.delta()
            nxt = cur[0] + dx, cur[1] + dy
            if nxt in prev or not _inside(p, nxt) or nxt in blocked:
                continue
            prev[nxt] = cur
            queue.append(nxt)
    if found is None:
        return None
    while prev[found] != source:
        found = prev[found]
    return found


def _distance(p, source, goals):
    if source in goals:
        return 0
    blocked, dist, queue = p.walls | p.foot | p.solids, {source: 0}, deque([source])
    while queue:
        cur = queue.popleft()
        for direction in D8:
            dx, dy = direction.delta()
            nxt = cur[0] + dx, cur[1] + dy
            if nxt in dist or not _inside(p, nxt) or nxt in blocked:
                continue
            dist[nxt] = dist[cur] + 1
            if nxt in goals:
                return dist[nxt]
            queue.append(nxt)
    return None


def _explore(p, ct):
    me, stride = tuple(ct.get_position()), 4

    # First resolve the enemy-Core hypotheses. This is map-agnostic: targets
    # come only from dimensions, our observed Core, and rejected symmetries.
    info_target = _enemy_scout_target(p, ct)
    if info_target is not None:
        _step(p, ct, Position(*info_target), False)
        return

    choices = [(x, y) for y in range(1, p.h, stride) for x in range(1, p.w, stride)
               if (x, y) not in p.explored and (x, y) not in p.walls
               and (x, y) not in p.solids
               and (x // stride + y // stride) % 3 == p.builder_index % 3]
    if not choices:
        p.explored.clear()
        return
    target = min(choices, key=lambda q: max(abs(q[0] - me[0]), abs(q[1] - me[1])))
    # A Builder already observes radius^2 20; don't idle walking to the exact
    # centre of an area that is fully visible.
    if (target[0] - me[0]) ** 2 + (target[1] - me[1]) ** 2 <= 20:
        p.explored.add(target)
        _explore(p, ct)
        return
    _step(p, ct, Position(*target), False)


def _enemy_core_candidates(p):
    """Candidate top-left Core coordinates: rotation, x mirror, y mirror."""
    x, y = p.core
    return (
        (p.w - 2 - x, p.h - 2 - y),
        (p.w - 2 - x, y),
        (x, p.h - 2 - y),
    )


def _transform(p, tile, index):
    x, y = tile
    if index == 0:
        return p.w - 1 - x, p.h - 1 - y
    if index == 1:
        return p.w - 1 - x, y
    return x, p.h - 1 - y


def _update_enemy_core_inference(p, ct):
    """Reject symmetry hypotheses using only this Builder's observations."""
    rejected = p.rejected_symmetries | _team_rejected_symmetries(ct)
    candidates = _enemy_core_candidates(p)
    for index, candidate in enumerate(candidates):
        if rejected & (1 << index):
            continue
        # Seeing the predicted footprint without an enemy Core disproves it.
        footprint = {(candidate[0] + dx, candidate[1] + dy)
                     for dx in (0, 1) for dy in (0, 1)}
        if all(_inside(p, tile) and tile in p.seen for tile in footprint):
            found = False
            for tile in footprint:
                bid = ct.get_tile_building_id(Position(*tile))
                if (bid is not None and ct.get_team(bid) != ct.get_team()
                        and ct.get_entity_type(bid) == EntityType.CORE):
                    ct.write_store(SLOT_ENEMY_CORE, pack_pos(ct.get_position(bid)))
                    found = True
                    break
            if not found:
                rejected |= 1 << index
                continue
        # A terrain mismatch between two observed paired cells disproves it.
        for tile, env in p.terrain.items():
            paired = _transform(p, tile, index)
            if paired in p.terrain and p.terrain[paired] != env:
                rejected |= 1 << index
                break
    p.rejected_symmetries = rejected
    ct.write_store(SLOT_SYMMETRY_REJECT_START + min(p.builder_index, 1), rejected)

    surviving = {candidate for i, candidate in enumerate(candidates)
                 if not rejected & (1 << i)}
    if len(surviving) == 1 and ct.read_store(SLOT_ENEMY_CORE) == 0:
        ct.write_store(SLOT_ENEMY_CORE, pack_pos(next(iter(surviving))))


def _enemy_scout_target(p, ct):
    """Assign unresolved candidate footprints across the two Builders."""
    if ct.read_store(SLOT_ENEMY_CORE):
        return None
    rejected = p.rejected_symmetries | _team_rejected_symmetries(ct)
    candidates = []
    for index, candidate in enumerate(_enemy_core_candidates(p)):
        if not rejected & (1 << index) and candidate not in candidates:
            candidates.append(candidate)
    if not candidates:
        return None
    # Different builder ids investigate different candidates; after a rejection
    # the modulo assignment automatically closes ranks next round.
    return candidates[p.builder_index % len(candidates)]


def _team_rejected_symmetries(ct):
    return ((ct.read_store(SLOT_SYMMETRY_REJECT_START)
             | ct.read_store(SLOT_SYMMETRY_REJECT_START + 1)) & 0x7)


def _adjacent(p, target):
    return {(target[0] + d.delta()[0], target[1] + d.delta()[1]) for d in D8
            if _inside(p, (target[0] + d.delta()[0], target[1] + d.delta()[1]))}


def _inside(p, tile):
    return 0 <= tile[0] < p.w and 0 <= tile[1] < p.h
