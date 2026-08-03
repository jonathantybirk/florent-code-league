"""Shared stateless helpers."""

from collections import deque

import atlas
from constants import ATLAS_ENABLED

from fcode import Direction, Position

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
D8 = tuple(d for d in Direction if d != Direction.CENTRE)

_OFFSET = {
    Direction.NORTH: (0, -1),
    Direction.NORTHEAST: (1, -1),
    Direction.EAST: (1, 0),
    Direction.SOUTHEAST: (1, 1),
    Direction.SOUTH: (0, 1),
    Direction.SOUTHWEST: (-1, 1),
    Direction.WEST: (-1, 0),
    Direction.NORTHWEST: (-1, -1),
    Direction.CENTRE: (0, 0),
}


def offset(direction: Direction) -> tuple[int, int]:
    return _OFFSET[direction]


def pack_pos(pos) -> int:
    """Encode a position in one store slot; 0 stays reserved for 'unknown'."""
    x, y = pos
    return 1 + x * 32 + y


def unpack_pos(value: int) -> tuple[int, int] | None:
    if value == 0:
        return None
    value -= 1
    return value // 32, value % 32


def dist_sq(a, b) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def chebyshev(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def facing_toward(frm, to) -> Direction:
    """The 8-way direction whose ray points most nearly from `frm` at `to`."""
    dx, dy = to[0] - frm[0], to[1] - frm[1]
    if dx == 0 and dy == 0:
        return Direction.NORTH
    best, best_score = Direction.NORTH, -2.0
    norm = (dx * dx + dy * dy) ** 0.5
    for d in D8:
        ox, oy = _OFFSET[d]
        scale = (ox * ox + oy * oy) ** 0.5
        score = (ox * dx + oy * dy) / (norm * scale)
        if score > best_score:
            best, best_score = d, score
    return best


def nearest_cardinal(direction: Direction) -> Direction:
    ox, oy = _OFFSET[direction]
    if abs(ox) >= abs(oy):
        return Direction.EAST if ox > 0 else Direction.WEST
    return Direction.SOUTH if oy > 0 else Direction.NORTH


def enemy_core_guess(ct, own_core) -> tuple[int, int]:
    """Where the enemy Core is: looked up if we know the map, reflected if not.

    Reflecting our Core through the map centre is the best blind rule available
    (median error 1 tile over the 41 Core layouts in the sample, against 12 and
    14 for the two axis mirrors) -- but 1 tile is exactly enough to flip a tie,
    and reproducing real games showed that is what pushed the round-1 Launcher
    onto the wrong side on `twins` and `aurora`.

    Pantheon does not make that error, which is itself evidence: at round 1 the
    enemy Core is far outside anyone's vision (Builder r^2=20), so being right
    means recognising the map, not inferring it. The published pool is uniquely
    keyed by (width, height, own Core), so that lookup is available to anyone.
    """
    w, h = ct.get_map_width(), ct.get_map_height()
    if ATLAS_ENABLED:
        known = atlas.identify(w, h, tuple(own_core))
        if known is not None:
            return known.enemy_core
    return (w - 1 - own_core[0], h - 1 - own_core[1])


def read_enemy_core(ct, own_core) -> tuple[int, int]:
    known = unpack_pos(ct.read_store(1))
    return known if known is not None else enemy_core_guess(ct, own_core)


def sight_enemy_core(ct) -> None:
    """Publish the enemy Core's real position the first time anyone sees it."""
    from fcode import EntityType
    if ct.read_store(1) != 0:
        return
    me = ct.get_team()
    for eid in ct.get_nearby_buildings():
        try:
            if ct.get_entity_type(eid) == EntityType.CORE and ct.get_team(eid) != me:
                ct.write_store(1, pack_pos(tuple(ct.get_position(eid))))
                return
        except Exception:
            continue


def step_toward(ct, target, horizon: int = 6) -> bool:
    """One cardinal step along a short path toward `target`.

    Greedy stepping deadlocks against any concave wall -- the Builder shuffles
    between two tiles forever, which on a 1000-round map is the whole game. So
    plan over what we can actually see: breadth-first out to `horizon` steps
    across passable, in-vision tiles, take whichever reachable tile lands
    nearest the target, and walk the first step of that path.
    """
    if ct.get_move_cooldown() != 0:
        return False
    pos = tuple(ct.get_position())
    target = tuple(target)
    if pos == target:
        return False

    # first_step[tile] = the direction we left `pos` by to reach it
    first_step = {pos: None}
    seen = {pos: 0}
    queue = deque([pos])
    best, best_key = None, None
    while queue:
        cur = queue.popleft()
        depth = seen[cur]
        if cur != pos:
            key = (dist_sq(cur, target), depth)
            if best_key is None or key < best_key:
                best, best_key = cur, key
        if depth >= horizon:
            continue
        for d in CARDINALS:
            ox, oy = offset(d)
            nxt = (cur[0] + ox, cur[1] + oy)
            if nxt in seen:
                continue
            p = Position(*nxt)
            try:
                if not ct.is_in_vision(p) or not ct.is_tile_passable(p):
                    continue
                # Another Builder standing there blocks us this turn, but it
                # will move -- treat it as passable beyond the first step only.
                if depth == 0 and ct.get_tile_builder_bot_id(p) is not None:
                    continue
            except Exception:
                continue
            seen[nxt] = depth + 1
            first_step[nxt] = first_step[cur] if cur != pos else d
            queue.append(nxt)

    if best is None or first_step.get(best) is None:
        return False
    if dist_sq(best, target) >= dist_sq(pos, target):
        return False          # nothing visible improves on standing still
    d = first_step[best]
    if ct.can_move(d):
        ct.move(d)
        return True
    return False
