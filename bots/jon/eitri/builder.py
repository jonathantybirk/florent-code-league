"""Executing one Builder's share of the opening plan.

A Builder holds two numbers: which of its lanes it is on, and how far along
that lane it has got.  Everything else it needs is in the shared plan, so the
per-round decision is small: stand on the tile behind the frontier, build the
frontier tile, step onto it, repeat, and finish with the Harvester.

Nothing here searches while a Builder is on its lane -- the lane is the path.
The one BFS is for crossing from a finished lane to the next one.
"""

import debug
import plan as planning
import walk
from fcode import Direction, EntityType

# Rounds of being unable to take the next step before we assume something is
# parked in the way for good and route around it.
PATIENCE = 3


class Crewman:
    """Where this Builder is in its plan. One per unit, alive for the match."""

    __slots__ = ("index", "lane", "tile", "path", "stalled", "traffic",
                 "traffic_rounds")

    def __init__(self):
        self.index = None       # which seat of the crew we are
        self.lane = 0           # how many of our lanes are finished
        self.tile = 0           # how far along the current lane
        self.path = None        # cached route to a lane we have not reached
        self.stalled = 0
        self.traffic = frozenset()
        self.traffic_rounds = 0


def run(player, ct):
    plan = planning.get(ct)
    if plan is None:
        return
    me = tuple(ct.get_position())
    crew = player.crew
    if crew.index is None:
        crew.index = plan.index_of(me, ct.get_current_round())
        if crew.index is None:
            return
    work = plan.work[crew.index]
    while crew.lane < len(work):
        lane_index = work[crew.lane]
        lane = plan.lanes[lane_index]
        if _advance(ct, plan, crew, lane, me):
            return
        plan.completed.add(lane.deposit)
        plan.finished.add(lane_index)
        crew.lane += 1
        crew.tile = 0
        crew.path = None
    _idle(ct, plan, crew, me)


def _advance(ct, plan, crew, lane, me) -> bool:
    """Work this lane for a round. False once the lane is finished."""
    board = plan.board
    while crew.tile < len(lane.tiles):
        tile, facing = lane.tiles[crew.tile]
        if _built(ct, tile):
            crew.tile += 1
            continue
        stand = lane.entry if crew.tile == 0 else lane.tiles[crew.tile - 1][0]
        if me == stand:
            ok = _try(ct, ct.build_conveyor, walk.at(tile), _direction(facing))
            _trace(ct, crew, me, f"conveyor {tile} {'ok' if ok else 'FAILED'}")
            _resolve_build(ct, crew, ok, me, tile)
        else:
            _trace(ct, crew, me, f"-> {stand} to lay {tile}")
            _approach(ct, plan, crew, me, stand)
        return True
    if not _built(ct, lane.deposit):
        if me == lane.stand:
            ok = _try(ct, ct.build_harvester, walk.at(lane.deposit))
            _trace(ct, crew, me, f"harvester {lane.deposit} "
                                 f"{'ok' if ok else 'FAILED'}")
            _resolve_build(ct, crew, ok, me, lane.deposit)
        else:
            _trace(ct, crew, me, f"-> {lane.stand} to dig {lane.deposit}")
            _approach(ct, plan, crew, me, lane.stand)
        return True
    return False


def _built(ct, tile) -> bool:
    """Whether something already stands here.

    Out of vision the engine tells us nothing, and a tile we cannot see is one
    we have not reached yet, so treating it as empty is the reading that keeps
    the Builder walking toward it.
    """
    try:
        return ct.get_tile_building_id(walk.at(tile)) is not None
    except Exception:
        return False


def _approach(ct, plan, crew, me, goal) -> None:
    """Take one step toward `goal`, re-routing only when the walk goes wrong."""
    if crew.path and crew.path[0] == me:
        crew.path.pop(0)
    if not crew.path or crew.path[-1] != goal:
        crew.path = _route(plan, me, goal)
    if crew.path and walk.step(ct, me, crew.path[0]):
        crew.path.pop(0)
        crew.stalled = 0
        return
    blocker = _friendly_at(ct, crew.path[0]) if crew.path else None
    if blocker is not None:
        detour = _route(plan, me, goal, {crew.path[0]})
        if (detour and len(detour) <= len(crew.path) + 1
                and walk.step(ct, me, detour[0])):
            crew.path = detour[1:]
            crew.stalled = 0
            return
    crew.stalled += 1
    if crew.stalled < PATIENCE:
        return
    # Whatever is in the way has been there long enough to be somebody parked
    # rather than somebody passing. Drop the route so the next round searches
    # afresh, and give ground this round so a head-on pair comes unstuck.
    crew.path = None
    crew.stalled = 0
    walk.sidestep(ct, ct.get_current_round() + crew.index)


def _friendly_at(ct, tile):
    """Friendly Builder id occupying `tile`, if visible."""
    try:
        return next(
            unit for unit in ct.get_nearby_units(2)
            if tuple(ct.get_position(unit)) == tile
            and ct.get_team(unit) == ct.get_team()
            and ct.get_entity_type(unit) == EntityType.BUILDER_BOT
        )
    except (Exception, StopIteration):
        return None


def _route(plan, me, goal, extra=frozenset()):
    """A walk to `goal` that keeps off the deposits we mean to dig.

    A route over a deposit is fine until the Harvester goes in and then it is
    a wall, so they are avoided up front. If that leaves no route at all --
    a deposit sitting in a one-tile corridor -- the honest answer is to cross
    it while it is still open.
    """
    board = plan.board
    blocked = (plan.deposits - {goal}) | set(extra)
    return (walk.route(board, me, goal, blocked)
            or walk.route(board, me, goal, plan.completed | set(extra))
            or [])


def _idle(ct, plan, crew, me) -> None:
    """Park off the planned network instead of blocking somebody else's lane."""
    goal = plan.spawns[crew.index]
    transit = set().union(*(tiles for index, tiles in enumerate(plan.transit)
                            if index != crew.index))
    construction = set().union(
        *(tiles for index, tiles in enumerate(plan.construction)
          if index not in plan.finished)
    )
    construction.update(plan.deposits - plan.completed)
    jam = me in transit and _traffic(ct, crew, me)
    if me not in construction and not jam:
        _trace(ct, crew, me, "parked")
        return
    active = construction | (transit if jam else set())
    for spot in plan.board.neighbours(me):
        if spot not in active and walk.step(ct, me, spot):
            _trace(ct, crew, me, f"-> {spot} to clear lane")
            return
    if goal is not None and me != goal:
        _trace(ct, crew, me, f"-> {goal} to clear lane")
        _approach(ct, plan, crew, me, goal)


def _traffic(ct, crew, me) -> bool:
    """Whether the same friendly Builder has been stuck beside us."""
    try:
        nearby = frozenset(
            unit for unit in ct.get_nearby_units(2)
            if tuple(ct.get_position(unit)) != me
            and ct.get_team(unit) == ct.get_team()
            and ct.get_entity_type(unit) == EntityType.BUILDER_BOT
        )
    except Exception:
        return False
    crew.traffic_rounds = (crew.traffic_rounds + 1
                           if nearby & crew.traffic else bool(nearby))
    crew.traffic = nearby
    return crew.traffic_rounds >= PATIENCE


def _trace(ct, crew, me, what) -> None:
    if debug.ON:
        debug.log(f"r{ct.get_current_round():>4} seat{crew.index} "
                  f"at{me} lane{crew.lane} tile{crew.tile}  {what}")


def _direction(facing):
    return walk.STEP_DIR[facing]


def _resolve_build(ct, crew, succeeded, here, target) -> None:
    """Yield a blocked build stand instead of retrying there forever."""
    if succeeded:
        crew.stalled = 0
        return
    direction = walk.STEP_DIR.get((target[0] - here[0], target[1] - here[1]))
    if direction is None or ct.can_move(direction):  # empty target: wait for resources
        crew.stalled = 0
        return
    crew.stalled += 1
    if crew.stalled >= PATIENCE:
        crew.stalled = 0
        crew.path = None
        walk.sidestep(ct, ct.get_current_round() + crew.index)


def _try(ct, action, *args) -> bool:
    try:
        action(*args)
        return True
    except Exception:
        return False
