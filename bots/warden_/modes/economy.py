"""ECONOMY mode: harvest ore and route it toward the Core -- joining the
nearest existing conveyor if one's closer than the Core itself.

Tracked by state.route_harvester / route_target / route_pending_pos /
route_pending_dir (see state.py), never more than one active route at
once:

  1. Seek ore and build a harvester -- no belt-laying. Once built, pick
     route_target: the nearest visible tile carrying one of our own
     Conveyors if it's closer than the Core, else the Core itself (see
     _find_nearest_friendly_conveyor). Every harvester routing all the
     way back to the Core on its own duplicates distance a later,
     nearer harvester could instead have covered by joining the trunk
     the first one already laid -- the network should grow outward as a
     shared trunk, not as many separate lines to the same destination.
  2. Walk from the harvester toward route_target one tile per round,
     axis-priority (horizontal gap first, then vertical -- see
     _pick_axis_direction), falling back to whichever other cardinal is
     open when both preferred axes are blocked right here.
  3. Every round after a successful move, the *previous* tile -- the one
     just vacated -- gets a conveyor built on it facing the direction
     that was actually just taken. This is one round late by
     construction (a Builder Bot can never build on its own tile, and
     build/move are mutually exclusive within a round -- see
     docs/official/docs/game-rules-builder-bot.txt), but it is never
     *wrong*: the facing always matches a move that has already actually
     succeeded, so the chain can't help but connect, whatever path the
     walk actually took.
  4. Whenever that vacated tile turns out to be itself orthogonally
     adjacent to route_target -- the Core, or specifically the existing
     conveyor tile chosen in step 1 -- it's built facing that instead of
     the direction actually taken, and the route ends there -- see
     _connection_facing. A conveyor accepts input from any adjacent
     tile regardless of that neighbor's own facing, so joining an
     existing tile this way feeds it exactly like a fresh Harvester
     would; whatever route originally connected it onward keeps
     carrying both flows from here. The Core's footprint (and any
     already-built conveyor) blocks the walk from ever stepping onto
     it, so this is the only way the last link ever gets built: it must
     be a tile the builder has already left (own-tile restriction),
     which step 3 guarantees for every tile but the one currently stood
     on -- so the walk takes one further, otherwise pointless step off
     a connectable tile purely to make it eligible.

Bug history, both caught by a chain-walking assertion in
tests/test_warden_economy.py rather than "titanium collected > 0" after a
full match (which is what let all three ship undetected the first time):

  - Facing computed from the direction used to *arrive* at a tile broke
    at turns: the segment's own outgoing direction can differ from its
    incoming one, and only the outgoing one is correct.
  - The fix for that -- computing facing from pure axis-priority geometry
    at the tile *before* actually moving there -- broke again on any map
    with real obstacles (walls/water): a route that has to detour around
    something no longer matches the geometry-only prediction, so a
    segment could be built facing a direction the walk was never
    actually going to take.
  - The fix for *that* -- build only ever describes a move that already
    happened, step 3 above -- left the tile the builder is currently
    standing on permanently unbuilt (it can never be its own build
    target), which breaks specifically at the Core end: a naive "look
    one tile ahead of wherever I'm standing and build the last segment
    there" check (this file's previous _final_segment) uses the current,
    always-unbuilt tile as its anchor, leaving a gap between it and
    whatever was built behind it. Step 4's fix is to never anchor a
    build on the current tile at all -- only ever on one already vacated.

This is the game's own "Logistics" tutorial's approach
(_pick_direction / _lay_conveyor_toward_core) for the walk, adapted for
the reasons above rather than ported directly.

Covered by tests/test_warden_economy.py, which simulates this against
tests/fake_controller.py's in-memory grid (including a walled detour) and
asserts the resulting chain is actually walkable end to end, tile by
tile, via each conveyor's own facing. Run that after touching this file,
before trusting a full fcode match to tell you whether it still works.
"""

from __future__ import annotations

from fcode import Controller, Direction, EntityType, Position

from constants import ROUTE_STUCK_THRESHOLD, SLOT_ORE_SHARE, STUCK_THRESHOLD
from state import BuilderState
from toolbox import (
    CARDINALS,
    explore_randomly,
    find_nearest_ore,
    in_bounds,
    read_position,
    share_ore,
    try_build_harvester_on_ore,
    try_move_toward,
)


def run(ct: Controller, state: BuilderState) -> None:
    if ct.get_action_cooldown() == 0:
        if state.route_harvester is None:
            built = try_build_harvester_on_ore(ct)
            if built is not None:
                state.ore_target = None
                state.route_harvester = built
                state.stuck.stuck_rounds = 0
                nearest_conveyor = _find_nearest_friendly_conveyor(ct)
                pos_now = ct.get_position()
                if (
                    nearest_conveyor is not None
                    and state.core_pos is not None
                    and pos_now.distance_squared(nearest_conveyor) < pos_now.distance_squared(state.core_pos)
                ):
                    state.route_target = nearest_conveyor
                else:
                    state.route_target = state.core_pos

    pos = ct.get_position()
    state.stuck.update(pos)

    if state.route_harvester is not None:
        state.econ_idle_rounds = 0
        _lay_route(ct, state, pos)
        share_ore(ct, SLOT_ORE_SHARE)
        return

    if state.ore_target is None:
        state.ore_target = find_nearest_ore(ct) or read_position(ct, SLOT_ORE_SHARE)

    if state.ore_target is not None and state.stuck.stuck_rounds < STUCK_THRESHOLD:
        state.econ_idle_rounds = 0
        try_move_toward(ct, state.ore_target)
    else:
        state.ore_target = None
        # Genuinely nothing to do this round -- no route, no target, not
        # mid-walk toward one. See policy.maybe_reassign()'s
        # ECON_IDLE_ROUNDS_BEFORE_SCOUT: enough of these in a row and
        # this builder gives up on Economy and starts Scouting instead.
        state.econ_idle_rounds += 1
        explore_randomly(ct)

    share_ore(ct, SLOT_ORE_SHARE)


def _find_nearest_friendly_conveyor(ct: Controller) -> Position | None:
    """Nearest currently-visible tile carrying one of our own Conveyors,
    or None. Checked once, right when a route starts (see run()), so a
    new harvester can join whichever is closer -- the existing network
    or the Core -- instead of every harvester paying the full distance
    back to the Core on its own; see this module's docstring.
    """
    my_team = ct.get_team()
    pos = ct.get_position()
    best = None
    best_dist = None
    for tile in ct.get_nearby_tiles():
        bid = ct.get_tile_building_id(tile)
        if bid is None or ct.get_team(bid) != my_team:
            continue
        if ct.get_entity_type(bid) != EntityType.CONVEYOR:
            continue
        d = pos.distance_squared(tile)
        if best_dist is None or d < best_dist:
            best, best_dist = tile, d
    return best


def _connection_facing(ct: Controller, pos: Position, target: Position) -> Direction | None:
    """The cardinal direction from pos to an orthogonally adjacent tile
    that completes the route: our own Core (any corner of its footprint,
    reached from any angle), or specifically target itself when target
    is an existing Conveyor tile chosen at route start. None if pos is
    adjacent to neither.

    Checking the *specific* target tile for the Conveyor case (not "any
    adjacent friendly Conveyor") matters: every tile this route has
    already built is itself a friendly Conveyor cardinally adjacent to
    the next one in line, and treating any of those as a valid
    connection would end the route against its own just-built segment
    instead of the intended target, one tile after leaving the
    Harvester.

    Used only against a tile the builder has already vacated (see
    _lay_route and this module's docstring) -- never against wherever
    it's currently standing, which is the mistake this replaced.
    """
    my_team = ct.get_team()
    for d in CARDINALS:
        neighbor = pos.add(d)
        if not in_bounds(ct, neighbor):
            continue
        bid = ct.get_tile_building_id(neighbor)
        if bid is None or ct.get_team(bid) != my_team:
            continue
        etype = ct.get_entity_type(bid)
        if etype == EntityType.CORE:
            return d
        if etype == EntityType.CONVEYOR and neighbor == target:
            return d
    return None


def _pick_axis_direction(ct: Controller, pos: Position, target: Position) -> Direction | None:
    """Horizontal gap first, then vertical, filtered to a currently-legal
    move. Falls back to whichever other cardinal is open when both
    preferred axes are blocked right here (a wall, water, or another
    building sitting on the direct line) rather than stalling outright --
    a single-tile-wide obstacle gets stepped around; the next round
    recomputes the preferred axes fresh from wherever that landed.

    Facing for the conveyor built behind this move is decided later, from
    the move actually taken -- never predicted from this function's
    choice in advance. See this module's docstring for why.
    """
    dx = target.x - pos.x
    dy = target.y - pos.y
    primary = []
    if dx != 0:
        primary.append(Direction.EAST if dx > 0 else Direction.WEST)
    if dy != 0:
        primary.append(Direction.SOUTH if dy > 0 else Direction.NORTH)
    for d in primary:
        if ct.can_move(d):
            return d
    for d in CARDINALS:
        if d not in primary and ct.can_move(d):
            return d
    return None


def _abandon(state: BuilderState) -> None:
    state.route_harvester = None
    state.route_target = None
    state.route_pending_pos = None
    state.route_pending_dir = None


def _lay_route(ct: Controller, state: BuilderState, pos: Position) -> None:
    assert state.route_harvester is not None
    assert state.route_target is not None

    # A tile vacated last round is owed its conveyor now. Normally that
    # means facing the direction actually taken to leave it -- but if
    # this tile completes the connection (Core-adjacent, or specifically
    # adjacent to the existing Conveyor tile chosen as route_target),
    # face that instead and finish the route: this is the only tile that
    # can ever be the last link (see this module's docstring), since
    # it's the one already-vacated tile that's close enough to connect
    # at all.
    if state.route_pending_pos is not None:
        connect_dir = _connection_facing(ct, state.route_pending_pos, state.route_target)
        facing = connect_dir if connect_dir is not None else state.route_pending_dir
        built = False
        if ct.can_build_conveyor(state.route_pending_pos, facing):
            ct.build_conveyor(state.route_pending_pos, facing)
            built = True
        state.route_pending_pos = None
        state.route_pending_dir = None
        state.stuck.stuck_rounds = 0
        if built and connect_dir is not None:
            _abandon(state)
        return

    if state.stuck.stuck_rounds >= ROUTE_STUCK_THRESHOLD:
        _abandon(state)
        return

    direction = _pick_axis_direction(ct, pos, state.route_target)
    if direction is None:
        return  # blocked on every cardinal; let stuck-counting handle giving up

    if ct.can_move(direction):
        ct.move(direction)
        state.route_pending_pos = pos
        state.route_pending_dir = direction
        state.stuck.stuck_rounds = 0
