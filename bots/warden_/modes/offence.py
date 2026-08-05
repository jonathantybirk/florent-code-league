"""OFFENCE mode: push toward the enemy Core once its location is known,
sabotage whatever enemy infrastructure is in reach along the way, and
seat one forward Gunner near the enemy Core to keep pressure on after
this Builder is inevitably lost.

Assignment is entirely reactive -- see policy.py's _try_join_offence --
there is no ticket-default path into this mode at all (QUOTA_CYCLE has
no OFFENCE entry): a Builder only ever arrives here once the team
actually knows where to go, capped at MAX_OFFENCE_UNITS. This mode does
not try to win the game by itself; it is priced as harassment (deny
resources, force the opponent to spend Builder-rounds and titanium on
cleanup) rather than a siege that expects to bring the enemy Core down
alone -- see bots/test/luc/vidar's README for why that expectation
would be unrealistic against a competently defended Core under the
current turret balance (defence is titanium-efficient there; see the
research this bot's own defence.py cites).

A Builder Bot can never fight an enemy unit directly -- ct.fire() only
ever damages a building on an adjacent tile (see
docs/official/docs/game-rules-builder-bot.txt) -- so try_sabotage_adjacent
(shared with modes/defence.py, now in toolbox.py) is the only direct
damage this mode ever deals itself; the seated Gunner does the rest,
auto-firing independently once placed (see main.py's GUNNER branch).

If SLOT_ENEMY_CORE is ever unset by the time this runs (shouldn't happen
-- see policy.py's promotion gate -- but nothing guarantees the store
write this depends on can't be reasoned about wrong somewhere), falls
back to ECONOMY rather than stranding the unit, same fallback role it
plays for every other mode via main.py's own exception handler.
"""

from __future__ import annotations

from fcode import Controller, Position

from constants import (
    MAX_OFFENCE_TURRETS_NEAR_ENEMY,
    OFFENCE_ENGAGE_RADIUS_SQ,
    SLOT_ENEMY_CORE,
    STUCK_THRESHOLD,
)
from state import BuilderState
from toolbox import (
    count_nearby_friendly_turrets,
    explore_randomly,
    read_position,
    try_build_gunner_facing,
    try_move_toward,
    try_sabotage_adjacent,
)

from . import economy


def run(ct: Controller, state: BuilderState) -> None:
    target = read_position(ct, SLOT_ENEMY_CORE)
    if target is None:
        economy.run(ct, state)
        return

    if ct.get_action_cooldown() == 0:
        try_sabotage_adjacent(ct)

    pos = ct.get_position()
    state.stuck.update(pos)

    if pos.distance_squared(target) <= OFFENCE_ENGAGE_RADIUS_SQ:
        _try_seat_forward_gunner(ct, pos, target)
        # Close enough to do useful work standing still (sabotage,
        # holding a firing angle for the Gunner once it's up) -- no
        # further movement needed this round.
        return

    if state.stuck.stuck_rounds >= STUCK_THRESHOLD:
        # Blocked on the direct approach (enemy walls/turrets/terrain).
        # The enemy Core never moves, so there's no target to re-pick
        # the way Economy or Scouting would -- just route around
        # whatever's in the way and keep trying toward the same target.
        explore_randomly(ct)
        return

    if not try_move_toward(ct, target):
        explore_randomly(ct)


def _try_seat_forward_gunner(ct: Controller, pos: Position, target: Position) -> Position | None:
    """Build one Gunner facing the enemy Core, if the local garrison
    isn't already up to MAX_OFFENCE_TURRETS_NEAR_ENEMY. A single forward
    turret is a nuisance the enemy has to spend a turret or a few
    Builder-rounds clearing; more than that is titanium this Builder
    will not live to spend twice.
    """
    if count_nearby_friendly_turrets(ct, OFFENCE_ENGAGE_RADIUS_SQ) >= MAX_OFFENCE_TURRETS_NEAR_ENEMY:
        return None
    facing = pos.direction_to(target)
    return try_build_gunner_facing(ct, facing, near=target, max_dist_sq=OFFENCE_ENGAGE_RADIUS_SQ)
