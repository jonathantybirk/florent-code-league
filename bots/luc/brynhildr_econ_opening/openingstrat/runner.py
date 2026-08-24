"""Small controller adapter for data-only opening plans."""

from collections import deque

from fcode import Direction, EntityType, Environment, Position

from .plans import CATALOG_PLANS, PLANS, resize_plan

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)


class OpeningRunner:
    """Execute a precomputed opening; return False when no plan applies/done."""

    def __init__(self, builder_count=4, use_store=True, enabled_maps=None):
        if not 1 <= builder_count <= 4:
            raise ValueError("builder_count must be between 1 and 4")
        self.builder_count = builder_count
        self.use_store = use_store
        self.enabled_maps = frozenset(enabled_maps) if enabled_maps is not None else None
        self.builder_index = None
        self.task_index = 0
        self.plan = None
        self.escape_target = None
        self.core_key = None
        self.map_name = None

    def _core_key(self, ct):
        if not self.use_store:
            if self.core_key is not None:
                return self.core_key
            try:
                for entity_id in ct.get_nearby_buildings():
                    if (ct.get_team(entity_id) == ct.get_team()
                            and ct.get_entity_type(entity_id) == EntityType.CORE):
                        pos = ct.get_position(entity_id)
                        self.core_key = ((ct.get_map_width(), ct.get_map_height()), (pos.x, pos.y))
                        return self.core_key
            except Exception:
                pass
            return None
        packed = ct.read_store(0)
        if not packed:
            return None
        core = ((packed >> 16) - 1, (packed & 0xFFFF) - 1)
        return ((ct.get_map_width(), ct.get_map_height()), core)

    @staticmethod
    def _terrain_mismatches(ct, walls, ores):
        return sum(
            (env == Environment.WALL) != (tile in walls)
            or (env == Environment.ORE_TITANIUM) != (tile in ores)
            for tile, env in (((p.x, p.y), ct.get_tile_env(p)) for p in ct.get_nearby_tiles())
        )

    def run_core(self, ct) -> bool:
        pos = ct.get_position()
        if self.use_store:
            ct.write_store(0, ((pos.x + 1) << 16) | (pos.y + 1))
        key = ((ct.get_map_width(), ct.get_map_height()), (pos.x, pos.y))
        plan = PLANS.get(key)
        if plan is not None:
            self.map_name = "sprint"
            if self.use_store:
                ct.write_store(1, 0x80000000)
        else:
            candidates = CATALOG_PLANS.get(key, ())
            if self.plan is None and candidates:
                ranked = []
                for index, (_name, walls, ores, candidate) in enumerate(candidates):
                    mismatches = self._terrain_mismatches(ct, walls, ores)
                    ranked.append((mismatches, index, candidate))
                _, index, self.plan = min(ranked)
                self.map_name = candidates[index][0]
                self.plan_code = index + 1
            plan = self.plan
            if plan is not None:
                if self.use_store:
                    ct.write_store(1, self.plan_code)
        if plan is None:
            return False
        if self.enabled_maps is not None and self.map_name not in self.enabled_maps:
            return False
        plan = resize_plan(plan, self.builder_count)
        self.plan = plan
        round_no = ct.get_current_round()
        if round_no >= len(plan.spawns):
            return True
        target = Position(*plan.spawns[round_no])
        if ct.can_spawn(target):
            ct.spawn_builder(target)
        else:
            for tile in ct.get_nearby_tiles(dist_sq=2):
                if ct.can_spawn(tile):
                    ct.spawn_builder(tile)
                    break
        return True

    def run_builder(self, ct) -> bool:
        key = self._core_key(ct)
        plan = (PLANS.get(key) if key else None) or self.plan
        if plan is None and key:
            code = ct.read_store(1) if self.use_store else 0
            candidates = CATALOG_PLANS.get(key, ())
            if candidates:
                selected = code - 1 if 1 <= code <= len(candidates) else 0
                current_error = self._terrain_mismatches(ct, candidates[selected][1], candidates[selected][2])
                best_error, best_index = min(
                    (self._terrain_mismatches(ct, walls, ores), index)
                    for index, (_name, walls, ores, _candidate) in enumerate(candidates)
                )
                if best_error < current_error:
                    selected = best_index
                    if self.plan is not candidates[selected][3]:
                        self.task_index = 0
                plan = resize_plan(candidates[selected][3], self.builder_count)
                self.plan = plan
                self.map_name = candidates[selected][0]
        if plan is None:
            return False
        if self.enabled_maps is not None and self.map_name not in self.enabled_maps:
            return False
        plan = resize_plan(plan, self.builder_count)
        self.plan = plan
        if self.builder_index is None:
            self.builder_index = ct.get_current_round() - 1
        if not 0 <= self.builder_index < len(plan.tasks):
            return False
        tasks = plan.tasks[self.builder_index]
        required = {task.tile for work in plan.tasks for task in work}
        while self.task_index < len(tasks):
            task = tasks[self.task_index]
            target = Position(*task.tile)
            if self._already_built(ct, task, target):
                self.task_index += 1
                continue
            pos = ct.get_position()
            cx, cy = plan.core
            core_tiles = {(cx, cy), (cx + 1, cy), (cx, cy + 1), (cx + 1, cy + 1)}
            blocked = plan.walls | core_tiles
            unbuilt = {
                other.tile for work in plan.tasks for other in work
                if not self._already_built(ct, other, Position(*other.tile))
            }
            staging_blocked = blocked | (unbuilt - {task.tile})
            staging = (self._safe_harvester_staging(ct, target, staging_blocked) or None
                       if task.kind == "harvester" else None)
            if abs(pos.x - target.x) + abs(pos.y - target.y) == 1:
                if staging is not None and (pos.x, pos.y) not in staging:
                    direction = self._next_step(ct, target, blocked, staging)
                    if direction is not None and ct.can_move(direction):
                        ct.move(direction)
                    return True
                if task.kind == "harvester" and ct.can_build_harvester(target):
                    ct.build_harvester(target)
                    self.task_index += 1
                elif task.kind == "conveyor":
                    output = Position(*task.output)
                    direction = target.cardinal_direction_to(output)
                    if ct.can_build_conveyor(target, direction):
                        ct.build_conveyor(target, direction)
                        self.task_index += 1
                if self.task_index > 0 and self._already_built(ct, task, target):
                    return True
                # A temporary occupant will replan on its own turn. Wandering
                # in an arbitrary direction here creates yield oscillations.
                return True
            direction = self._next_step(ct, target, blocked, staging)
            if direction is not None and ct.can_move(direction):
                ct.move(direction)
            return True
        pos = ct.get_position()
        if (pos.x, pos.y) not in required:
            return False
        cx, cy = plan.core
        blocked = plan.walls | {(cx, cy), (cx + 1, cy), (cx, cy + 1), (cx + 1, cy + 1)}
        if self.escape_target is None:
            self.escape_target = self._escape_goal(ct, required, blocked)
        if self.escape_target is not None:
            goal = Position(*self.escape_target)
            direction = self._next_step(ct, goal, blocked, frozenset({self.escape_target}))
            if direction is not None and ct.can_move(direction):
                ct.move(direction)
                return True
        return False

    @staticmethod
    def _already_built(ct, task, target):
        try:
            building = ct.get_tile_building_id(target)
        except Exception:
            return False
        if building is None:
            return False
        return ct.get_entity_type(building) == (
            EntityType.HARVESTER if task.kind == "harvester" else EntityType.CONVEYOR
        )

    @staticmethod
    def _next_step(ct, target, walls=frozenset(), staging=None):
        start = ct.get_position()
        queue = deque([(start, None)])
        seen = {(start.x, start.y)}
        while queue:
            pos, first = queue.popleft()
            if ((pos.x, pos.y) in staging if staging is not None
                    else abs(pos.x - target.x) + abs(pos.y - target.y) == 1):
                return first
            for direction in CARDINALS:
                nxt = pos.add(direction)
                key = (nxt.x, nxt.y)
                if key in seen or not (0 <= nxt.x < ct.get_map_width() and 0 <= nxt.y < ct.get_map_height()):
                    continue
                # A build target is a goal to stand beside, never a transit
                # tile. Entering it only forces a later step back out.
                if staging is None and nxt == target:
                    continue
                if key in walls:
                    continue
                seen.add(key)
                if pos == start:
                    if not ct.can_move(direction):
                        continue
                else:
                    try:
                        if ct.get_tile_builder_bot_id(nxt) is not None:
                            continue
                        building = ct.get_tile_building_id(nxt)
                        if (building is not None
                                and ct.get_entity_type(building) not in
                                (EntityType.CONVEYOR, EntityType.SPLITTER)):
                            continue
                    except Exception:
                        pass
                queue.append((nxt, direction if first is None else first))
        return None

    @staticmethod
    def _safe_harvester_staging(ct, target, blocked):
        def traversable(tile):
            key = (tile.x, tile.y)
            if key in blocked or not (0 <= tile.x < ct.get_map_width()
                                      and 0 <= tile.y < ct.get_map_height()):
                return False
            try:
                building = ct.get_tile_building_id(tile)
                return building is None or ct.get_entity_type(building) in (
                    EntityType.CONVEYOR, EntityType.SPLITTER
                )
            except Exception:
                return True

        candidates = []
        for direction in CARDINALS:
            tile = target.add(direction)
            key = (tile.x, tile.y)
            if not traversable(tile):
                continue
            if any(traversable(tile.add(move)) for move in CARDINALS
                   if tile.add(move) != target):
                candidates.append(key)
        return frozenset(candidates)

    @staticmethod
    def _escape_goal(ct, required, blocked):
        start = ct.get_position()
        queue = deque([start])
        seen = {(start.x, start.y)}
        while queue:
            pos = queue.popleft()
            if pos != start and (pos.x, pos.y) not in required:
                return pos.x, pos.y
            for direction in CARDINALS:
                nxt = pos.add(direction)
                key = (nxt.x, nxt.y)
                if key in seen or key in blocked or not (
                    0 <= nxt.x < ct.get_map_width() and 0 <= nxt.y < ct.get_map_height()
                ):
                    continue
                try:
                    if ct.get_tile_builder_bot_id(nxt) is not None:
                        continue
                    building = ct.get_tile_building_id(nxt)
                    if building is not None and ct.get_entity_type(building) not in (
                        EntityType.CONVEYOR, EntityType.SPLITTER
                    ):
                        continue
                except Exception:
                    pass
                seen.add(key)
                queue.append(nxt)
        return None
