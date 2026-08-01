"""Per-unit world model: terrain memory, symmetry inference and pathing.

Units share only sixteen integers, so every Builder maintains its own map of
whatever it has personally seen. Nothing here reads map files: the enemy half
is predicted purely from the rulebook guarantee that maps are symmetric.
"""

from collections import deque

from fcode import EntityType, Environment

from constants import (
    CLAIM_SLOTS,
    D4_DELTAS,
    D8,
    D8_DELTAS,
    SLOT_ENEMY_CORE,
    SLOT_SYMMETRY_A,
    SLOT_SYMMETRY_B,
    WALKABLE_BUILDINGS,
)
from utils import pack_pos, unpack_pos

# Symmetry hypotheses, in the order their bits live in the rejection mask.
ROT180, MIRROR_X, MIRROR_Y = 0, 1, 2


def init(p, ct):
    p.w, p.h = ct.get_map_width(), ct.get_map_height()
    p.seen = set()
    p.terrain = {}
    p.walls = set()
    p.ores = set()
    p.solids = set()          # non-walkable buildings (either team)
    p.conveyors = {}          # own walkable buildings: tile -> facing
    p.my_harvesters = set()
    # Bots are not buildings and do not persist in memory, but they do
    # make a tile impassable this round. Without this a Builder walks
    # into an occupied corridor forever, because its remembered map says
    # the tile is free while can_move() keeps refusing it.
    p.crowded = set()
    p.enemy_builders = set()
    p.enemy_buildings = {}    # tile -> EntityType
    # Producers are omnidirectional and do not care whose building receives a
    # stack, so an enemy Harvester is a perfectly good ammunition supply.
    p.enemy_output = {}       # tile -> facing, or None for a Harvester
    p.core = None
    p.foot = set()
    p.rejected = 0
    p.enemy_core = None
    # Terrain mirrored from our own half once the symmetry is pinned down.
    p.mirror_walls = set()
    p.mirror_ores = set()
    p.mirror_seen = set()
    p._pred_index = None
    p._pred_size = -1


def sense(p, ct):
    """Fold this round's vision into the remembered map."""
    team = ct.get_team()
    me = ct.get_id()
    p.crowded = set()
    p.enemy_builders = set()
    for tile in ct.get_nearby_tiles():
        occupant = ct.get_tile_builder_bot_id(tile)
        if occupant is not None and occupant != me:
            p.crowded.add((tile.x, tile.y))
            if ct.get_team(occupant) != team:
                p.enemy_builders.add((tile.x, tile.y))
        key = (tile.x, tile.y)
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
            p.my_harvesters.discard(key)
            p.conveyors.pop(key, None)
            p.enemy_buildings.pop(key, None)
            p.enemy_output.pop(key, None)
            continue
        kind = ct.get_entity_type(bid)
        mine = ct.get_team(bid) == team
        if kind == EntityType.CORE:
            if mine:
                p.core = (ct.get_position(bid).x, ct.get_position(bid).y)
            else:
                anchor = ct.get_position(bid)
                p.enemy_core = (anchor.x, anchor.y)
                if ct.read_store(SLOT_ENEMY_CORE) == 0:
                    ct.write_store(SLOT_ENEMY_CORE, pack_pos(p.enemy_core))
        if mine:
            p.enemy_buildings.pop(key, None)
            p.enemy_output.pop(key, None)
        else:
            p.enemy_buildings[key] = kind
            if kind == EntityType.HARVESTER:
                p.enemy_output[key] = None
            elif kind in WALKABLE_BUILDINGS:
                p.enemy_output[key] = ct.get_direction(bid)
            else:
                p.enemy_output.pop(key, None)
        if kind == EntityType.HARVESTER and mine:
            p.my_harvesters.add(key)
        else:
            p.my_harvesters.discard(key)
        if kind in WALKABLE_BUILDINGS:
            p.solids.discard(key)
            if mine:
                p.conveyors[key] = ct.get_direction(bid)
            else:
                p.conveyors.pop(key, None)
        else:
            p.solids.add(key)
            p.conveyors.pop(key, None)
    if p.core and not p.foot:
        x, y = p.core
        p.foot = {(x + dx, y + dy) for dx in (0, 1) for dy in (0, 1)}


# --------------------------------------------------------------------------
# Symmetry


def transform(p, tile, index):
    """Map a tile onto its counterpart under one symmetry hypothesis."""
    x, y = tile
    if index == ROT180:
        return p.w - 1 - x, p.h - 1 - y
    if index == MIRROR_X:
        return p.w - 1 - x, y
    return x, p.h - 1 - y


def core_candidates(p):
    """Enemy Core anchors implied by each surviving symmetry hypothesis."""
    x, y = p.core
    return ((p.w - 2 - x, p.h - 2 - y), (p.w - 2 - x, y), (x, p.h - 2 - y))


def update_symmetry(p, ct, slot):
    """Reject hypotheses contradicted by anything this unit has observed."""
    rejected = p.rejected | team_rejected(ct)
    for index, candidate in enumerate(core_candidates(p)):
        if rejected & (1 << index):
            continue
        footprint = [(candidate[0] + dx, candidate[1] + dy)
                     for dx in (0, 1) for dy in (0, 1)]
        if all(inside(p, t) and t in p.seen for t in footprint):
            if not any(p.enemy_buildings.get(t) == EntityType.CORE
                       for t in footprint):
                rejected |= 1 << index
                continue
        for tile, env in p.terrain.items():
            paired = transform(p, tile, index)
            if paired in p.terrain and p.terrain[paired] != env:
                rejected |= 1 << index
                break
    p.rejected = rejected
    ct.write_store(slot, rejected)

    if p.enemy_core is None:
        packed = ct.read_store(SLOT_ENEMY_CORE)
        if packed:
            p.enemy_core = unpack_pos(packed)
    if p.enemy_core is None:
        alive = surviving(p, ct)
        if len(alive) == 1:
            p.enemy_core = alive[0]
            ct.write_store(SLOT_ENEMY_CORE, pack_pos(p.enemy_core))


def team_rejected(ct):
    return (ct.read_store(SLOT_SYMMETRY_A) | ct.read_store(SLOT_SYMMETRY_B)) & 0x7


def surviving(p, ct):
    rejected = p.rejected | team_rejected(ct)
    out = []
    for index, candidate in enumerate(core_candidates(p)):
        if not rejected & (1 << index) and candidate not in out:
            out.append(candidate)
    return out


def symmetry_index(p, ct):
    """The single surviving hypothesis index, or None while still ambiguous."""
    rejected = p.rejected | team_rejected(ct)
    alive = [i for i in range(3) if not rejected & (1 << i)]
    if len(alive) == 1:
        return alive[0]
    # Distinct hypotheses can agree on the Core anchor (square symmetric maps);
    # any of them then predicts the same mirrored ore field.
    if alive and len({core_candidates(p)[i] for i in alive}) == 1:
        return alive[0]
    return None


def refresh_prediction(p, ct):
    """Mirror observed terrain onto the unseen half.

    The rulebook guarantees the map is symmetric, so once a single hypothesis
    survives, everything this unit has walked past also describes the enemy
    half. Only terrain is mirrored -- buildings must still be seen.
    """
    index = symmetry_index(p, ct)
    if index is None:
        return
    if index == p._pred_index and len(p.terrain) == p._pred_size:
        return
    p._pred_index, p._pred_size = index, len(p.terrain)
    walls, ores, seen = set(), set(), set()
    for tile, env in p.terrain.items():
        mirrored = transform(p, tile, index)
        if mirrored in p.terrain or not inside(p, mirrored):
            continue
        seen.add(mirrored)
        if env == Environment.WALL:
            walls.add(mirrored)
        elif env == Environment.ORE_TITANIUM:
            ores.add(mirrored)
    p.mirror_walls, p.mirror_ores, p.mirror_seen = walls, ores, seen


def known_seen(p):
    return p.seen | p.mirror_seen


def known_walls(p):
    return p.walls | p.mirror_walls


def known_ores(p):
    return p.ores | p.mirror_ores


def inside(p, tile):
    return 0 <= tile[0] < p.w and 0 <= tile[1] < p.h


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def dist_sq(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def footprint(anchor):
    return [(anchor[0] + dx, anchor[1] + dy) for dx in (0, 1) for dy in (0, 1)]


def adjacent8(p, tile):
    return {(tile[0] + dx, tile[1] + dy) for dx, dy in D8_DELTAS
            if inside(p, (tile[0] + dx, tile[1] + dy))}


def adjacent4(p, tile):
    return {(tile[0] + dx, tile[1] + dy) for dx, dy in D4_DELTAS
            if inside(p, (tile[0] + dx, tile[1] + dy))}


def blocked_tiles(p):
    """Tiles a Builder cannot stand on, as far as this unit knows."""
    return p.walls | p.mirror_walls | p.solids | p.crowded


def bfs_step(p, source, goals, treat_unseen_as_open=True):
    """First tile of a shortest 8-connected walk from source into goals."""
    if source in goals:
        return None
    blocked = blocked_tiles(p)
    prev = {source: None}
    queue = deque([source])
    found = None
    while queue:
        cur = queue.popleft()
        if cur in goals:
            found = cur
            break
        for dx, dy in D8_DELTAS:
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in prev or not inside(p, nxt) or nxt in blocked:
                continue
            if not treat_unseen_as_open and nxt not in p.seen:
                continue
            prev[nxt] = cur
            queue.append(nxt)
    if found is None:
        return None
    while prev[found] != source:
        found = prev[found]
    return found


def distance_field(p, goals):
    """Walk distance from every reachable tile to the nearest goal."""
    blocked = blocked_tiles(p)
    dist = {g: 0 for g in goals if inside(p, g)}
    queue = deque(dist)
    while queue:
        cur = queue.popleft()
        for dx, dy in D8_DELTAS:
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in dist or not inside(p, nxt) or nxt in blocked:
                continue
            dist[nxt] = dist[cur] + 1
            queue.append(nxt)
    return dist


def walk_distance(p, source, goals):
    if source in goals:
        return 0
    blocked = blocked_tiles(p)
    dist = {source: 0}
    queue = deque([source])
    while queue:
        cur = queue.popleft()
        for dx, dy in D8_DELTAS:
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in dist or not inside(p, nxt) or nxt in blocked:
                continue
            dist[nxt] = dist[cur] + 1
            if nxt in goals:
                return dist[nxt]
            queue.append(nxt)
    return None


def claim(ct, slots, value):
    """Take one of `slots` for `value`, or None when they are all spoken for."""
    packed = pack_pos(value)
    for slot in slots:
        if ct.read_store(slot) == packed:
            return slot
    for slot in slots:
        if ct.read_store(slot) == 0:
            ct.write_store(slot, packed)
            return slot
    return None


def unclaim(ct, slots, value):
    packed = pack_pos(value)
    for slot in slots:
        if ct.read_store(slot) == packed:
            ct.write_store(slot, 0)
            return


def claimed_positions(p, ct, slots):
    """Claims held by other units, plus anything we personally ruled out."""
    out = set(getattr(p, "rejected_ores", ()))
    for slot in slots:
        value = unpack_pos(ct.read_store(slot))
        if value:
            out.add(value)
    return out


def home_claims(ct):
    out = set()
    for slot in CLAIM_SLOTS:
        value = unpack_pos(ct.read_store(slot))
        if value:
            out.add(value)
    return out
