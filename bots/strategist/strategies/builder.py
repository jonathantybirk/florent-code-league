"""Builder Bot strategies.

HarvesterRush and GunnerDefense are a straightforward split of
bots/test/starter/main.py's single _run_builder into two selectable
strategies (policy.select_strategy switches between them using the same
TARGET_HARVESTERS threshold the original inline logic used). SaboteurScout
is new -- modeled on bots/test/tester/main.py's wall-seeking builder, but
retargeted at enemy buildings: Builder Bots can attack an adjacent enemy
building for 2 Ti / 2 damage (see game-rules-builder-bot.txt), which makes
enemy infrastructure a far more useful target than a generic wall.
"""

from __future__ import annotations

import random

from fcode import Controller, Direction, Environment, Position, Team

from state import BotState
from utils import (
    CARDINALS,
    DIRECTIONS,
    SLOT_CORE_X,
    SLOT_CORE_Y,
    SLOT_HARVESTER_COUNT,
    SLOT_ORE_LOCATION,
    in_bounds,
    nearest_cardinal,
    pack_pos,
    unpack_pos,
)

# ----------------------------------------------------------------------
# Shared helpers (used by more than one strategy below)
# ----------------------------------------------------------------------


def _read_core_pos(ct: Controller, state: BotState) -> None:
    if state.core_pos is not None:
        return
    x = ct.read_store(SLOT_CORE_X)
    y = ct.read_store(SLOT_CORE_Y)
    if x > 0 or y > 0:
        state.core_pos = Position(x, y)


def _update_stuck(ct: Controller, state: BotState) -> None:
    pos = ct.get_position()
    if state.last_pos == pos:
        state.stuck += 1
    else:
        state.stuck = 0
    state.last_pos = pos


def _try_build_conveyor_toward_core(ct: Controller, state: BotState, harvester_pos: Position) -> None:
    if state.core_pos is None:
        return
    ti = ct.get_global_resources()
    cost = ct.get_conveyor_cost()
    if ti < cost:
        return
    toward_core = harvester_pos.direction_to(state.core_pos)
    if toward_core == Direction.CENTRE:
        return
    facing = nearest_cardinal(toward_core)
    conv_pos = harvester_pos.add(facing)
    if ct.can_build_conveyor(conv_pos, facing):
        ct.build_conveyor(conv_pos, facing)


def _try_build_harvester(ct: Controller, state: BotState) -> bool:
    ti = ct.get_global_resources()
    cost = ct.get_harvester_cost()
    if ti < cost:
        return False
    pos = ct.get_position()
    for d in Direction:
        build_pos = pos.add(d)
        if ct.can_build_harvester(build_pos):
            ct.build_harvester(build_pos)
            count = ct.read_store(SLOT_HARVESTER_COUNT)
            ct.write_store(SLOT_HARVESTER_COUNT, count + 1)
            _try_build_conveyor_toward_core(ct, state, build_pos)
            state.target = None
            return True
    return False


def _try_build_gunner(ct: Controller, state: BotState) -> bool:
    ti = ct.get_global_resources()
    cost = ct.get_gunner_cost()
    if ti < cost:
        return False
    pos = ct.get_position()
    if state.core_pos is None or pos.distance_squared(state.core_pos) > 18:
        return False
    facing = pos.direction_to(state.core_pos).opposite()
    if facing == Direction.CENTRE:
        facing = random.choice(DIRECTIONS)
    for d in Direction:
        build_pos = pos.add(d)
        if ct.can_build_gunner(build_pos, facing):
            ct.build_gunner(build_pos, facing)
            return True
    return False


def _try_heal(ct: Controller) -> None:
    pos = ct.get_position()
    for d in Direction:
        check = pos.add(d)
        if ct.can_heal(check):
            ct.heal(check)
            return


def _try_move(ct: Controller, state: BotState, d: Direction) -> bool:
    if d == Direction.CENTRE:
        return False
    pos = ct.get_position()
    next_pos = pos.add(d)
    if in_bounds(ct, next_pos) and ct.is_tile_empty(next_pos) and state.core_pos is not None:
        toward_core = next_pos.direction_to(state.core_pos)
        cardinal = nearest_cardinal(toward_core)
        if ct.can_build_conveyor(next_pos, cardinal):
            ct.build_conveyor(next_pos, cardinal)
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


def _move_toward(ct: Controller, state: BotState, target: Position | None) -> None:
    if ct.get_move_cooldown() != 0 or target is None:
        return
    pos = ct.get_position()
    desired = pos.direction_to(target)
    if desired == Direction.CENTRE:
        return
    primary = [desired, desired.rotate_left(), desired.rotate_right()]
    for d in primary:
        if _try_move(ct, state, d):
            return
    remaining = [d for d in DIRECTIONS if d not in primary]
    random.shuffle(remaining)
    for d in remaining:
        if _try_move(ct, state, d):
            return


def _pick_ore_target(ct: Controller) -> Position | None:
    pos = ct.get_position()
    best_ore = None
    best_dist = float("inf")
    for tile in ct.get_nearby_tiles():
        if ct.get_tile_env(tile) != Environment.ORE_TITANIUM:
            continue
        if ct.get_tile_building_id(tile) is not None:
            continue
        d = pos.distance_squared(tile)
        if d < best_dist:
            best_dist = d
            best_ore = tile
    return best_ore


def _share_ore(ct: Controller) -> None:
    for tile in ct.get_nearby_tiles():
        if ct.get_tile_env(tile) == Environment.ORE_TITANIUM:
            if ct.get_tile_building_id(tile) is None:
                ct.write_store(SLOT_ORE_LOCATION, pack_pos(tile))
                return


# ----------------------------------------------------------------------
# Strategies
# ----------------------------------------------------------------------


class HarvesterRush:
    """Build harvesters on ore, route conveyors toward the core, and explore
    for more ore. Ported from bots/test/starter/main.py's _run_builder,
    minus the gunner-building branch (that's GunnerDefense's job now).
    """

    def run(self, ct: Controller, state: BotState) -> None:
        pos = ct.get_position()
        _read_core_pos(ct, state)
        _update_stuck(ct, state)

        if ct.get_action_cooldown() == 0:
            if not _try_build_harvester(ct, state):
                _try_heal(ct)

        if state.target is None or pos == state.target or state.stuck >= 3:
            state.target = self._pick_target(ct)
            state.stuck = 0
        _move_toward(ct, state, state.target)

        _share_ore(ct)

    def _pick_target(self, ct: Controller) -> Position:
        ore = _pick_ore_target(ct)
        if ore is not None:
            return ore
        pos = ct.get_position()
        shared = unpack_pos(ct.read_store(SLOT_ORE_LOCATION))
        if shared is not None and pos.distance_squared(shared) > 4:
            return shared
        w, h = ct.get_map_width(), ct.get_map_height()
        return Position(random.randrange(w), random.randrange(h))


class GunnerDefense:
    """Return to base and place gunner turrets for defense once the economy
    is established. Ported from bots/test/starter/main.py's gunner-building
    branch of _run_builder.
    """

    def run(self, ct: Controller, state: BotState) -> None:
        pos = ct.get_position()
        _read_core_pos(ct, state)
        _update_stuck(ct, state)

        if ct.get_action_cooldown() == 0:
            if not _try_build_gunner(ct, state):
                _try_heal(ct)

        if state.core_pos is not None and pos.distance_squared(state.core_pos) > 8:
            state.target = state.core_pos
        elif state.target is None or pos == state.target or state.stuck >= 3:
            w, h = ct.get_map_width(), ct.get_map_height()
            state.target = Position(random.randrange(w), random.randrange(h))
            state.stuck = 0
        _move_toward(ct, state, state.target)


class SaboteurScout:
    """Seek out and attack the nearest visible enemy building.

    Modeled on bots/test/tester/main.py's wall-seeking builder, retargeted
    at enemy infrastructure -- an actual sabotage strategy, since Builder
    Bots can attack adjacent enemy buildings for 2 Ti / 2 damage.
    """

    def run(self, ct: Controller, state: BotState) -> None:
        pos = ct.get_position()
        my_team = ct.get_team()

        for d in CARDINALS:
            check = pos.add(d)
            if not in_bounds(ct, check):
                continue
            building_id = ct.get_tile_building_id(check)
            if building_id is not None and ct.get_team(building_id) != my_team and ct.can_fire(check):
                ct.fire(check)
                return

        if state.sabotage_target is None or pos == state.sabotage_target:
            state.sabotage_target = self._find_enemy_building(ct, my_team)

        if ct.get_move_cooldown() != 0:
            return

        if state.sabotage_target is None:
            dirs = list(DIRECTIONS)
            random.shuffle(dirs)
            for d in dirs:
                if ct.can_move(d):
                    ct.move(d)
                    return
            return

        move_dir = pos.cardinal_direction_to(state.sabotage_target)
        if move_dir != Direction.CENTRE and ct.can_move(move_dir):
            ct.move(move_dir)

    def _find_enemy_building(self, ct: Controller, my_team: Team) -> Position | None:
        pos = ct.get_position()
        best = None
        best_dist = float("inf")
        for building_id in ct.get_nearby_buildings():
            if ct.get_team(building_id) == my_team:
                continue
            b_pos = ct.get_position(building_id)
            d = pos.distance_squared(b_pos)
            if d < best_dist:
                best_dist = d
                best = b_pos
        return best
