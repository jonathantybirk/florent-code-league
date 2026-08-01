"""Casemate Oracle: map-specific protected piercing-sentinel siege."""

from collections import deque

from fcode import Controller, Direction, EntityType, Environment, Position
from atlas import identify_visible


D8 = [d for d in Direction if d != Direction.CENTRE]
CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
SLOT_CORE = 0
SLOT_ENEMY = 1
SLOT_ORE = 2
SLOT_ROLES = 3
SLOT_WALLS = 8
SLOT_MAP = 9
MAX_BUILDERS = 5
AMMO_TARGET = 60

MAP_NAMES = (
    "atoll", "aurora", "bridge", "crossfire", "duel", "fjord", "hive",
    "jackpot", "longship", "pinch", "quarry", "runestone", "showdown",
    "skerry", "sprint", "strait", "string", "sweden", "twins", "vase",
    "vault",
)

# These compact maps reward getting the third piercing lane online before a
# second miner. On longer maps, two belts repay before contact.
THREE_MASON_MAPS = {"bridge", "duel", "showdown", "sprint", "string", "vase"}
# Immediate contact makes a three-wall opening too slow on these maps.
FAST_CONTACT_MAPS = {"bridge", "showdown", "sprint", "string"}
SENTINEL_SIDES = {
    ("bridge", (0, 6)), ("skerry", (2, 17)), ("sprint", (1, 1)),
    ("strait", (2, 2)), ("string", (0, 6)),
}


def pack(pos: Position) -> int:
    return ((pos.x + 1) << 16) | (pos.y + 1)


def unpack(value: int) -> Position | None:
    if not value:
        return None
    return Position((value >> 16) - 1, (value & 0xFFFF) - 1)


def inside(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


def direction_between(source: Position, target: Position) -> Direction | None:
    dx, dy = target.x - source.x, target.y - source.y
    if dx == 0 and dy == 0:
        return None
    if not (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
        return None
    step = (0 if dx == 0 else (1 if dx > 0 else -1),
            0 if dy == 0 else (1 if dy > 0 else -1))
    return next((d for d in D8 if d.delta() == step), None)


class Player:
    def __init__(self):
        self.spawned = 0
        self.core: Position | None = None
        self.role: str | None = None
        self.known_passable: set[tuple[int, int]] = set()
        self.known_blocked: set[tuple[int, int]] = set()
        self.visited: set[tuple[int, int]] = set()
        self.sentinel: Position | None = None
        self.routing = False
        self.route_pending: Position | None = None
        self.last: Position | None = None
        self.stuck = 0
        self.atlas = None
        self.turrets_built = 0

    def run(self, ct: Controller) -> None:
        kind = ct.get_entity_type()
        if kind == EntityType.CORE:
            self.run_core(ct)
        elif kind == EntityType.BUILDER_BOT:
            self.run_builder(ct)
        elif kind == EntityType.SENTINEL:
            self.run_sentinel(ct)
        elif kind == EntityType.GUNNER:
            self.run_gunner(ct)

    def use_sentinel(self) -> bool:
        return (self.atlas is None or self.core is None
                or (self.atlas.name, (self.core.x, self.core.y)) in SENTINEL_SIDES)

    def run_core(self, ct: Controller) -> None:
        pos = ct.get_position()
        ct.write_store(SLOT_CORE, pack(pos))
        if self.atlas is None:
            self.atlas = identify_visible(ct, (pos.x, pos.y))
        if self.atlas is not None:
            ct.write_store(SLOT_MAP, MAP_NAMES.index(self.atlas.name) + 1)

        # Sentinels spend in ten-ammo bursts. Preserve a builder purchase while
        # establishing the team, then keep enough for two simultaneous shots.
        # After spawning, retain a real construction bank. Without this, every
        # passive titanium tick is immediately converted to ammo and the cheap
        # barrier half of the strategy never exists in practice.
        map_name = self.atlas.name if self.atlas is not None else None
        required_walls = 0 if map_name in FAST_CONTACT_MAPS else 3
        fortified = ct.read_store(SLOT_WALLS) >= required_walls
        reserve = (ct.get_builder_bot_cost() if self.spawned < MAX_BUILDERS else
                   30 if fortified else 100)
        missing = AMMO_TARGET - ct.get_global_ammo()
        amount = min(missing, max(0, ct.get_global_resources() - reserve))
        if amount > 0 and ct.can_convert_ammo(amount):
            ct.convert_ammo(amount)

        if self.spawned >= MAX_BUILDERS:
            return
        target = Position(ct.get_map_width() - 2 - pos.x,
                          ct.get_map_height() - 2 - pos.y)
        choices = sorted(ct.get_nearby_tiles(2),
                         key=lambda p: (p.distance_squared(target), p.x, p.y))
        for candidate in choices:
            if ct.can_spawn(candidate):
                builder_id = ct.spawn_builder(candidate)
                ct.write_store(SLOT_ROLES + self.spawned, builder_id)
                self.spawned += 1
                return

    def run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        if self.core is None:
            self.core = unpack(ct.read_store(SLOT_CORE))
        if self.atlas is None and self.core is not None:
            self.atlas = identify_visible(ct, (self.core.x, self.core.y))
            if self.atlas is not None:
                for y in range(self.atlas.height):
                    for x in range(self.atlas.width):
                        key = (x, y)
                        if key in self.atlas.walls:
                            self.known_blocked.add(key)
                        else:
                            self.known_passable.add(key)
        # Entity ids interleave both teams and all newly built structures, so
        # the Core publishes explicit spawn-order assignments.
        map_name = self.atlas.name if self.atlas is not None else None
        roles = (("mason", "guard", "mason", "miner", "mason")
                 if map_name in THREE_MASON_MAPS else
                 ("mason", "miner", "guard", "miner", "mason"))
        for index, role in enumerate(roles):
            if ct.read_store(SLOT_ROLES + index) == ct.get_id():
                self.role = role
                break
        if self.role is None:
            return

        self.observe(ct)
        self.report_enemy(ct)
        if self.last == pos:
            self.stuck += 1
        else:
            self.stuck = 0
        self.last = pos
        self.visited.add((pos.x, pos.y))

        if ct.get_action_cooldown() == 0:
            if self.heal_valuable(ct):
                pass
            elif self.role == "miner" and self.extend_route(ct):
                pass
            elif self.role == "miner" and self.build_harvester(ct):
                pass
            elif self.role == "mason":
                self.build_casemate(ct)
            elif self.role == "guard":
                self.build_home_wall(ct)

        target = self.choose_target(ct)
        if target is not None:
            self.step_toward(ct, target)

    def observe(self, ct: Controller) -> None:
        for tile in ct.get_nearby_tiles():
            key = (tile.x, tile.y)
            env = ct.get_tile_env(tile)
            building = ct.get_tile_building_id(tile)
            if env == Environment.WALL or building is not None:
                self.known_blocked.add(key)
                self.known_passable.discard(key)
            else:
                self.known_passable.add(key)
                self.known_blocked.discard(key)
            if env == Environment.ORE_TITANIUM and building is None:
                ct.write_store(SLOT_ORE, pack(tile))

    def report_enemy(self, ct: Controller) -> None:
        enemies = [i for i in ct.get_nearby_entities()
                   if ct.get_team(i) != ct.get_team()]
        cores = [i for i in enemies if ct.get_entity_type(i) == EntityType.CORE]
        if cores:
            ct.write_store(SLOT_ENEMY, pack(ct.get_position(cores[0])))

    def enemy_core(self, ct: Controller) -> Position:
        if self.atlas is not None:
            return Position(*self.atlas.enemy_core)
        seen = unpack(ct.read_store(SLOT_ENEMY))
        if seen is not None:
            return seen
        core = self.core or ct.get_position()
        return Position(ct.get_map_width() - 2 - core.x,
                        ct.get_map_height() - 2 - core.y)

    def heal_valuable(self, ct: Controller) -> bool:
        pos = ct.get_position()
        candidates = []
        for d in CARDINALS:
            tile = pos.add(d)
            if not inside(ct, tile) or not ct.can_heal(tile):
                continue
            building = ct.get_tile_building_id(tile)
            priority = 0
            if building is not None:
                kind = ct.get_entity_type(building)
                priority = {EntityType.SENTINEL: 4, EntityType.CORE: 3,
                            EntityType.BARRIER: 2}.get(kind, 1)
            candidates.append((-priority, tile.x, tile.y, tile))
        if not candidates:
            return False
        ct.heal(min(candidates)[-1])
        return True

    def build_harvester(self, ct: Controller) -> bool:
        pos = ct.get_position()
        for d in CARDINALS:
            tile = pos.add(d)
            if inside(ct, tile) and ct.can_build_harvester(tile):
                ct.build_harvester(tile)
                self.known_blocked.add((tile.x, tile.y))
                # Walk home and leave a rear-facing belt on each vacated tile.
                self.routing = True
                self.route_pending = pos
                return True
        return False

    def extend_route(self, ct: Controller) -> bool:
        if not self.routing or self.route_pending is None:
            return False
        pos = ct.get_position()
        pending = self.route_pending
        direction = direction_between(pending, pos)
        if (direction in CARDINALS and pending.distance_squared(pos) == 1
                and ct.can_build_conveyor(pending, direction)):
            ct.build_conveyor(pending, direction)
            self.known_blocked.discard((pending.x, pending.y))
            self.known_passable.add((pending.x, pending.y))
            return True
        return False

    def build_casemate(self, ct: Controller) -> bool:
        enemy = self.enemy_core(ct)
        pos = ct.get_position()

        # Let the guard spend the cheap part of the opening first. Otherwise
        # scaled sentinel purchases consume the bank before a wall is legal.
        map_name = self.atlas.name if self.atlas is not None else None
        required_walls = 0 if map_name in FAST_CONTACT_MAPS else 3
        if ct.read_store(SLOT_WALLS) < required_walls:
            return False

        # Once a sentinel exists, wrap its enemy-facing side first. Sentinels
        # pierce the screen; conventional return fire and builders do not.
        if self.sentinel is not None:
            facing = direction_between(self.sentinel, enemy)
            if facing is not None:
                front = self.sentinel.add(facing)
                if pos.distance_squared(front) == 1 and ct.can_build_barrier(front):
                    ct.build_barrier(front)
                    self.known_blocked.add((front.x, front.y))
                    return True
            for d in CARDINALS:
                screen = self.sentinel.add(d)
                if (pos.distance_squared(screen) == 1
                        and screen != pos and ct.can_build_barrier(screen)):
                    ct.build_barrier(screen)
                    self.known_blocked.add((screen.x, screen.y))
                    return True

        # Search only legal eight-way rays to one of the core's four tiles.
        turret_type = EntityType.SENTINEL if self.use_sentinel() else EntityType.GUNNER
        range_sq = 32 if turret_type == EntityType.SENTINEL else 13
        core_tiles = [enemy, Position(enemy.x + 1, enemy.y),
                      Position(enemy.x, enemy.y + 1), Position(enemy.x + 1, enemy.y + 1)]
        candidates = []
        for d in CARDINALS:
            seat = pos.add(d)
            if not inside(ct, seat):
                continue
            for target in core_tiles:
                facing = direction_between(seat, target)
                can_build = (ct.can_build_sentinel(seat, facing)
                             if turret_type == EntityType.SENTINEL else
                             ct.can_build_gunner(seat, facing)) if facing is not None else False
                if (facing is not None and seat.distance_squared(target) <= range_sq
                        and can_build):
                    candidates.append((seat.distance_squared(target), seat.x, seat.y,
                                       seat, facing))
        if candidates:
            *_, seat, facing = min(candidates)
            if turret_type == EntityType.SENTINEL:
                ct.build_sentinel(seat, facing)
                self.sentinel = seat
            else:
                ct.build_gunner(seat, facing)
            self.turrets_built += 1
            self.known_blocked.add((seat.x, seat.y))
            return True
        return False

    def build_home_wall(self, ct: Controller) -> bool:
        if self.core is None:
            return False
        pos = ct.get_position()
        enemy = self.enemy_core(ct)
        ring = []
        for x in range(self.core.x - 1, self.core.x + 3):
            for y in range(self.core.y - 1, self.core.y + 3):
                if self.core.x <= x <= self.core.x + 1 and self.core.y <= y <= self.core.y + 1:
                    continue
                tile = Position(x, y)
                if inside(ct, tile):
                    ring.append(tile)
        ring.sort(key=lambda p: (p.distance_squared(enemy), p.x, p.y))
        for tile in ring:
            if pos.distance_squared(tile) == 1 and ct.can_build_barrier(tile):
                ct.build_barrier(tile)
                self.known_blocked.add((tile.x, tile.y))
                ct.write_store(SLOT_WALLS, ct.read_store(SLOT_WALLS) + 1)
                return True
        return False

    def choose_target(self, ct: Controller) -> Position | None:
        pos = ct.get_position()
        if self.role == "mason":
            if self.sentinel is not None:
                facing = direction_between(self.sentinel, self.enemy_core(ct))
                if facing is not None:
                    front = self.sentinel.add(facing)
                    if inside(ct, front):
                        return front
            staging = self.oracle_siege_staging(ct)
            return staging if staging is not None else self.enemy_core(ct)

        if self.role == "guard" and self.core is not None:
            missing = []
            for x in range(self.core.x - 1, self.core.x + 3):
                for y in range(self.core.y - 1, self.core.y + 3):
                    tile = Position(x, y)
                    if (inside(ct, tile)
                            and not (self.core.x <= x <= self.core.x + 1
                                     and self.core.y <= y <= self.core.y + 1)
                            and (tile.x, tile.y) not in self.known_blocked):
                        missing.append(tile)
            if missing:
                core_tiles = [Position(self.core.x + dx, self.core.y + dy)
                              for dx in (0, 1) for dy in (0, 1)]
                # Stand inside the Core and construct outward. Walking onto a
                # missing wall tile would make that tile unbuildable.
                return min(core_tiles, key=lambda p: (
                    min(p.distance_squared(wall) for wall in missing),
                    p.distance_squared(pos), p.x, p.y))
            return self.core

        if self.routing and self.core is not None:
            return self.core

        ore = unpack(ct.read_store(SLOT_ORE))
        if ore is not None:
            return ore
        # Deterministic coverage: miners take opposite horizontal corners.
        far_x = ct.get_map_width() - 1 if ct.get_id() % 2 else 0
        far_y = 0 if ct.get_id() % 4 < 2 else ct.get_map_height() - 1
        return Position(far_x, far_y)

    def oracle_siege_staging(self, ct: Controller) -> Position | None:
        """Choose a build stance, never the sentinel seat itself."""
        if self.atlas is None:
            return None
        enemy = Position(*self.atlas.enemy_core)
        range_limit = 32 if self.use_sentinel() else 13
        core_tiles = [enemy, Position(enemy.x + 1, enemy.y),
                      Position(enemy.x, enemy.y + 1), Position(enemy.x + 1, enemy.y + 1)]
        enemy_foot = {(p.x, p.y) for p in core_tiles}
        choices = []
        for y in range(self.atlas.height):
            for x in range(self.atlas.width):
                seat = Position(x, y)
                if (x, y) in self.atlas.walls or (x, y) in enemy_foot:
                    continue
                rays = [target for target in core_tiles
                        if direction_between(seat, target) is not None
                        and seat.distance_squared(target) <= range_limit]
                if not rays:
                    continue
                for d in CARDINALS:
                    stage = seat.add(d)
                    key = (stage.x, stage.y)
                    if (not inside(ct, stage) or key in self.atlas.walls
                            or key in enemy_foot):
                        continue
                    # Prefer outer-range seats, then the staging tile nearest
                    # this mason. Exact atlas BFS handles walls after selection.
                    range_sq = max(seat.distance_squared(t) for t in rays)
                    choices.append((-range_sq,
                                    stage.distance_squared(ct.get_position()),
                                    stage.x, stage.y, stage))
        return min(choices)[-1] if choices else None

    def step_toward(self, ct: Controller, target: Position) -> None:
        if ct.get_move_cooldown() != 0:
            return
        start = ct.get_position()
        first = self.bfs_step(ct, start, target)
        allowed = CARDINALS if self.routing else D8
        directions = ([first] if first in allowed else []) + allowed
        seen = set()
        ranked = []
        for d in directions:
            if d is None or d in seen or not ct.can_move(d):
                continue
            seen.add(d)
            nxt = start.add(d)
            novelty = (nxt.x, nxt.y) not in self.visited
            ranked.append((0 if d == first else 1, 0 if novelty else 1,
                           nxt.distance_squared(target), d.value, d))
        if ranked:
            old = start
            ct.move(min(ranked)[-1])
            if self.routing:
                # The conveyor built this round occupied the previous pending
                # tile; the tile just vacated becomes next round's belt piece.
                self.route_pending = old
                if self.core is not None:
                    now = ct.get_position()
                    if self.core.x <= now.x <= self.core.x + 1 and self.core.y <= now.y <= self.core.y + 1:
                        # One final turn will place the pending conveyor into Core.
                        pass

    def bfs_step(self, ct: Controller, start: Position, target: Position) -> Direction | None:
        start_key = (start.x, start.y)
        queue = deque([start_key])
        parent = {start_key: None}
        best = start_key
        while queue:
            current = queue.popleft()
            if ((current[0] - target.x) ** 2 + (current[1] - target.y) ** 2
                    < (best[0] - target.x) ** 2 + (best[1] - target.y) ** 2):
                best = current
            if current == (target.x, target.y):
                best = current
                break
            for d in D8:
                dx, dy = d.delta()
                nxt = current[0] + dx, current[1] + dy
                if nxt in parent or nxt not in self.known_passable:
                    continue
                parent[nxt] = current
                queue.append(nxt)
        if best == start_key:
            return None
        while parent[best] != start_key:
            best = parent[best]
            if best is None:
                return None
        delta = best[0] - start.x, best[1] - start.y
        return next((d for d in D8 if d.delta() == delta), None)

    def run_sentinel(self, ct: Controller) -> None:
        targets = [i for i in ct.get_nearby_entities()
                   if ct.get_team(i) != ct.get_team()
                   and ct.can_fire(ct.get_position(i))]
        if targets:
            target = min(targets, key=lambda i: (
                0 if ct.get_entity_type(i) == EntityType.CORE else 1,
                ct.get_hp(i), ct.get_position(i).distance_squared(ct.get_position())))
            ct.fire(ct.get_position(target))

    def run_gunner(self, ct: Controller) -> None:
        target = ct.get_gunner_target()
        if target is not None and ct.can_fire(target):
            ct.fire(target)
