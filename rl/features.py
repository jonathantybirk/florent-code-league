"""Observation encoding and action decoding shared by the RL bot and the training loop.

Per-entity-type action spaces, sized to each type's actual decision complexity (see
NUM_ACTIONS): Builder Bot gets the rich, map-aware observation and the large action
set since it makes the real economy/combat/build decisions; Core/Gunner/Sentinel get
small, cheap observations and action sets since their decisions don't need spatial
context beyond what the engine's own targeting helpers already give them.

Builder Bot build placements are deliberately fixed-direction (harvester: nearest
legal ore tile; gunner/sentinel: always the tile north; conveyor: always the tile
south) so the model only has to decide *whether* and *which facing*, not *where* --
collapsing an otherwise huge placement search into a handful of discrete choices.
This means a build can silently no-op if that fixed tile happens to be blocked
(wall/ore/occupied/off-map); that's an accepted trade-off, not a bug.
"""

from __future__ import annotations

from fcode import Controller, Direction, EntityType, Position

from rl.map_memory import MapMemory

GRID_RADIUS = 3
GRID_SIZE = 2 * GRID_RADIUS + 1  # 7x7 local high-res patch
LOCAL_CHANNELS = 6  # wall, ore, own_building, enemy_building, own_unit, enemy_unit

COARSE_GRID_SIZE = 8
COARSE_CHANNELS = 8  # the 6 above + recency + self-mask

NUM_COMM_SLOTS = 16

ENTITY_TYPES = [
    EntityType.CORE,
    EntityType.BUILDER_BOT,
    EntityType.GUNNER,
    EntityType.SENTINEL,
    EntityType.LAUNCHER,
]

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
ALL_DIRS = [d for d in Direction if d != Direction.CENTRE]  # 8 directions

# -- Builder Bot action layout -------------------------------------------------
# 0: NOOP
# 1-8: MOVE (ALL_DIRS order, but engine only allows cardinal moves -- diagonal
#      move choices are legal actions that simply no-op via can_move())
# 9: BUILD_HARVESTER (nearest legal adjacent ore tile)
# 10-17: BUILD_GUNNER facing ALL_DIRS[0..7], fixed placement north
# 18-25: BUILD_SENTINEL facing ALL_DIRS[0..7], fixed placement north
# 26-29: BUILD_CONVEYOR facing CARDINALS[0..3], fixed placement south
# 30: HEAL (nearest damaged adjacent ally)
# 31: SABOTAGE (fire nearest legal adjacent tile, north preferred)
# 32: SELF_DESTRUCT
# 33: BROADCAST_POS (writes own x,y into comm slots 0,1)
B_NOOP = 0
B_MOVE = list(range(1, 9))
B_BUILD_HARVESTER = 9
B_BUILD_GUNNER = list(range(10, 18))
B_BUILD_SENTINEL = list(range(18, 26))
B_BUILD_CONVEYOR = list(range(26, 30))
B_HEAL = 30
B_SABOTAGE = 31
B_SELF_DESTRUCT = 32
B_BROADCAST_POS = 33
BUILDER_NUM_ACTIONS = 34

# -- Core action layout ---------------------------------------------------------
# 0: NOOP, 1-8: spawn in ALL_DIRS[0..7], 9: BROADCAST_UNIT_COUNT (slot 2)
C_SPAWN = list(range(1, 9))
C_BROADCAST_COUNT = 9
CORE_NUM_ACTIONS = 10

NUM_ACTIONS = {
    EntityType.CORE: CORE_NUM_ACTIONS,
    EntityType.BUILDER_BOT: BUILDER_NUM_ACTIONS,
    EntityType.GUNNER: 4,  # NOOP, FIRE, ROTATE_LEFT, ROTATE_RIGHT
    EntityType.SENTINEL: 2,  # NOOP, FIRE
    EntityType.LAUNCHER: 1,  # NOOP (throwing builder bots is a future extension)
}

# -- Observation sizes ---------------------------------------------------------
# Rich obs (Core, Builder Bot): local patch + coarse map summary + comms + scalars + type one-hot.
_RICH_SCALAR_DIM = 12
RICH_OBS_DIM = (
    GRID_SIZE * GRID_SIZE * LOCAL_CHANNELS
    + COARSE_GRID_SIZE * COARSE_GRID_SIZE * COARSE_CHANNELS
    + NUM_COMM_SLOTS
    + _RICH_SCALAR_DIM
    + len(ENTITY_TYPES)
)
# Light obs (Gunner, Sentinel, Launcher): scalars + comms + type one-hot, no grids --
# these units act on engine-provided targeting helpers, not spatial memory.
_LIGHT_SCALAR_DIM = 6
LIGHT_OBS_DIM = _LIGHT_SCALAR_DIM + NUM_COMM_SLOTS + len(ENTITY_TYPES)

RICH_TYPES = {EntityType.CORE, EntityType.BUILDER_BOT}
OBS_DIM = {t: (RICH_OBS_DIM if t in RICH_TYPES else LIGHT_OBS_DIM) for t in ENTITY_TYPES}


def _entity_type_onehot(etype: EntityType) -> list[float]:
    return [1.0 if etype == t else 0.0 for t in ENTITY_TYPES]


def _read_comms(ct: Controller) -> list[float]:
    return [ct.read_store(i) / 1000.0 for i in range(NUM_COMM_SLOTS)]


def encode_observation(ct: Controller, memory: MapMemory | None) -> list[float]:
    etype = ct.get_entity_type()
    if etype in RICH_TYPES:
        assert memory is not None
        return _encode_rich(ct, memory, etype)
    return _encode_light(ct, etype)


def _encode_rich(ct: Controller, memory: MapMemory, etype: EntityType) -> list[float]:
    memory.update(ct)
    local = memory.local_patch(ct, GRID_RADIUS)
    coarse = memory.coarse_grid(ct, COARSE_GRID_SIZE)
    comms = _read_comms(ct)

    pos = ct.get_position()
    w, h = ct.get_map_width(), ct.get_map_height()
    hp = ct.get_hp()
    max_hp = max(ct.get_max_hp(), 1)
    scalars = [
        pos.x / max(w, 1),
        pos.y / max(h, 1),
        ct.get_current_round() / _max_turns(ct),
        ct.get_global_resources() / 1000.0,
        ct.get_scale_percent() / 100.0,
        ct.get_unit_count() / 50.0,
        hp / max_hp,
        ct.get_action_cooldown() / 4.0,
        ct.get_move_cooldown() / 4.0,
        1.0,  # bias term
        0.0,
        0.0,
    ]
    return local + coarse + comms + scalars + _entity_type_onehot(etype)


def _encode_light(ct: Controller, etype: EntityType) -> list[float]:
    comms = _read_comms(ct)
    hp = ct.get_hp()
    max_hp = max(ct.get_max_hp(), 1)
    is_turret = etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.LAUNCHER)
    has_gunner_target = etype == EntityType.GUNNER and ct.get_gunner_target() is not None
    scalars = [
        hp / max_hp,
        ct.get_action_cooldown() / 4.0,
        (ct.get_ammo_amount() / 20.0) if is_turret else 0.0,
        1.0 if has_gunner_target else 0.0,
        ct.get_current_round() / _max_turns(ct),
        1.0,  # bias term
    ]
    return comms + scalars + _entity_type_onehot(etype)


def _max_turns(ct: Controller) -> float:
    from fcode import GameConstants

    return float(GameConstants.MAX_TURNS)


# -- Action application ---------------------------------------------------------


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
    if action in C_SPAWN:
        d = ALL_DIRS[C_SPAWN.index(action)]
        pos = ct.get_position().add(d)
        if ct.can_spawn(pos):
            ct.spawn_builder(pos)
        return
    if action == C_BROADCAST_COUNT:
        ct.write_store(2, ct.get_unit_count())
        return


def apply_builder_action(ct: Controller, action: int) -> None:
    pos = ct.get_position()

    if action == B_NOOP:
        return

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

    if action in B_BUILD_GUNNER:
        facing = ALL_DIRS[B_BUILD_GUNNER.index(action)]
        target = pos.add(Direction.NORTH)
        if ct.can_build_gunner(target, facing):
            ct.build_gunner(target, facing)
        return

    if action in B_BUILD_SENTINEL:
        facing = ALL_DIRS[B_BUILD_SENTINEL.index(action)]
        target = pos.add(Direction.NORTH)
        if ct.can_build_sentinel(target, facing):
            ct.build_sentinel(target, facing)
        return

    if action in B_BUILD_CONVEYOR:
        facing = CARDINALS[B_BUILD_CONVEYOR.index(action)]
        target = pos.add(Direction.SOUTH)
        if ct.can_build_conveyor(target, facing):
            ct.build_conveyor(target, facing)
        return

    if action == B_HEAL:
        p = _first_adjacent(ct, pos, ct.can_heal)
        if p is not None:
            ct.heal(p)
        return

    if action == B_SABOTAGE:
        # ct.fire() can never target the builder's own tile and can only damage a
        # building, never a unit -- north preferred, else nearest legal cardinal.
        north = pos.add(Direction.NORTH)
        if ct.can_fire(north):
            ct.fire(north)
            return
        p = _first_adjacent(ct, pos, ct.can_fire)
        if p is not None:
            ct.fire(p)
        return

    if action == B_SELF_DESTRUCT:
        ct.self_destruct()
        return

    if action == B_BROADCAST_POS:
        ct.write_store(0, pos.x)
        ct.write_store(1, pos.y)
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
    import math

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
