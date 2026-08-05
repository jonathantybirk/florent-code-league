"""General-purpose action helpers shared across Florent Code League bots.

This is the canonical source. The fcode engine only puts main.py's own
directory on sys.path (confirmed against the installed CLI's run.py, and
matches bots/strategist_learned's docstring, which flags a sys.path-append
trick as unsafe for ladder submission), and a submitted zip only contains
that bot's own directory -- so every bot that wants this module needs a
physical copy sitting next to its main.py. Never hand-edit a copy: edit
this file, then run `uv run scripts/sync_toolbox.py` to fan the change out
to every bots/<name>/toolbox.py listed in that script's TARGETS.

Every function takes the Controller (and any store slots / targets / etc.)
as plain arguments rather than assuming fixed slot numbers or bot-specific
state, so it composes with whatever strategy and comm-store layout a given
bot already uses. Nothing here is exception-safe by design -- these wrap
can_X()/X() pairs, not try/except; a bot with a fallback-on-exception
policy (see bots/strategist/main.py) should keep that at its own call
site, not inside these helpers.
"""

from __future__ import annotations

import random
from typing import Callable

from fcode import Controller, Direction, EntityType, Environment, Position, Team

# All directions except CENTRE -- useful for movement and spawning.
DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

# Cardinal directions only -- conveyors, splitters, and Builder Bot
# movement can only use these.
CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]

# The three turret types -- every unit that isn't a Core or a Builder Bot.
TURRET_TYPES = {EntityType.GUNNER, EntityType.SENTINEL, EntityType.LAUNCHER}


# ----------------------------------------------------------------------
# Position <-> communication store
# ----------------------------------------------------------------------

def pack_pos(pos: Position) -> int:
    """Encode a position into a single store slot.

    Offset by +1 so (0, 0) doesn't encode as 0, which is reserved to mean
    "no data" -- see unpack_pos.
    """
    return ((pos.x + 1) << 16) | (pos.y + 1)


def unpack_pos(val: int) -> Position | None:
    """Decode a position packed by pack_pos. None for the reserved "no
    data" value 0.
    """
    if val == 0:
        return None
    return Position((val >> 16) - 1, (val & 0xFFFF) - 1)


def write_position(ct: Controller, slot: int, pos: Position) -> None:
    """Broadcast pos to a single store slot.

    Buffered like every store write: readable by teammates next round,
    not this one.
    """
    ct.write_store(slot, pack_pos(pos))


def read_position(ct: Controller, slot: int) -> Position | None:
    """Read a position written by write_position, or None if unset."""
    return unpack_pos(ct.read_store(slot))


# ----------------------------------------------------------------------
# Direction / bounds
# ----------------------------------------------------------------------

def nearest_cardinal(d: Direction) -> Direction:
    """Snap any direction to the nearest cardinal direction.

    Conveyors, splitters, and Builder Bot movement can only face/use
    N/E/S/W. CENTRE (no clear direction -- e.g. two coincident positions)
    snaps to NORTH arbitrarily rather than raising, since callers
    generally want *a* valid facing over none.
    """
    return {
        Direction.NORTH: Direction.NORTH,
        Direction.NORTHEAST: Direction.NORTH,
        Direction.EAST: Direction.EAST,
        Direction.SOUTHEAST: Direction.EAST,
        Direction.SOUTH: Direction.SOUTH,
        Direction.SOUTHWEST: Direction.SOUTH,
        Direction.WEST: Direction.WEST,
        Direction.NORTHWEST: Direction.WEST,
        Direction.CENTRE: Direction.NORTH,
    }[d]


def in_bounds(ct: Controller, pos: Position) -> bool:
    """True if pos is on the map.

    Tile getters like get_tile_building_id() and is_tile_empty() raise
    GameError on an off-map position, so any code checking a hypothetical
    adjacent tile (rather than one already sourced from
    get_nearby_tiles()) must guard with this first -- easy to miss at map
    edges, since a unit rarely stands there during early testing.
    """
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


# ----------------------------------------------------------------------
# Sensing
# ----------------------------------------------------------------------

def locate_own_core(ct: Controller) -> Position | None:
    """Find this unit's own Core by scanning currently visible tiles.

    Filters by team, unlike a plain EntityType.CORE scan -- if the enemy
    Core is also in vision this would otherwise happily return theirs.
    Only usable once vision actually reaches a Core (true for every unit
    spawned near it, early game); cache the result once found, since the
    Core never moves.
    """
    my_team = ct.get_team()
    for tile in ct.get_nearby_tiles():
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            continue
        if ct.get_entity_type(bid) == EntityType.CORE and ct.get_team(bid) == my_team:
            return tile
    return None


def find_nearest_ore(ct: Controller, pos: Position | None = None) -> Position | None:
    """Nearest currently-visible ore tile with nothing built on it, or None.

    pos defaults to this unit's own position.
    """
    pos = pos if pos is not None else ct.get_position()
    best = None
    best_dist = None
    for tile in ct.get_nearby_tiles():
        if ct.get_tile_env(tile) != Environment.ORE_TITANIUM:
            continue
        if ct.get_tile_building_id(tile) is not None:
            continue
        d = pos.distance_squared(tile)
        if best_dist is None or d < best_dist:
            best, best_dist = tile, d
    return best


def share_ore(ct: Controller, slot: int) -> bool:
    """Broadcast the first visible unclaimed ore tile to slot for teammates.

    Returns True if something was broadcast this round.
    """
    for tile in ct.get_nearby_tiles():
        if ct.get_tile_env(tile) == Environment.ORE_TITANIUM and ct.get_tile_building_id(tile) is None:
            write_position(ct, slot, tile)
            return True
    return False


def find_nearest_enemy(ct: Controller, radius_sq: int | None = None) -> Position | None:
    """Closest enemy entity (turret, other building, or Builder Bot)
    within radius_sq of this unit's own position, or None.

    Uses get_nearby_entities -- the superset of units and buildings --
    rather than get_nearby_units alone, which would miss e.g. an enemy
    Harvester or Barrier encroaching nearby.
    """
    pos = ct.get_position()
    my_team = ct.get_team()
    best = None
    best_dist = None
    for uid in ct.get_nearby_entities(dist_sq=radius_sq):
        if ct.get_team(uid) == my_team:
            continue
        d = pos.distance_squared(ct.get_position(uid))
        if best_dist is None or d < best_dist:
            best, best_dist = ct.get_position(uid), d
    return best


def count_nearby_friendly_turrets(ct: Controller, radius_sq: int) -> int:
    """Count of this unit's own team's turrets (Gunner/Sentinel/Launcher)
    within radius_sq of this unit's own position."""
    my_team = ct.get_team()
    return sum(
        1
        for uid in ct.get_nearby_units(dist_sq=radius_sq)
        if ct.get_team(uid) == my_team and ct.get_entity_type(uid) in TURRET_TYPES
    )


# ----------------------------------------------------------------------
# Movement
# ----------------------------------------------------------------------

class StuckTracker:
    """Counts consecutive rounds a unit's position hasn't changed.

    Owns no Controller state of its own -- create one per persistent unit
    (e.g. as a Player attribute) and call update(pos) once per round.
    """

    def __init__(self) -> None:
        self.last_pos: Position | None = None
        self.stuck_rounds = 0

    def update(self, pos: Position) -> int:
        if self.last_pos == pos:
            self.stuck_rounds += 1
        else:
            self.stuck_rounds = 0
        self.last_pos = pos
        return self.stuck_rounds


def try_move_toward(
    ct: Controller,
    target: Position,
    *,
    before_step: Callable[[Position], None] | None = None,
) -> bool:
    """Attempt one step toward target this round.

    Tries the direct cardinal direction, then its two neighbours, then
    every other cardinal direction in random order -- so a unit boxed in
    on its preferred side can still escape instead of stalling.

    If before_step is given, it's called with each destination tile
    *before* that direction's can_move() check, once per candidate
    direction actually tried this round (in bounds, only) -- for a bot
    that wants to do something to the tile it's about to step onto, e.g.
    dropping infrastructure as it walks. Runs even for a direction that
    turns out to be blocked, matching "try to improve this tile whenever
    we consider stepping on it," not "only once we succeed."

    Returns whether a move actually happened. Doesn't build anything
    itself and tracks no state, so it composes with StuckTracker and
    whatever target-picking a bot already has.
    """
    pos = ct.get_position()
    desired = pos.direction_to(target)
    if desired == Direction.CENTRE:
        return False

    primary = [desired, desired.rotate_left(), desired.rotate_right()]
    remaining = [d for d in CARDINALS if d not in primary]
    random.shuffle(remaining)

    for d in primary + remaining:
        if not d.is_cardinal():
            continue
        next_pos = pos.add(d)
        if before_step is not None and in_bounds(ct, next_pos):
            before_step(next_pos)
        if ct.can_move(d):
            ct.move(d)
            return True
    return False


def explore_randomly(ct: Controller) -> bool:
    """Take one wall-avoiding random step, preferring open (EMPTY) ground.

    For a unit with no target at all -- pure exploration, not navigation.
    """
    pos = ct.get_position()
    open_dirs = [
        d for d in CARDINALS
        if ct.can_move(d) and ct.get_tile_env(pos.add(d)) == Environment.EMPTY
    ]
    options = open_dirs or [d for d in CARDINALS if ct.can_move(d)]
    if not options:
        return False
    ct.move(random.choice(options))
    return True


# ----------------------------------------------------------------------
# Building
# ----------------------------------------------------------------------

def try_build_harvester_on_ore(ct: Controller) -> Position | None:
    """Build a Harvester on an adjacent ore tile if possible.

    Returns the built position, or None if no adjacent tile qualified.
    """
    pos = ct.get_position()
    for d in CARDINALS:
        tile = pos.add(d)
        # get_tile_env() is a raw getter, not a can_* check -- it raises on
        # an out-of-bounds tile (unlike can_build_harvester, which would
        # just return False), so in_bounds must run first.
        if not in_bounds(ct, tile):
            continue
        if ct.get_tile_env(tile) == Environment.ORE_TITANIUM and ct.can_build_harvester(tile):
            ct.build_harvester(tile)
            return tile
    return None


def try_build_conveyor_facing(ct: Controller, pos: Position, target: Position) -> bool:
    """Place a conveyor directly at pos, facing the cardinal direction
    nearest target.

    Typical use: pos is a tile a Builder Bot is about to step onto, target
    is the Core -- lets a bot lay track as it walks.
    """
    facing = nearest_cardinal(pos.direction_to(target))
    if ct.can_build_conveyor(pos, facing):
        ct.build_conveyor(pos, facing)
        return True
    return False


def try_build_conveyor_toward(ct: Controller, from_pos: Position, target: Position) -> bool:
    """Place a single conveyor one step out from from_pos, facing target.

    Typical use: from_pos is a Harvester you just built, which can't have
    a conveyor built on its own tile -- this places one on the next tile
    toward target instead, starting (but not completing) a supply line.
    This is the one-segment primitive; a full chain means calling
    try_build_conveyor_facing repeatedly while walking, or a
    purpose-written multi-segment router.
    """
    facing = nearest_cardinal(from_pos.direction_to(target))
    conv_pos = from_pos.add(facing)
    if not in_bounds(ct, conv_pos):
        return False
    return try_build_conveyor_facing(ct, conv_pos, target)


def try_build_barrier(ct: Controller, pos: Position) -> bool:
    """Build a Barrier on an adjacent tile if possible.

    A Barrier costs the same as a Conveyor (see get_barrier_cost) but
    just blocks the tile -- no facing, nothing routed. Useful for sealing
    a gap in a defensive perimeter, or denying a tile outright.
    """
    if ct.can_build_barrier(pos):
        ct.build_barrier(pos)
        return True
    return False


def try_build_gunner_facing(
    ct: Controller,
    facing: Direction,
    *,
    near: Position | None = None,
    max_dist_sq: int | None = None,
) -> Position | None:
    """Build a Gunner on an adjacent tile facing `facing`.

    If near and max_dist_sq are both given, refuses to build unless this
    unit's own position is within range of near -- e.g. keep Gunners
    close to the Core rather than scattered wherever a Builder happens to
    be. Returns the built position, or None.
    """
    pos = ct.get_position()
    if near is not None and max_dist_sq is not None and pos.distance_squared(near) > max_dist_sq:
        return None
    for d in DIRECTIONS:
        build_pos = pos.add(d)
        if ct.can_build_gunner(build_pos, facing):
            ct.build_gunner(build_pos, facing)
            return build_pos
    return None


def try_heal_adjacent(ct: Controller) -> Position | None:
    """Heal the first adjacent tile with damaged friendly HP, if any."""
    pos = ct.get_position()
    for d in CARDINALS:
        target = pos.add(d)
        if ct.can_heal(target):
            ct.heal(target)
            return target
    return None


def try_sabotage_adjacent(ct: Controller) -> Position | None:
    """Damage an adjacent enemy building, if any. Mirrors
    try_heal_adjacent's shape.

    ct.fire() only ever damages a building on an adjacent tile, never a
    unit (see docs/official/docs/game-rules-builder-bot.txt) -- this is
    sabotage of encroaching or targeted enemy infrastructure, not a way
    to fight off an attacking Builder Bot or turret directly.
    """
    pos = ct.get_position()
    my_team = ct.get_team()
    for d in CARDINALS:
        target = pos.add(d)
        if not in_bounds(ct, target):
            continue
        bid = ct.get_tile_building_id(target)
        if bid is None or ct.get_team(bid) == my_team:
            continue
        if ct.can_fire(target):
            ct.fire(target)
            return target
    return None


def try_spawn_builder(ct: Controller, *, shuffle: bool = True) -> int | None:
    """Core only: spawn a Builder Bot on any tile in spawn range.

    Returns the new unit's id, or None if no legal tile / can't afford it.
    shuffle=False always tries the same tile order, which is cheaper but
    biases which tile gets used first every round.
    """
    tiles = list(ct.get_nearby_tiles(dist_sq=2))
    if shuffle:
        random.shuffle(tiles)
    for pos in tiles:
        if ct.can_spawn(pos):
            return ct.spawn_builder(pos)
    return None


# ----------------------------------------------------------------------
# Combat / economy
# ----------------------------------------------------------------------

def tile_occupant_team(ct: Controller, pos: Position) -> Team | None:
    """Team owning whatever occupies pos (a Builder Bot or a building),
    or None if the tile is unoccupied.

    get_gunner_target()/can_fire() don't filter by team on their own --
    the ray stops at the first targetable tile whether it's friend or
    foe, and can_fire only checks range/ammo/legality, not ownership --
    so a caller that must not hit its own side (see auto_fire) needs
    this.
    """
    bid = ct.get_tile_builder_bot_id(pos)
    if bid is None:
        bid = ct.get_tile_building_id(pos)
    if bid is None:
        return None
    return ct.get_team(bid)


def auto_fire(ct: Controller) -> bool:
    """Gunner only: fire at whatever get_gunner_target() finds; if its
    fixed facing has nothing on it (or has a teammate on it), rotate
    toward the nearest enemy this unit could actually hit once turned.

    A Gunner's facing line is set at build time and never moves on its
    own -- without the rotate fallback, a Gunner can only ever hit
    whatever happens to wander onto that one ray, including never once
    engaging a stationary enemy turret built off to the side. Only
    Sentinels and Launchers can't rotate (see try_rotate_toward_enemy),
    so this stays correct if called for those too.

    get_gunner_target() returns the closest targetable tile regardless of
    team -- a teammate walking across the ray is the ordinary case, not
    an error -- so this must check tile_occupant_team itself; can_fire()
    alone would happily let a Gunner shoot its own side.
    """
    target = ct.get_gunner_target()
    if (
        target is not None
        and tile_occupant_team(ct, target) != ct.get_team()
        and ct.can_fire(target)
    ):
        ct.fire(target)
        return True
    try_rotate_toward_enemy(ct)
    return False


def try_rotate_toward_enemy(ct: Controller) -> bool:
    """Gunner only: rotate to face the nearest enemy this unit could
    actually hit once turned, if any and if affordable.

    Rotation costs titanium and a round of cooldown (see
    docs/official/docs/robot-api.txt), so it's only worth paying when the
    new facing yields a real firing solution -- can_fire_from checks the
    line for range/obstacles/terrain; a bare compass bearing toward the
    enemy does not, and would happily spend titanium to turn and still
    hit nothing. A no-op (returns False) for Sentinels/Launchers, which
    can't rotate at all.
    """
    if ct.get_entity_type() != EntityType.GUNNER:
        return False
    my_team = ct.get_team()
    pos = ct.get_position()
    enemies = sorted(
        (uid for uid in ct.get_nearby_entities() if ct.get_team(uid) != my_team),
        key=lambda uid: pos.distance_squared(ct.get_position(uid)),
    )
    for uid in enemies:
        target = ct.get_position(uid)
        for d in DIRECTIONS:
            if not ct.can_fire_from(pos, d, EntityType.GUNNER, target):
                continue
            if ct.can_rotate(d):
                ct.rotate(d)
                return True
    return False


def maintain_ammo(ct: Controller, target_ammo: int, chunk: int) -> bool:
    """Core only: top up team ammunition to at least target_ammo.

    Converts chunk titanium at a time (at most one conversion per team
    per turn, so calling this more than once a round from the Core has no
    extra effect). Returns whether a conversion happened this round.
    """
    if ct.get_global_ammo() < target_ammo and ct.can_convert_ammo(chunk):
        ct.convert_ammo(chunk)
        return True
    return False
