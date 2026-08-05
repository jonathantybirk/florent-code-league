"""SCOUTING mode: head for likely enemy territory using map symmetry,
reporting enemy sightings (the enemy Core specifically, when seen, since
that's what modes/offence.py needs) and any ore it passes along the way.

Maps are symmetric (docs/official/docs/game-rules-overview.txt), so a
180-degree rotation and the two axis reflections of our own Core position
are real candidates for the enemy Core's location, not a guess. This
stays bot-local rather than living in toolbox.py, which is meant to be
map-topology-agnostic.

Ore sharing (share_ore into SLOT_ORE_SHARE) matters here specifically:
Economy builders only ever search their own vision and fall back to
whatever's in that slot, so ore sitting outside the routes an Economy
builder actually walks -- exactly the ground a Scout covers that nobody
else does -- would otherwise never get discovered at all.

Spotting the enemy Core (SLOT_ENEMY_CORE, distinct from the generic
SLOT_ENEMY_SIGHTING) is what lets policy.maybe_reassign() start Offence
at all -- see its docstring for why the Scout that finds it is usually
the one that goes on to use it, one round later once the write commits.
"""

from __future__ import annotations

from fcode import Controller, EntityType, Position

from constants import (
    SCOUT_ARRIVAL_DIST_SQ,
    SLOT_ENEMY_CORE,
    SLOT_ENEMY_SIGHTING,
    SLOT_ORE_SHARE,
    STUCK_THRESHOLD,
)
from state import BuilderState
from toolbox import explore_randomly, share_ore, try_move_toward, write_position


def _symmetry_candidates(core_pos: Position, map_w: int, map_h: int) -> list[Position]:
    """180-degree rotation and axis reflections of core_pos, farthest from
    core_pos first -- the rotation candidate is usually the true enemy
    Core on a point-symmetric map, but visiting farthest-first means a
    wrong guess still covers the most unexplored ground early.
    """
    rotated = Position(map_w - 1 - core_pos.x, map_h - 1 - core_pos.y)
    mirror_x = Position(map_w - 1 - core_pos.x, core_pos.y)
    mirror_y = Position(core_pos.x, map_h - 1 - core_pos.y)
    candidates = [rotated, mirror_x, mirror_y]
    candidates.sort(key=lambda p: -core_pos.distance_squared(p))
    return candidates


def _next_scout_target(ct: Controller, state: BuilderState) -> Position | None:
    if state.core_pos is None:
        return None
    candidates = _symmetry_candidates(state.core_pos, ct.get_map_width(), ct.get_map_height())
    return candidates[state.scout_cycle % len(candidates)]


def _report_sighting(ct: Controller) -> None:
    """Report the first enemy Core seen (the valuable, permanent
    sighting Offence needs) in preference to any other enemy entity
    (a merely informational, frequently-stale one) -- a Core sighting
    always wins if both are visible the same round, since it's strictly
    more useful and there's only one report to spend this round anyway.
    """
    my_team = ct.get_team()
    fallback = None
    for uid in ct.get_nearby_entities():
        if ct.get_team(uid) == my_team:
            continue
        pos = ct.get_position(uid)
        if ct.get_entity_type(uid) == EntityType.CORE:
            write_position(ct, SLOT_ENEMY_CORE, pos)
            ct.draw_indicator_dot(pos, 255, 0, 0)
            return
        if fallback is None:
            fallback = pos
    if fallback is not None:
        write_position(ct, SLOT_ENEMY_SIGHTING, fallback)
        ct.draw_indicator_dot(fallback, 255, 0, 0)


def run(ct: Controller, state: BuilderState) -> None:
    _report_sighting(ct)
    share_ore(ct, SLOT_ORE_SHARE)

    if state.scout_target is None:
        state.scout_target = _next_scout_target(ct, state)

    pos = ct.get_position()
    state.stuck.update(pos)

    if state.scout_target is None:
        explore_randomly(ct)
        return

    arrived = pos.distance_squared(state.scout_target) <= SCOUT_ARRIVAL_DIST_SQ
    if arrived:
        state.scout_cycle += 1
        state.scout_target = _next_scout_target(ct, state)
    elif state.stuck.stuck_rounds >= STUCK_THRESHOLD:
        state.scout_cycle += 1
        state.scout_target = _next_scout_target(ct, state)
        state.stuck.stuck_rounds = 0
    elif not try_move_toward(ct, state.scout_target):
        explore_randomly(ct)
