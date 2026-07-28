"""Observation encoding and action decoding shared by the RL bot and the training loop.

Keeps the policy's action space small by using macro-actions (e.g. "build a harvester
on the best adjacent ore tile") instead of exposing every low-level engine call. This
trades some expressiveness for a tractable action space; expand per-type action lists
here as the policy proves it can use them.
"""

from __future__ import annotations

import math

from fcode import Controller, Direction, EntityType, Environment, GameConstants, Position

GRID_RADIUS = 3
GRID_SIZE = 2 * GRID_RADIUS + 1  # 7x7
GRID_CHANNELS = 6  # wall, ore, own_building, enemy_building, own_unit, enemy_unit
SCALAR_DIM = 12

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
ALL_DIRS = [d for d in Direction if d != Direction.CENTRE]

ENTITY_TYPES = [
    EntityType.CORE,
    EntityType.BUILDER_BOT,
    EntityType.GUNNER,
    EntityType.SENTINEL,
    EntityType.LAUNCHER,
]

OBS_DIM = GRID_SIZE * GRID_SIZE * GRID_CHANNELS + SCALAR_DIM + len(ENTITY_TYPES)

# Action counts per controllable entity type.
NUM_ACTIONS = {
    EntityType.CORE: 1 + 8,  # NOOP + spawn in one of 8 directions
    EntityType.BUILDER_BOT: 14,
    EntityType.GUNNER: 4,  # NOOP, FIRE, ROTATE_LEFT, ROTATE_RIGHT
    EntityType.SENTINEL: 2,  # NOOP, FIRE
    EntityType.LAUNCHER: 1,  # NOOP (throwing builder bots is a future extension)
}

# Builder bot macro-action indices.
B_NOOP = 0
B_MOVE = list(range(1, 9))  # 1..8 -> ALL_DIRS[0..7]
B_BUILD_HARVESTER = 9
B_BUILD_GUNNER = 10
B_BUILD_CONVEYOR = 11
B_HEAL = 12
B_SELF_DESTRUCT = 13


def _entity_type_onehot(etype: EntityType) -> list[float]:
    return [1.0 if etype == t else 0.0 for t in ENTITY_TYPES]


def encode_observation(ct: Controller) -> list[float]:
    """Encode this unit's local surroundings and status into a flat feature vector."""
    pos = ct.get_position()
    w, h = ct.get_map_width(), ct.get_map_height()
    team = ct.get_team()

    grid = [0.0] * (GRID_SIZE * GRID_SIZE * GRID_CHANNELS)
    for gy in range(GRID_SIZE):
        for gx in range(GRID_SIZE):
            tx, ty = pos.x + (gx - GRID_RADIUS), pos.y + (gy - GRID_RADIUS)
            base = (gy * GRID_SIZE + gx) * GRID_CHANNELS
            if tx < 0 or ty < 0 or tx >= w or ty >= h:
                grid[base + 0] = 1.0  # treat out-of-bounds as wall
                continue
            tile = Position(tx, ty)
            if not ct.is_in_vision(tile):
                continue  # unseen tile: leave as all-zero (unknown)
            env = ct.get_tile_env(tile)
            if env == Environment.WALL:
                grid[base + 0] = 1.0
            elif env == Environment.ORE_TITANIUM:
                grid[base + 1] = 1.0

            building_id = ct.get_tile_building_id(tile)
            if building_id is not None:
                if ct.get_team(building_id) == team:
                    grid[base + 2] = 1.0
                else:
                    grid[base + 3] = 1.0

            builder_id = ct.get_tile_builder_bot_id(tile)
            if builder_id is not None:
                if ct.get_team(builder_id) == team:
                    grid[base + 4] = 1.0
                else:
                    grid[base + 5] = 1.0

    etype = ct.get_entity_type()
    hp = ct.get_hp()
    max_hp = max(ct.get_max_hp(), 1)
    is_turret = etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.LAUNCHER)
    has_gunner_target = etype == EntityType.GUNNER and ct.get_gunner_target() is not None
    scalars = [
        pos.x / max(w, 1),
        pos.y / max(h, 1),
        ct.get_current_round() / GameConstants.MAX_TURNS,
        ct.get_global_resources() / 1000.0,
        ct.get_scale_percent() / 100.0,
        ct.get_unit_count() / GameConstants.MAX_TEAM_UNITS,
        hp / max_hp,
        ct.get_action_cooldown() / 4.0,
        ct.get_move_cooldown() / 4.0,
        (ct.get_ammo_amount() / 20.0) if is_turret else 0.0,
        1.0 if has_gunner_target else 0.0,
        1.0,  # bias term
    ]
    return grid + scalars + _entity_type_onehot(etype)


def _best_adjacent_ore(ct: Controller, pos: Position) -> Position | None:
    for d in ALL_DIRS:
        p = pos.add(d)
        if ct.can_build_harvester(p):
            return p
    return None


def _first_adjacent(ct: Controller, pos: Position, check) -> Position | None:
    for d in ALL_DIRS:
        p = pos.add(d)
        if check(p):
            return p
    return None


def apply_core_action(ct: Controller, action: int) -> None:
    if action == 0:
        return
    d = ALL_DIRS[action - 1]
    pos = ct.get_position().add(d)
    if ct.can_spawn(pos):
        ct.spawn_builder(pos)


def apply_builder_action(ct: Controller, action: int) -> None:
    pos = ct.get_position()

    if action in B_MOVE:
        d = ALL_DIRS[B_MOVE.index(action)]
        if ct.can_move(d):
            ct.move(d)
        return

    if action == B_BUILD_HARVESTER:
        p = _best_adjacent_ore(ct, pos)
        if p is not None:
            ct.build_harvester(p)
        return

    if action == B_BUILD_GUNNER:
        # Face the gunner outward (away from this builder's position).
        for d in CARDINALS:
            t = pos.add(d)
            facing = d
            if ct.can_build_gunner(t, facing):
                ct.build_gunner(t, facing)
                return
        return

    if action == B_BUILD_CONVEYOR:
        for d in CARDINALS:
            t = pos.add(d)
            if ct.can_build_conveyor(t, d):
                ct.build_conveyor(t, d)
                return
        return

    if action == B_HEAL:
        p = _first_adjacent(ct, pos, ct.can_heal)
        if p is not None:
            ct.heal(p)
        return

    if action == B_SELF_DESTRUCT:
        ct.self_destruct()
        return


def apply_gunner_action(ct: Controller, action: int) -> None:
    if action == 0:
        return
    if action == 1:
        target = ct.get_gunner_target()
        if target is not None and ct.can_fire(target):
            ct.fire(target)
        return
    if action == 2:
        d = ct.get_direction().rotate_left()
        if ct.can_rotate(d):
            ct.rotate(d)
        return
    if action == 3:
        d = ct.get_direction().rotate_right()
        if ct.can_rotate(d):
            ct.rotate(d)
        return


def apply_sentinel_action(ct: Controller, action: int) -> None:
    if action == 0:
        return
    facing = ct.get_direction()
    best = None
    best_dist = math.inf
    pos = ct.get_position()
    for tile in ct.get_attackable_tiles():
        if not ct.can_fire(tile):
            continue
        d = pos.distance_squared(tile)
        if d < best_dist:
            best_dist = d
            best = tile
    if best is not None:
        ct.fire(best)


def apply_launcher_action(ct: Controller, action: int) -> None:
    return  # no-op for now


APPLY_FN = {
    EntityType.CORE: apply_core_action,
    EntityType.BUILDER_BOT: apply_builder_action,
    EntityType.GUNNER: apply_gunner_action,
    EntityType.SENTINEL: apply_sentinel_action,
    EntityType.LAUNCHER: apply_launcher_action,
}


def apply_action(ct: Controller, entity_type: EntityType, action: int) -> None:
    APPLY_FN[entity_type](ct, action)
