"""The opening plan, computed once per match and shared by every unit.

Modules are imported once per team, so the first unit to ask pays for the plan
and every unit after it -- including Builders spawned hundreds of rounds later
-- reads the same object.  That is what keeps this inside the 10 ms per-unit
budget: the work is two floods and a gradient walk per deposit, paid once.

The cache is keyed by team rather than being a bare global because a mirror
match can put both sides in one interpreter, and a plan drawn for one seat is
exactly wrong for the other.  It is keyed by team and *not* by Core anchor for
a reason worth stating: a Builder finds the anchor by looking at the Core, its
vision radius^2 is 20, and by round twenty-five it is halfway down a lane and
cannot see home.  Asking again every round would hand it a plan for the first
part of the match and nothing afterwards -- which is exactly the shape of the
bug that had three of four Builders frozen from round twenty-four.
"""

import atlas
import crew
import network

_CACHE = {}


class Plan:
    __slots__ = ("board", "lanes", "work", "spawns", "deposits", "completed",
                 "finished", "construction")

    def __init__(self, board, lanes, work, spawns):
        self.board = board
        self.lanes = lanes
        self.work = work
        self.spawns = spawns
        # Every tile a Harvester is planned for. Ore is walkable ground
        # right up until one is built on it, and a route laid across a
        # deposit stops dead the moment it is dug -- so routes avoid
        # them from the start rather than discovering it later.
        self.deposits = frozenset(lane.deposit for lane in lanes)
        self.completed = set()
        self.finished = set()
        self.construction = tuple(
            frozenset([lane.entry] + [tile for tile, _ in lane.tiles])
            for lane in lanes
        )

    def index_of(self, tile, round_):
        """Which Builder is standing on `tile`, by the seat it was spawned into.

        Identifying a Builder by where it woke up rather than by when means the
        crew survives a delayed spawn: if the ring tile for seat 2 is blocked
        for a round, seat 2 is still seat 2 when it finally appears.  The round
        is only a fallback for a Builder the Core had to put down elsewhere.
        """
        for index, spot in enumerate(self.spawns):
            if spot == tile:
                return index
        return round_ if round_ < len(self.work) else None


def get(ct):
    """The plan for this unit's team, or None on a map outside the atlas."""
    team = ct.get_team()
    if team in _CACHE:
        return _CACHE[team]
    home = atlas.home_anchor(ct)
    if home is None:
        return None                       # out of sight of home; ask again
    built = _build(ct, home)
    _CACHE[team] = built                  # a miss is final: the map is the map
    return built


def _build(ct, home):
    board = atlas.identify(ct, home)
    if board is None:
        return None
    picks, field = network.survey(board)
    best = None
    for order in (picks, picks[::-1]):
        lanes = network.lay(board, order, field)
        work, spawns, done = crew.assign(board, lanes)
        worth = crew.value(lanes, done)
        if best is None or worth > best[0]:
            best = (worth, lanes, work, spawns)
    _, lanes, work, spawns = best
    return Plan(board, lanes, work, spawns)
