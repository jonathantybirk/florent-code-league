from fcode import Controller, Direction, EntityType, GameConstants, Position

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
RECEIVER_TYPES = (EntityType.CONVEYOR, EntityType.SPLITTER, EntityType.CORE)


def _in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


def _is_receiver(ct: Controller, pos: Position, direction: Direction) -> bool:
    """Whether the tile in direction from pos is a same-team Conveyor,
    Splitter, or Core -- something that can actually hold a delivered
    stack, as opposed to empty ground, a wall, or a building (Barrier,
    turret, ...) with nowhere to put titanium."""
    target = pos.add(direction)
    if not _in_bounds(ct, target):
        return False
    bid = ct.get_tile_building_id(target)
    if bid is None or ct.get_team(bid) != ct.get_team():
        return False
    return ct.get_entity_type(bid) in RECEIVER_TYPES


def _core_footprint(ct: Controller) -> list[Position]:
    """All tiles of this Core's 2x2 footprint. dist_sq=2 covers the whole
    footprint from any tile within it, since the farthest two tiles of a
    2x2 block are a diagonal step (distance_sq 2) apart."""
    core_id = ct.get_id()
    return [pos for pos in ct.get_nearby_tiles(dist_sq=2) if ct.get_tile_building_id(pos) == core_id]


def _feeder_at(ct: Controller, pos: Position, from_dir: Direction) -> tuple[Position, EntityType, float] | None:
    """The neighbour in from_dir, if it's a Conveyor or Splitter that feeds
    pos, with the probability a stack it holds actually goes to pos next
    dispatch.

    A Conveyor has one fixed output, so that probability is 1.0. A Splitter
    rotates only among its outputs that currently lead to a receiver (see
    _is_receiver) and exposes no way to read which one of those is next, so
    each is treated as equally likely: 1 / (however many it currently has).
    Verified against the real engine: a Splitter with only one receiving
    output got 222 of 222 dispatches over an 887-round sample, not the ~74
    a blind rotation through a fixed 3 would produce -- an output with
    nothing to receive isn't in the rotation at all. Harvesters aren't
    included: get_stored_resource only supports Conveyors and Splitters,
    so there's no way to even see whether one is holding titanium to
    estimate.
    """
    neighbor = pos.add(from_dir)
    if not _in_bounds(ct, neighbor):
        return None
    bid = ct.get_tile_building_id(neighbor)
    if bid is None:
        return None
    if ct.get_team(bid) != ct.get_team():
        return None

    etype = ct.get_entity_type(bid)
    if etype not in (EntityType.CONVEYOR, EntityType.SPLITTER):
        return None

    facing = ct.get_direction(bid)
    out_dir = from_dir.opposite()  # direction the neighbour must output in to reach pos
    if etype == EntityType.CONVEYOR:
        return (neighbor, etype, 1.0) if facing == out_dir else None
    back = facing.opposite()
    if out_dir == back:  # the back is input-only, not an output
        return None
    live_outputs = [d for d in CARDINALS if d != back and _is_receiver(ct, neighbor, d)]
    # pos itself is a receiver reached via out_dir, so live_outputs is
    # never empty here.
    return neighbor, etype, 1 / len(live_outputs)


def _feeders(ct: Controller, pos: Position, etype: EntityType) -> list[tuple[Position, EntityType, float]]:
    """Everything currently feeding pos. A Splitter only ever accepts input
    from the single tile behind it; anything else (a Conveyor, or the Core
    itself) can be fed from any side."""
    if etype == EntityType.SPLITTER:
        directions = (ct.get_direction(ct.get_tile_building_id(pos)).opposite(),)
    else:
        directions = CARDINALS
    return [feeder for d in directions if (feeder := _feeder_at(ct, pos, d)) is not None]


def _titanium_via(ct: Controller, pos: Position, etype: EntityType, weight: float, rounds_left: int) -> float:
    """Titanium expected to reach the Core within rounds_left rounds via pos
    and whatever feeds it, weighted by the probability (weight) that a
    stack at pos actually completes its route to the Core.

    Bounded recursion instead of an explicit worklist: rounds_left shrinks
    by one on every hop, so this can't run away even on a pathological map.
    It also can't double-count -- each Conveyor/Splitter has exactly one
    output direction, so it can only ever be discovered as a feeder of the
    one specific tile it points at, never more than once.
    """
    holding = ct.get_stored_resource(ct.get_tile_building_id(pos)) is not None
    total = weight * GameConstants.STACK_SIZE if holding else 0.0
    if rounds_left > 1:
        for neighbor, n_etype, hop_weight in _feeders(ct, pos, etype):
            total += _titanium_via(ct, neighbor, n_etype, weight * hop_weight, rounds_left - 1)
    return total


def expected_titanium_flow(ct: Controller) -> float:
    """Average titanium expected to flow into the Core per round, over the
    next PASSIVE_TITANIUM_INTERVAL rounds: titanium already in transit
    (weighted by delivery probability) within that window, plus the
    guaranteed passive trickle, averaged over the window.

    Must be called on the Core's own turn -- _core_footprint identifies the
    footprint by matching ct.get_id(), which is this *calling unit's* id.
    Called from anything else, that match is never found, the footprint
    comes back empty, and this returns a plausible-looking passive-only
    number instead of failing loudly.
    """
    if ct.get_entity_type() != EntityType.CORE:
        raise ValueError("expected_titanium_flow must be called from the Core's own turn")
    window = GameConstants.PASSIVE_TITANIUM_INTERVAL
    pending = sum(
        _titanium_via(ct, neighbor, etype, weight, window)
        for tile in _core_footprint(ct)
        for neighbor, etype, weight in _feeders(ct, tile, EntityType.CORE)
    )
    return (pending + GameConstants.PASSIVE_TITANIUM_AMOUNT) / window


class Player:
    def _expected_income(self, ct: Controller) -> float:
        return expected_titanium_flow(ct)
