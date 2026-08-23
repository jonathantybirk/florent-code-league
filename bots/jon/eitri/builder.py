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
from fcode import Direction

# Rounds of being unable to take the next step before we assume something is
# parked in the way for good and route around it.
PATIENCE = 3


class Crewman:
    """Where this Builder is in its plan. One per unit, alive for the match."""

    __slots__ = ("index", "lane", "tile", "path", "stalled")

    def __init__(self):
        self.index = None       # which seat of the crew we are
        self.lane = 0           # how many of our lanes are finished
        self.tile = 0           # how far along the current lane
        self.path = None        # cached route to a lane we have not reached
        self.stalled = 0


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
        lane = plan.lanes[work[crew.lane]]
        if _advance(ct, plan, crew, lane, me):
            return
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
        else:
            _trace(ct, crew, me, f"-> {stand} to lay {tile}")
            _approach(ct, plan, crew, me, stand)
        return True
    if not _built(ct, lane.deposit):
        if me == lane.stand:
            ok = _try(ct, ct.build_harvester, walk.at(lane.deposit))
            _trace(ct, crew, me, f"harvester {lane.deposit} "
                                 f"{'ok' if ok else 'FAILED'}")
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
    crew.stalled += 1
    if crew.stalled < PATIENCE:
        return
    # Whatever is in the way has been there long enough to be somebody parked
    # rather than somebody passing. Drop the route so the next round searches
    # afresh, and give ground this round so a head-on pair comes unstuck.
    crew.path = None
    crew.stalled = 0
    walk.sidestep(ct, ct.get_current_round() + crew.index)


def _route(plan, me, goal):
    """A walk to `goal` that keeps off the deposits we mean to dig.

    A route over a deposit is fine until the Harvester goes in and then it is
    a wall, so they are avoided up front. If that leaves no route at all --
    a deposit sitting in a one-tile corridor -- the honest answer is to cross
    it while it is still open.
    """
    board = plan.board
    blocked = plan.deposits - {goal}
    return (walk.route(board, me, goal, blocked)
            or walk.route(board, me, goal)
            or [])


def _idle(ct, plan, crew, me) -> None:
    """Nothing left in this Builder's plan."""
    _trace(ct, crew, me, "idle")


def _trace(ct, crew, me, what) -> None:
    if debug.ON:
        debug.log(f"r{ct.get_current_round():>4} seat{crew.index} "
                  f"at{me} lane{crew.lane} tile{crew.tile}  {what}")


def _direction(facing):
    return walk.STEP_DIR[facing]


def _try(ct, action, *args) -> bool:
    try:
        action(*args)
        return True
    except Exception:
        return False
