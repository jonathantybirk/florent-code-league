from fcode import Controller, Direction, EntityType, GameConstants, Position

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
SPLITTER_OUTPUTS = 3


def _in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


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
    round-robins between 3 outputs and exposes no way to read which one is
    next, so each of its 3 valid outputs is treated as equally likely: 1/3.
    Harvesters aren't included: get_stored_resource only supports Conveyors
    and Splitters, so there's no way to even see whether one is holding
    titanium to estimate.
    """
    neighbor = pos.add(from_dir)
    if not _in_bounds(ct, neighbor):
        return None
    bid = ct.get_tile_building_id(neighbor)
    if bid is None:
        return None

    etype = ct.get_entity_type(bid)
    if etype not in (EntityType.CONVEYOR, EntityType.SPLITTER):
        return None

    facing = ct.get_direction(bid)
    out_dir = from_dir.opposite()  # direction the neighbour must output in to reach pos
    if etype == EntityType.CONVEYOR:
        return (neighbor, etype, 1.0) if facing == out_dir else None
    if out_dir == facing.opposite():  # the back is input-only, not an output
        return None
    return neighbor, etype, 1 / SPLITTER_OUTPUTS


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
    guaranteed passive trickle, averaged over the window."""
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
