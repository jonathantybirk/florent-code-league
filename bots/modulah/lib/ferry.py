"""Moving Builders faster than they can walk.

A Launcher throws a Builder up to `dist_sq 26` -- about five tiles -- in a
single round, over anything in between. Walking that costs five rounds and can
be blocked outright.

Why this module exists, from the measurements rather than from taste. Against
steward, on the same 3.7 Builders:

    harvesters   aegis 3.8   steward 2.3
    conveyors    aegis ~11   steward 12.1
    gunners      aegis 3.3   steward 4.4
    launchers    aegis 0.0   steward 1.7

Economy was eliminated as the gap (we out-collect it, 878 to 788). So was
turret scheduling -- four separate routes to an earlier Gunner all cost more
titanium than they bought. So was workforce size: capping at 4 reproduced
steward's headcount exactly and changed nothing. What is left is what each
Builder gets done per turn, and the one structural thing we lack is any way to
move one faster than walking.

No request protocol
-------------------
The obvious design is a request/response handshake in the store, and it would
cost two rounds: a Builder's write at round R is not readable until R+1, so
asking and being served cannot happen in the same round.

It is also unnecessary. Builders already publish the tile they are committed
to (`comms.BUILDER_TARGET_X/Y`), so a Launcher can read what its neighbours
are trying to reach and serve them unasked. The published target is one round
stale, which does not matter for a destination that stays put.
"""

from __future__ import annotations

from fcode import EntityType, GameError, Position

from geometry import building_at, in_bounds

# A throw reaches dist_sq 26. Candidates are ranked by how much closer to the
# goal they land and the best few are checked against the engine, because
# can_launch is a pyo3 crossing and the platform kills a unit over 10 ms.
THROW_RANGE_SQ = 26
MAX_CANDIDATES = 18

# Below this the walk is as fast as the negotiation, and a throw that saves
# one tile is not worth a Builder's turn.
MIN_GAIN_SQ = 9


def adjacent_friendly_builders(ct, pos: Position):
    """Builder bots of ours standing next to this Launcher."""
    me = ct.get_team()
    out = []
    for uid in ct.get_nearby_units(dist_sq=2):
        try:
            if ct.get_team(uid) != me:
                continue
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            p = ct.get_position(uid)
        except GameError:
            continue
        if abs(p.x - pos.x) + abs(p.y - pos.y) == 1:
            out.append((uid, p))
    return out


def best_landing(ct, bot_pos: Position, goal: Position):
    """Legal landing tile that gets the Builder closest to `goal`, or None.

    Returns None unless the throw is worth a turn -- see MIN_GAIN_SQ. A throw
    that lands the passenger no nearer than it started is a round spent to
    stand still.
    """
    here = bot_pos.distance_squared(goal)
    cands = []
    r = int(THROW_RANGE_SQ ** 0.5) + 1
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if dx * dx + dy * dy > THROW_RANGE_SQ:
                continue
            tile = Position(bot_pos.x + dx, bot_pos.y + dy)
            if not in_bounds(ct, tile) or building_at(ct, tile) is not None:
                continue
            gain = here - tile.distance_squared(goal)
            if gain >= MIN_GAIN_SQ:
                cands.append((-gain, tile))
    if not cands:
        return None
    cands.sort(key=lambda c: c[0])
    for _, tile in cands[:MAX_CANDIDATES]:
        try:
            if ct.can_launch(bot_pos, tile):
                return tile
        except GameError:
            continue
    return None


def serve(ct, read_target) -> bool:
    """Throw one adjacent Builder toward whatever it published. True if thrown.

    `read_target` is supplied by the caller so this module never has to know
    the store schema -- it takes a unit id and returns a Position or None.
    """
    try:
        pos = ct.get_position()
    except GameError:
        return False
    for uid, bot_pos in adjacent_friendly_builders(ct, pos):
        goal = read_target(uid)
        if goal is None:
            continue
        tile = best_landing(ct, bot_pos, goal)
        if tile is None:
            continue
        try:
            ct.launch(bot_pos, tile)
            return True
        except GameError:
            continue
    return False
