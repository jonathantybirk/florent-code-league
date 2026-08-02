"""Benchmark probe: economy denial and routing stress, no Core threat.

Three builders cross the map and make the subject's life hard in exactly the
ways weak mechanics fail: barriers on the subject's ore (harvester denial),
fire at conveyors (belt sabotage), and parking on the Core's spawn ring
(spawn denial + body-blocking). It never attacks the Core, so any game the
subject loses to this probe is lost on mechanics, not on strategy.
"""

from collections import deque

from fcode import Controller, Direction, EntityType, Environment, GameError

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
SLOT_ENEMY_CORE = 0
MAX_BUILDERS = 3


def pack(pos) -> int:
    return ((pos.x + 1) << 8) | (pos.y + 1)


def unpack(value):
    if not value:
        return None
    return ((value >> 8) - 1, (value & 0xFF) - 1)


class Player:
    def __init__(self):
        self.spawned = 0
        self.blocked_ores = set()
        self.walls = set()
        self.target = None

    def run(self, ct: Controller) -> None:
        try:
            if ct.get_entity_type() == EntityType.CORE:
                self._core(ct)
            elif ct.get_entity_type() == EntityType.BUILDER_BOT:
                self._builder(ct)
        except GameError:
            pass

    def _core(self, ct: Controller) -> None:
        me = ct.get_position()
        # Farthest symmetry candidate is the enemy core on most pool maps.
        w, h = ct.get_map_width(), ct.get_map_height()
        candidates = [(w - 2 - me.x, h - 2 - me.y), (w - 2 - me.x, me.y),
                      (me.x, h - 2 - me.y)]
        guess = max(candidates,
                    key=lambda c: (c[0] - me.x) ** 2 + (c[1] - me.y) ** 2)
        for i in ct.get_nearby_entities():
            if (ct.get_team(i) != ct.get_team()
                    and ct.get_entity_type(i) == EntityType.CORE):
                p = ct.get_position(i)
                guess = (p.x, p.y)
        ct.write_store(SLOT_ENEMY_CORE, ((guess[0] + 1) << 8) | (guess[1] + 1))
        if self.spawned < MAX_BUILDERS:
            for tile in sorted(ct.get_nearby_tiles(2),
                               key=lambda t: (t.x, t.y)):
                if ct.can_spawn(tile):
                    ct.spawn_builder(tile)
                    self.spawned += 1
                    return

    def _builder(self, ct: Controller) -> None:
        me = ct.get_position()
        enemy_core = unpack(ct.read_store(SLOT_ENEMY_CORE))
        if enemy_core is None:
            return
        for tile in ct.get_nearby_tiles():
            if ct.get_tile_env(tile) == Environment.WALL:
                self.walls.add((tile.x, tile.y))

        # 1. Adjacent enemy conveyor/splitter/harvester: shoot it.
        for d in CARDINALS:
            t = me.add(d)
            if not self._inside(ct, t):
                continue
            b = ct.get_tile_building_id(t)
            if (b is not None and ct.get_team(b) != ct.get_team()
                    and ct.get_entity_type(b) in (
                        EntityType.CONVEYOR, EntityType.SPLITTER,
                        EntityType.HARVESTER)
                    and ct.can_fire(t)):
                ct.fire(t)
                return
        # 2. Adjacent free enemy-half ore: barrier it.
        for d in CARDINALS:
            t = me.add(d)
            if (self._inside(ct, t)
                    and ct.get_tile_env(t) == Environment.ORE_TITANIUM
                    and self._enemy_half(ct, t, enemy_core)
                    and ct.can_build_barrier(t)):
                ct.build_barrier(t)
                self.blocked_ores.add((t.x, t.y))
                return
        # 3. Walk: nearest unblocked visible enemy-half ore, else spawn ring.
        goal = None
        ores = [t for t in ct.get_nearby_tiles()
                if ct.get_tile_env(t) == Environment.ORE_TITANIUM
                and (t.x, t.y) not in self.blocked_ores
                and ct.get_tile_building_id(t) is None
                and self._enemy_half(ct, t, enemy_core)]
        if ores:
            goal = min(ores, key=lambda t: (
                (t.x - me.x) ** 2 + (t.y - me.y) ** 2, t.x, t.y))
            goal = (goal.x, goal.y)
        if goal is None:
            ring = [(enemy_core[0] + dx, enemy_core[1] + dy)
                    for dx in (-1, 0, 1, 2) for dy in (-1, 0, 1, 2)
                    if dx in (-1, 2) or dy in (-1, 2)]
            ring = [g for g in ring if 0 <= g[0] < ct.get_map_width()
                    and 0 <= g[1] < ct.get_map_height()]
            if ring:
                goal = ring[ct.get_id() % len(ring)]
        if goal is None or (me.x, me.y) == goal:
            return
        step = self._bfs_step(ct, (me.x, me.y), goal)
        if step is not None and ct.can_move(step):
            ct.move(step)

    def _enemy_half(self, ct, tile, enemy_core) -> bool:
        return ((tile.x - enemy_core[0]) ** 2 + (tile.y - enemy_core[1]) ** 2
                <= (ct.get_map_width() ** 2 + ct.get_map_height() ** 2) // 4)

    def _inside(self, ct, pos) -> bool:
        return (0 <= pos.x < ct.get_map_width()
                and 0 <= pos.y < ct.get_map_height())

    def _bfs_step(self, ct, start, goal):
        deltas = {(0, -1): Direction.NORTH, (1, 0): Direction.EAST,
                  (0, 1): Direction.SOUTH, (-1, 0): Direction.WEST}
        best, best_d2 = None, (start[0] - goal[0]) ** 2 + (start[1] - goal[1]) ** 2
        queue, parent = deque([start]), {start: None}
        expansions = 0
        while queue and expansions < 2500:
            cur = queue.popleft()
            expansions += 1
            d2 = (cur[0] - goal[0]) ** 2 + (cur[1] - goal[1]) ** 2
            if d2 < best_d2:
                best, best_d2 = cur, d2
                if d2 == 0:
                    break
            for dx, dy in deltas:
                nxt = (cur[0] + dx, cur[1] + dy)
                if (nxt in parent or nxt in self.walls
                        or not (0 <= nxt[0] < ct.get_map_width())
                        or not (0 <= nxt[1] < ct.get_map_height())):
                    continue
                parent[nxt] = cur
                queue.append(nxt)
        if best is None:
            return None
        while parent[best] != start:
            best = parent[best]
            if best is None:
                return None
        return deltas.get((best[0] - start[0], best[1] - start[1]))
