"""Recognising which pool map we are on, on round zero.

The maps are published, so there is nothing to scout: dimensions plus our
Core's anchor narrow the pool to one map almost always, and to a handful of
same-shaped maps for ten of the seating keys.  Those are settled against the
terrain the unit can actually see, which the Core alone resolves on its first
round -- its vision radius^2 of 36 covers far more tiles than any two maps in
the pool agree on.

If nothing matches -- an unpublished map, or a pool update we have not
regenerated for -- `identify` returns None and the caller has no plan.  That
is deliberate: this module either knows everything or nothing, and a bot built
on half-knowledge of the terrain is harder to reason about than one that sits
out an unfamiliar map.
"""

from fcode import Environment, EntityType

from atlas_data import INDEX, MAPS
from board import Board

_ENV = {"#": Environment.WALL, "O": Environment.ORE_TITANIUM,
        ".": Environment.EMPTY}


def home_anchor(ct):
    """Our Core's 2x2 anchor, as seen from any of our units.

    A Builder spawns on the Core's ring and its vision radius^2 of 20 covers
    the whole footprint, so this succeeds on the Builder's very first round.
    """
    if ct.get_entity_type() == EntityType.CORE:
        return tuple(ct.get_position())
    team = ct.get_team()
    for ident in ct.get_nearby_buildings():
        try:
            if (ct.get_entity_type(ident) == EntityType.CORE
                    and ct.get_team(ident) == team):
                return tuple(ct.get_position(ident))
        except Exception:
            continue
    return None


def identify(ct, home):
    """The Board we are playing on, or None if the map is not in the atlas."""
    if home is None:
        return None
    candidates = INDEX.get((ct.get_map_width(), ct.get_map_height(), home))
    if not candidates:
        return None
    if len(candidates) > 1:
        candidates = [entry for entry in candidates if _agrees(ct, entry[0])]
    if len(candidates) != 1:
        return None
    name, away = candidates[0]
    width, height, rows, _ = MAPS[name]
    return Board(name, width, height, rows, home, away)


def _agrees(ct, name) -> bool:
    """Whether every tile this unit can see matches the atlas copy of `name`."""
    rows = MAPS[name][2]
    for position in ct.get_nearby_tiles():
        x, y = position.x, position.y
        try:
            if ct.get_tile_env(position) != _ENV[rows[y][x]]:
                return False
        except Exception:
            return False
    return True
