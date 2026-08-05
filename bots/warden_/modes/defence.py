"""DEFENCE mode: guard the Core -- heal, sabotage adjacent enemy
infrastructure, emplace Gunners, and seal any open gap in the Core's
immediate ring with cheap Barriers.

A Builder Bot can never fight an enemy unit directly (ct.fire() only ever
damages a building -- see docs/official/docs/game-rules-builder-bot.txt),
so actual anti-unit defense comes from the Gunners this mode builds; they
auto-fire independently once placed (see main.py's GUNNER branch).

Turret placement is biased toward wherever the threat actually is (see
_guard_position): a defender holds a spot on the Core's threatened side
before it's ever eligible to build, rather than emplacing wherever it
happened to be standing when a threat was first noticed -- otherwise a
turret can land facing (or sitting behind) the wrong side of the Core
entirely, which is as good as not having one.

Ring-sealing (_find_unsealed_ring_tile) is a small, deliberately simpler
take on the walling seen in bots/test/luc/vidar's builder.py (its
_core_seal/_bulwark machinery computes a whole threat-disc, tracks a
per-tile "already checked" cache, and re-verifies a closed ring
periodically since Barriers get shot out of sight): here, a defender with
nothing more urgent to do just checks the Core's 8 orthogonally-adjacent
tiles for a genuinely empty one and plugs it with a Barrier. Any existing
building there already -- a Conveyor feeding the Core, a Gunner, an
earlier Barrier -- counts as sealed and is left alone, so this never
doubles up on infrastructure that already blocks the tile.
"""

from __future__ import annotations

import random

from fcode import Controller, Direction, Position

from constants import (
    DEFENCE_RADIUS_SQ,
    MAX_DEFENCE_TURRETS_NEAR_CORE,
    PATROL_RADIUS_SQ,
    SLOT_THREAT_POS,
)
from state import BuilderState
from toolbox import (
    CARDINALS,
    DIRECTIONS,
    count_nearby_friendly_turrets,
    explore_randomly,
    find_nearest_enemy,
    in_bounds,
    read_position,
    try_build_barrier,
    try_build_gunner_facing,
    try_heal_adjacent,
    try_move_toward,
    try_sabotage_adjacent,
)


def _guard_position(core_pos: Position, threat_pos: Position | None, ring_radius_sq: int) -> Position:
    """A point near the Core on the side facing threat_pos, so a
    defender posted here -- and any turret it builds once it arrives --
    actually covers the approach instead of landing on whatever side of
    the Core it happened to be standing on. Falls back to core_pos
    itself (hold right at the Core) with no threat direction to orient
    toward yet.
    """
    if threat_pos is None:
        return core_pos
    dx = threat_pos.x - core_pos.x
    dy = threat_pos.y - core_pos.y
    if dx == 0 and dy == 0:
        return core_pos
    steps = max(abs(dx), abs(dy))
    ring = ring_radius_sq**0.5
    scale = ring / steps
    return Position(core_pos.x + round(dx * scale), core_pos.y + round(dy * scale))


def _patrol_near(ct: Controller, guard_pos: Position, radius_sq: int) -> None:
    """Hold position at guard_pos -- a guard, not a wanderer."""
    pos = ct.get_position()
    if pos.distance_squared(guard_pos) > radius_sq:
        try_move_toward(ct, guard_pos)
    # else: close enough -- stay put, keep this round's action free for
    # heal/sabotage instead of pathing.


def _core_ring_tiles(core_pos: Position) -> list[Position]:
    """The 8 tiles orthogonally touching the Core's 2x2 footprint (2 per
    side) -- the cheapest tiles from which something could stand right
    next to the Core. Diagonal corner tiles aren't included: a Builder
    Bot can only ever build on an orthogonally adjacent tile, so a corner
    can never be sealed by standing next to the footprint itself anyway.
    """
    cx, cy = core_pos.x, core_pos.y
    return [
        Position(cx, cy - 1), Position(cx + 1, cy - 1),  # north
        Position(cx, cy + 2), Position(cx + 1, cy + 2),  # south
        Position(cx - 1, cy), Position(cx - 1, cy + 1),  # west
        Position(cx + 2, cy), Position(cx + 2, cy + 1),  # east
    ]


def _find_unsealed_ring_tile(ct: Controller, core_pos: Position) -> Position | None:
    """First Core-ring tile (see _core_ring_tiles) with no building on it
    at all, or None if the whole ring is already covered. Any existing
    building already blocks the tile just as well as a fresh Barrier
    would, so this only ever reports a genuine gap.
    """
    for tile in _core_ring_tiles(core_pos):
        if not in_bounds(ct, tile):
            continue
        if ct.get_tile_building_id(tile) is None:
            return tile
    return None


def _adjacent_direction(pos: Position, target: Position) -> Direction | None:
    for d in CARDINALS:
        if pos.add(d) == target:
            return d
    return None


def run(ct: Controller, state: BuilderState) -> None:
    if ct.get_action_cooldown() == 0:
        if try_heal_adjacent(ct) is None:
            try_sabotage_adjacent(ct)

    core_pos = state.core_pos
    if core_pos is None:
        explore_randomly(ct)
        return

    # Prefer whatever this unit can see with its own eyes; fall back to
    # the Core's much wider-vision broadcast (see core.py) so a defender
    # can orient toward a threat it hasn't personally spotted yet.
    threat_pos = find_nearest_enemy(ct, DEFENCE_RADIUS_SQ) or read_position(ct, SLOT_THREAT_POS)
    guard_pos = _guard_position(core_pos, threat_pos, PATROL_RADIUS_SQ)

    pos = ct.get_position()
    # Only eligible to build once actually holding the guard spot -- not
    # merely "somewhere within range of the Core" -- otherwise a
    # defender emplaces wherever a threat first got noticed rather than
    # walking to the side that's actually threatened.
    if pos.distance_squared(guard_pos) <= PATROL_RADIUS_SQ and pos.distance_squared(core_pos) <= DEFENCE_RADIUS_SQ:
        turret_count = count_nearby_friendly_turrets(ct, DEFENCE_RADIUS_SQ)
        if turret_count < MAX_DEFENCE_TURRETS_NEAR_CORE:
            facing = None
            if threat_pos is not None:
                # Face whatever we're actually meant to counter.
                facing = pos.direction_to(threat_pos)
            elif turret_count == 0:
                # No threat sighted yet, but hold a baseline garrison
                # rather than waiting for one to show up.
                facing = pos.direction_to(core_pos).opposite()
                if facing == Direction.CENTRE:
                    facing = random.choice(DIRECTIONS)
            if facing is not None:
                try_build_gunner_facing(ct, facing, near=core_pos, max_dist_sq=DEFENCE_RADIUS_SQ)

    # Nothing more urgent this round (or the turret build above already
    # spent the action -- try_build_barrier just no-ops then, same as
    # every other build call here relies on): plug an open gap in the
    # Core's own ring if one exists and we can reach it.
    gap = _find_unsealed_ring_tile(ct, core_pos)
    if gap is not None:
        d = _adjacent_direction(pos, gap)
        if d is not None:
            try_build_barrier(ct, gap)
        else:
            _patrol_near(ct, gap, 1)
            return

    _patrol_near(ct, guard_pos, PATROL_RADIUS_SQ)
