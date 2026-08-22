from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from fcode import Controller, Direction, EntityType, GameConstants

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
RECEIVER_TYPES = (EntityType.CONVEYOR, EntityType.SPLITTER, EntityType.CORE)

# fcode.Direction.delta()/.opposite() rebuild a dict literal on every call
# (see fcode/_types.py) rather than a cached lookup -- cheap in isolation,
# but _build_paths calls these thousands of times on a full-map scan.
# Precomputing once here turns each call into an O(1) dict lookup.
_DELTA = {d: d.delta() for d in CARDINALS}
_OPPOSITE = {d: d.opposite() for d in CARDINALS}


tiles = (type for type in (EntityType.CONVEYOR, EntityType.SPLITTER, EntityType.CORE))

# EMA smoothing weight for Path.actual_flow: how much a single round's
# observation moves the running estimate. Lower = smoother but slower to
# reflect a harvester actually breaking; tune as needed.
_FLOW_EMA_ALPHA = 0.2


# eq=False: Harvester.entry_path and Path.harvesters reference each other
# (a harvester is appended to every Path node on its route, including its
# own entry_path), which is a genuine reference cycle. The dataclass-default
# eq compares field tuples with no cycle guard, so `path_a == path_b` would
# recurse forever; identity comparison (the default without eq) is also the
# only sensible notion of equality for graph nodes like these anyway.
@dataclass(eq=False)
class Path:
    """A single conveyor/splitter tile on a route to the core. `next` chains
    toward the core (None once the next hop IS the core). `harvesters` is
    every harvester whose delivery passes through this exact tile, so a tile
    on a shared trunk accumulates all of its upstream harvesters -- this is
    what lets a tile the core can currently see be checked against how much
    flow should be crossing it."""

    position: tuple[int, int]
    next: Path | None = None
    harvesters: list[Harvester] = field(default_factory=list)

    # Observed-flow state, carried over across rebuilds by _build_paths so
    # history survives the network being re-scanned each round. Populated by
    # _observe_flow; do not read _last_seen_id directly.
    actual_flow: float = 0.0
    _last_seen_id: int | None = field(default=None, repr=False)

    @property
    def expected_flow(self) -> float:
        """Expected titanium/round through this tile, assuming every
        connected harvester delivers its average rate: one
        PASSIVE_TITANIUM_AMOUNT stack every PASSIVE_TITANIUM_INTERVAL
        rounds (see docs/official/docs/game-rules-harvester.txt)."""
        stacks_per_round = len(self.harvesters) / GameConstants.PASSIVE_TITANIUM_INTERVAL
        return stacks_per_round * GameConstants.PASSIVE_TITANIUM_AMOUNT


@dataclass(eq=False)
class Harvester:
    position: tuple[int, int]
    connected: bool = False
    entry_path: Path | None = None  # first Path node its output reaches

    @property
    def path(self) -> list[tuple[int, int]] | None:
        """Conveyor/splitter coordinates from this harvester to the core
        (core excluded), or None if unreachable."""
        if not self.connected:
            return None
        coords = []
        node = self.entry_path
        while node is not None:
            coords.append(node.position)
            node = node.next
        return coords


class Player:
    def __init__(self, ct: Controller):
        self.harvester_positions: list[tuple] = []
        self.harvesters: list[Harvester] = []
        self.paths: dict[tuple[int, int], Path] = {}
        self.map = self._contruct_map(ct)

    @property
    def _num_harvesters(self) -> int:
        return len(self.harvester_positions)

    def _contruct_map(self, ct: Controller) -> list[list]:
        """Row major, i.e. elements map[row][column]"""
        return [[None for _ in range(ct.get_map_width())] for _ in range(ct.get_map_height())]

    def _accepts_from(self, entity, travel_dir: Direction) -> bool:
        """Whether `entity` accepts a stack arriving via a step in travel_dir."""
        if entity.type == EntityType.CORE:
            return True
        if entity.type == EntityType.CONVEYOR:
            # Every cardinal side feeds a conveyor except the one it outputs
            # to -- that's the tile you'd be arriving from if you travelled
            # in the opposite of its facing direction.
            return travel_dir != _OPPOSITE[entity.direction]
        if entity.type == EntityType.SPLITTER:
            # Splitters only accept from directly behind, i.e. the incoming
            # step matches the facing direction itself.
            return travel_dir == entity.direction
        return False

    @staticmethod
    def _out_dirs(entity) -> tuple[Direction, ...]:
        """Directions `entity` can actually push a stack out to."""
        if entity.type == EntityType.CONVEYOR:
            return (entity.direction,)
        if entity.type == EntityType.SPLITTER:
            return tuple(d for d in CARDINALS if d != _OPPOSITE[entity.direction])
        return ()

    def _build_paths(self, ct: Controller) -> dict[tuple[int, int], Path]:
        """Single reverse BFS from every Core tile, walking predecessor edges
        (the mirror of _accepts_from/_out_dirs). Builds one Path node per
        conveyor/splitter tile that can eventually deliver to the core,
        chained toward the core via `.next`. `.harvesters` is left empty here
        -- _update_harvesters fills it in per harvester afterwards. Computed
        once per call regardless of harvester count -- O(width x height)
        total, versus re-deriving reachability from scratch per harvester.

        A tile that also existed in the previous self.paths keeps its
        actual_flow/observation state (a new Path object is still created,
        since `next`/`harvesters` depend on the current network shape, but
        flow history shouldn't reset just because the network got rescanned).
        """
        width, height = ct.get_map_width(), ct.get_map_height()

        core_tiles = {
            (x, y)
            for y in range(height)
            for x in range(width)
            if (entity := self.map[y][x]) is not None and entity.type == EntityType.CORE
        }

        paths: dict[tuple[int, int], Path] = {}
        frontier = deque(core_tiles)

        while frontier:
            cx, cy = frontier.popleft()
            target = self.map[cy][cx]
            for d in CARDINALS:
                dx, dy = _DELTA[d]
                px, py = cx - dx, cy - dy
                if not (0 <= px < width and 0 <= py < height):
                    continue
                key = (px, py)
                if key in core_tiles or key in paths:
                    continue

                source = self.map[py][px]
                if source is None or source.type not in (EntityType.CONVEYOR, EntityType.SPLITTER):
                    continue
                # d is the direction of travel from source into target: valid
                # only if source actually outputs that way AND target accepts
                # an arrival from that direction.
                if d not in self._out_dirs(source) or not self._accepts_from(target, d):
                    continue

                next_path = None if (cx, cy) in core_tiles else paths[(cx, cy)]
                node = Path(position=key, next=next_path)
                previous = self.paths.get(key)
                if previous is not None:
                    node.actual_flow = previous.actual_flow
                    node._last_seen_id = previous._last_seen_id
                paths[key] = node
                frontier.append(key)

        return paths

    def _find_entry(
        self, ct: Controller, position: tuple[int, int], paths: dict[tuple[int, int], Path]
    ) -> tuple[bool, Path | None]:
        """Whether `position` (a harvester) has a viable route to the core,
        and the first Path node that route passes through (None either if
        unreachable, or if the very next tile IS the core -- zero conveyors
        in between)."""
        width, height = ct.get_map_width(), ct.get_map_height()
        start_x, start_y = position

        for d in CARDINALS:
            dx, dy = _DELTA[d]
            x, y = start_x + dx, start_y + dy
            if not (0 <= x < width and 0 <= y < height):
                continue

            entity = self.map[y][x]
            if entity is None or not self._accepts_from(entity, d):
                continue
            if entity.type == EntityType.CORE:
                return True, None
            if (x, y) in paths:
                return True, paths[(x, y)]

        return False, None

    def _update_harvesters(self, ct: Controller) -> None:
        """Recompute the conveyor network's reachability and each tile's
        expected flow. Call this whenever the conveyor network may have
        changed (built/destroyed) before reading self.harvesters/self.paths.
        """
        paths = self._build_paths(ct)
        harvesters: list[Harvester] = []

        for pos in self.harvester_positions:
            connected, entry_path = self._find_entry(ct, pos, paths)
            harvester = Harvester(position=pos, connected=connected, entry_path=entry_path)
            harvesters.append(harvester)

            node = entry_path
            while node is not None:
                node.harvesters.append(harvester)
                node = node.next

        self.harvesters = harvesters
        self.paths = paths

    def _observe_flow(self, ct: Controller) -> None:
        """Update actual_flow for every Path currently within the Core's
        vision. Call once per round from the Core's own run(), after
        _update_harvesters (a fresh self.paths needs to exist first).

        A conveyor/splitter holds exactly one stack at a time, so a changed
        get_stored_resource_id() since last observed means a fresh stack
        passed through this round; an unchanged id means the previous stack
        is still sitting there (backpressure), not a new delivery. Each
        round contributes one sample -- PASSIVE_TITANIUM_AMOUNT on arrival,
        0 otherwise -- folded into an EMA, since a single round's snapshot
        can't tell you a rate on its own. Paths outside vision this round
        are left untouched: there's nothing to observe.

        Walks ct.get_nearby_tiles() (bounded by the Core's vision radius,
        e.g. ~113 tiles) rather than every entry in self.paths (up to the
        full map) -- the vast majority of paths.items() would just fail an
        is_in_vision check anyway, so it's cheaper to only ever look at
        tiles already known to be visible.
        """
        if ct.get_entity_type() != EntityType.CORE:
            raise ValueError("_observe_flow must be called from the Core's own turn")

        for tile in ct.get_nearby_tiles():
            path = self.paths.get((tile.x, tile.y))
            if path is None:
                continue

            building_id = ct.get_tile_building_id(tile)
            if building_id is None:
                continue

            stack_id = ct.get_stored_resource_id(building_id)
            arrived = stack_id is not None and stack_id != path._last_seen_id
            sample = GameConstants.PASSIVE_TITANIUM_AMOUNT if arrived else 0.0

            path.actual_flow = _FLOW_EMA_ALPHA * sample + (1 - _FLOW_EMA_ALPHA) * path.actual_flow
            path._last_seen_id = stack_id
