"""Core logic: spawn Builder Bots, keep ammo topped up, and broadcast a
decaying home-threat signal (plus where it's coming from) that
policy.maybe_reassign() and modes/defence.py react to.
"""

from __future__ import annotations

from fcode import Controller

from constants import (
    AMMO_CHUNK,
    AMMO_TARGET,
    BUILDER_SPAWN_COOLDOWN_ROUNDS,
    CORE_THREAT_VISION_SQ,
    MAX_TOTAL_BUILDERS,
    SLOT_THREAT_LEVEL,
    SLOT_THREAT_POS,
    THREAT_DECAY_ROUNDS,
)
from state import BuilderState
from toolbox import maintain_ammo, try_spawn_builder, write_position


def _update_threat_level(ct: Controller) -> None:
    """Broadcast both *that* a threat was seen (decaying flag, unchanged)
    and *where* the nearest one was -- the Core's own vision (r^2=36) is
    much wider than any one defender's, and without a position a
    defender can only react to whatever it happens to see itself, which
    is often nothing until the threat is already on top of the Core.
    """
    my_team = ct.get_team()
    pos = ct.get_position()
    nearest = None
    nearest_dist = None
    for uid in ct.get_nearby_units(dist_sq=CORE_THREAT_VISION_SQ):
        if ct.get_team(uid) == my_team:
            continue
        d = pos.distance_squared(ct.get_position(uid))
        if nearest_dist is None or d < nearest_dist:
            nearest, nearest_dist = ct.get_position(uid), d
    if nearest is not None:
        ct.write_store(SLOT_THREAT_LEVEL, THREAT_DECAY_ROUNDS)
        write_position(ct, SLOT_THREAT_POS, nearest)
    else:
        level = ct.read_store(SLOT_THREAT_LEVEL)
        ct.write_store(SLOT_THREAT_LEVEL, max(0, level - 1))


def run(ct: Controller, state: BuilderState) -> None:
    _update_threat_level(ct)
    maintain_ammo(ct, AMMO_TARGET, AMMO_CHUNK)

    # try_spawn_builder already checks affordability via can_spawn; this
    # cap is about not overrunning the team's unit budget (50, shared with
    # turrets and the Core itself). get_unit_count() reflects who's alive
    # *right now* -- a cumulative spawn counter would stop replacing
    # combat losses forever once it once hit the cap, permanently
    # shrinking the economy for the rest of a long match even though the
    # team cap has room again.
    #
    # The cooldown is separate from affordability: early on the Core can
    # usually afford several Builders back to back, which just bursts out
    # a cluster racing for whatever ore is nearest the spawn -- only one
    # can claim each tile, so most of that burst starts out idle. Pacing
    # spawns gives each one time to disperse and find its own ore (or
    # give up and reassign, see ECON_IDLE_ROUNDS_BEFORE_SCOUT) before the
    # next one shows up.
    round_now = ct.get_current_round()
    if (
        ct.get_unit_count() < MAX_TOTAL_BUILDERS
        and round_now - state.last_spawn_round >= BUILDER_SPAWN_COOLDOWN_ROUNDS
    ):
        if try_spawn_builder(ct) is not None:
            state.last_spawn_round = round_now
