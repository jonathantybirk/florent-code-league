"""One BFS for every planner, ported from steward_reinforced (555c3ce).

The steward Builder once had four path searches -- movement, target choice,
distance-to-goal-set, belt laying -- and they disagreed: a Launcher hop was a
one-round edge in one and absent in another, so a Builder chose its errand by
walking distance and then travelled by throwing. A goal that is far when
choosing and near when moving keeps winning and losing; on r03 builder 11 was
ferried three times in twelve rounds, each ferry correct for the goal it held
that instant.

The cure was one search (`travel`) that everything else is a thin view over.
This module is that search with the steward-specific state (`p.walls`,
`p.threat`, ...) pulled out into a `Terrain` value, so any bot can use it.

Vocabulary
----------
tile        a ``(x, y)`` pair; ``(0, 0)`` is the top-left of the map.
walkable    inside the map and not in `Terrain.blocked`.
exact goal  the route must end *on* the target tile.
adjacent    the route may end on any of the eight tiles around the target
            (what you want for "go build on / mine that tile").
hop         an edge a friendly Launcher provides: from any tile in its pickup
            ring to any tile it can throw to. Costs one step like a walk, and
            is reconstructed as an ordinary parent link -- the caller notices
            a hop because consecutive path tiles are not adjacent.

Safety is a property of the graph, not a price. Firing lines and enemy
Launcher radii are simply absent from the graph (``Terrain.threat``,
``Terrain.launcher_hazards``), because two notions of safety -- "forbidden"
in one planner and "expensive" in another -- is a livelock waiting to happen:
builder 66 oscillated between two tiles from round 43 to the end of a game
doing exactly that. `allow_fire=True` re-admits threat tiles for the one
caller that has to decide whether a walk through fire is survivable.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

Tile = tuple[int, int]

# Cardinal neighbours, the only moves a unit can actually make.
D4_DELTAS: tuple[Tile, ...] = ((0, -1), (1, 0), (0, 1), (-1, 0))
# All eight neighbours, for "adjacent to the target" goal sets.
D8_DELTAS: tuple[Tile, ...] = ((-1, -1), (0, -1), (1, -1), (1, 0),
                               (1, 1), (0, 1), (-1, 1), (-1, 0))

# Engine geometry of a Launcher (fcode 2.x): it picks up from the eight tiles
# around itself and throws up to distance² 26.
LAUNCH_PICKUP_SQ = 2
LAUNCH_RANGE_SQ = 26


@dataclass
class Terrain:
    """Everything the search needs to know about the board this round.

    Build one per turn from whatever the bot already tracks. All tile sets are
    plain ``set[Tile]``; the search never mutates them.

    blocked           tiles no unit may stand on: walls, solid buildings,
                      other bots, ore you must not trample -- whatever the
                      bot considers impassable. Union them before passing.
    threat            tiles inside an enemy turret's firing line. Forbidden
                      unless ``allow_fire``.
    launcher_hazards  tiles an enemy Launcher could pick us up from. Always
                      forbidden: being thrown is not damage to weigh against a
                      shorter route, it is the loss of position entirely.
    friendly_launchers  positions of our own Launchers, for hops.
    landing_blocked   tiles a friendly throw may not land on (typically
                      walls | solids; the engine refuses to land on those).
                      Defaults to ``blocked`` when not given.
    """

    width: int
    height: int
    blocked: set[Tile] = field(default_factory=set)
    threat: set[Tile] = field(default_factory=set)
    launcher_hazards: set[Tile] = field(default_factory=set)
    friendly_launchers: Iterable[Tile] = ()
    landing_blocked: set[Tile] | None = None

    def inside(self, tile: Tile) -> bool:
        return 0 <= tile[0] < self.width and 0 <= tile[1] < self.height

    def adjacent(self, target: Tile) -> set[Tile]:
        """The eight on-map tiles around `target`."""
        return {(target[0] + dx, target[1] + dy) for dx, dy in D8_DELTAS
                if self.inside((target[0] + dx, target[1] + dy))}

    def no_go(self, source: Tile | None = None) -> set[Tile]:
        """Ground no unit may walk on, the single answer for every planner.

        `source` is exempt: standing somewhere forbidden has to leave a legal
        move out of it, or the unit is stuck by its own rules.
        """
        out = self.blocked | self.threat | self.launcher_hazards
        if source is not None:
            out.discard(source)
        return out

    def pickup_ring(self, launcher: Tile) -> set[Tile]:
        """Tiles a friendly Launcher at `launcher` can pick a unit up from."""
        return {(launcher[0] + dx, launcher[1] + dy)
                for dx in range(-1, 2) for dy in range(-1, 2)
                if (dx or dy) and dx * dx + dy * dy <= LAUNCH_PICKUP_SQ
                and self.inside((launcher[0] + dx, launcher[1] + dy))}

    def throw_landings(self, launcher: Tile) -> list[Tile]:
        """Tiles a friendly Launcher could put us on.

        Deliberately generous: legality is the Launcher's business at the
        moment of the throw, and a route that assumes a landing which turns
        out illegal simply re-plans next round. Being pessimistic here is what
        would keep the hop out of routes it should be in. Threat tiles are
        still excluded -- landing in a firing line is never a plan.
        """
        forbidden = (self.blocked if self.landing_blocked is None
                     else self.landing_blocked)
        span = int(LAUNCH_RANGE_SQ ** 0.5)
        out = []
        for dx in range(-span, span + 1):
            for dy in range(-span, span + 1):
                if dx * dx + dy * dy > LAUNCH_RANGE_SQ:
                    continue
                tile = (launcher[0] + dx, launcher[1] + dy)
                if (self.inside(tile) and tile not in forbidden
                        and tile not in self.threat):
                    out.append(tile)
        return out


def travel(terrain: Terrain, source: Tile, goals: set[Tile] | None = None,
           hops: bool = True, allow_fire: bool = False,
           extra_blocked: Iterable[Tile] = ()):
    """The single BFS. Returns ``(dist, came_from)``.

    ``dist`` maps every reached tile to its step count from `source`;
    ``came_from`` maps it to its parent (``None`` for the source). A hop is an
    ordinary parent link, so a route through a Launcher reconstructs exactly
    like a walk.

    Stops as soon as any tile in `goals` is dequeued, so with goals given the
    returned maps are partial -- use :func:`distance_map` for a full flood.

    hops          add friendly-Launcher edges. ``False`` for callers that
                  genuinely mean walking: pricing a throw against a walk, or
                  planning conveyor tiles.
    allow_fire    re-admit ``terrain.threat`` tiles.
    extra_blocked temporary obstacles, e.g. "what if we built a turret here".
    """
    blocked = terrain.no_go(source) | set(extra_blocked)
    if allow_fire:
        blocked -= terrain.threat
    blocked.discard(source)

    pads: dict[Tile, Tile] = {}
    if hops:
        pads = {tile: pad
                for pad in terrain.friendly_launchers
                for tile in terrain.pickup_ring(pad)}

    goal_set = set(goals) if goals else None
    dist: dict[Tile, int] = {source: 0}
    prev: dict[Tile, Tile | None] = {source: None}
    queue = deque([source])
    while queue:
        cur = queue.popleft()
        if goal_set and cur in goal_set:
            break
        neighbours = [(cur[0] + dx, cur[1] + dy) for dx, dy in D4_DELTAS]
        pad = pads.get(cur)
        if pad is not None:
            neighbours.extend(terrain.throw_landings(pad))
        for nxt in neighbours:
            if nxt in dist or not terrain.inside(nxt) or nxt in blocked:
                continue
            dist[nxt] = dist[cur] + 1
            prev[nxt] = cur
            queue.append(nxt)
    return dist, prev


def path(terrain: Terrain, source: Tile, target: Tile, exact: bool = True,
         hops: bool = True, allow_fire: bool = False,
         extra_blocked: Iterable[Tile] = ()) -> list[Tile] | None:
    """Full route from `source` to `target`, inclusive of both, or ``None``.

    ``exact=False`` accepts any of the eight tiles around `target` as the
    destination -- the form to use when the target is something you will
    build on or mine, and therefore cannot stand on. Returns ``[source]``
    when already there.
    """
    goals = {target} if exact else terrain.adjacent(target)
    if source in goals:
        return [source]
    dist, prev = travel(terrain, source, goals=goals, hops=hops,
                        allow_fire=allow_fire, extra_blocked=extra_blocked)
    reached = [(dist[g], g) for g in goals if g in dist]
    if not reached:
        return None
    found: Tile | None = min(reached)[1]
    out = []
    while found is not None:
        out.append(found)
        found = prev[found]
    out.reverse()
    return out


def first_step(terrain: Terrain, source: Tile, target: Tile,
               exact: bool = True, hops: bool = True,
               allow_fire: bool = False) -> Tile | None:
    """The next tile to move to, or ``None`` when there is no route.

    If the returned tile is not cardinally adjacent to `source`, the route
    starts with a hop: ask the Launcher whose pickup ring covers `source` to
    throw you there instead of calling ``move``.
    """
    route = path(terrain, source, target, exact, hops, allow_fire)
    if route is None or len(route) < 2:
        return None
    return route[1]


def safe_path(terrain: Terrain, source: Tile, target: Tile,
              exact: bool = True, hops: bool = True,
              survives=None) -> tuple[list[Tile] | None, bool]:
    """A clean route, else a survivable route through fire, else ``None``.

    Returns ``(route, blocked_by_fire)``. ``blocked_by_fire`` is ``True``
    only when a route exists through fire but was refused -- the signal a
    caller uses to retreat or build a Launcher over the top.

    `survives` is ``callable(route_tail) -> bool``, the bot's own judgement
    of whether walking the given tiles (excluding `source`) leaves it alive;
    when ``None``, routes through fire are never taken.

    The old shape -- plan short, price it, detour if it kills us, otherwise
    walk it anyway -- was the source of the oscillation described in the
    module docstring. Preferring safety and enforcing safety are not the same
    rule, and running both at once is a livelock. So: a clean route is taken.
    Failing that, a route through fire only if genuinely survivable, because
    sometimes the errand still has to happen and the alternative is standing
    still. Failing that, refuse.
    """
    route = path(terrain, source, target, exact, hops)
    if route is not None:
        return route, False
    through_fire = path(terrain, source, target, exact, hops, allow_fire=True)
    if through_fire is None:
        return None, False
    if survives is not None and survives(through_fire[1:]):
        return through_fire, False
    return None, True


def distance(terrain: Terrain, source: Tile, goals: set[Tile],
             hops: bool = True) -> int | None:
    """Steps to the nearest of `goals`, or ``None``. Same search as movement."""
    if source in goals:
        return 0
    dist, _ = travel(terrain, source, goals=goals, hops=hops)
    reached = [dist[g] for g in goals if g in dist]
    return min(reached) if reached else None


def distance_map(terrain: Terrain, source: Tile,
                 hops: bool = True) -> dict[Tile, int]:
    """Every reachable distance, on the same terms movement will use."""
    return travel(terrain, source, hops=hops)[0]


def keeps_route_open(terrain: Terrain, spot: Tile, source: Tile,
                     target: Tile, exact: bool = True,
                     baseline: set[Tile] | None | object = ...) -> bool:
    """True when `spot` can be built on without cutting our own way forward.

    Turrets are solid. Dropping one on the single corridor to the enemy Core
    walls the attacker out of the game it was built to fight. Building onto
    the goal itself (or where we stand) is exempt.

    Pass `baseline` -- ``set(path(...))`` computed once, or ``None`` if there
    is no route -- when testing many sites against the same route. A site the
    existing route does not use cannot close it, so only sites *on* the route
    need the second search. This is exact, not a heuristic, and is what turned
    a 13.5 ms Builder turn on longship into one that fits the 10 ms limit.
    """
    if spot == target or spot == source:
        return True
    if baseline is ...:
        route = path(terrain, source, target, exact)
        baseline = None if route is None else set(route)
    if baseline is None:
        # Already no route; a turret cannot make that worse, and refusing here
        # would disable the breaker in exactly the case it exists for.
        return True
    if spot not in baseline:
        return True
    return path(terrain, source, target, exact,
                extra_blocked=(spot,)) is not None
