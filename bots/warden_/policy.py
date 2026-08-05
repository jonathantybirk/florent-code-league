"""Sticky ticket-based mode assignment, plus the v1 reassignment triggers.
Deliberately NOT a per-round "score all 4 modes and pick best" -- see
bots/warden_'s plan notes on herd behavior and thrashing.
"""

from __future__ import annotations

from fcode import Controller

from constants import (
    ECON_IDLE_ROUNDS_BEFORE_SCOUT,
    MAX_OFFENCE_UNITS,
    MAX_PROMOTED_DEFENDERS,
    Mode,
    QUOTA_CYCLE,
    SLOT_BUILDER_TICKET,
    SLOT_DEFENCE_COUNT,
    SLOT_ENEMY_CORE,
    SLOT_OFFENCE_COUNT,
    SLOT_THREAT_LEVEL,
)
from state import BuilderState
from toolbox import read_position


def default_mode_for_ticket(ticket: int) -> Mode:
    return QUOTA_CYCLE[ticket % len(QUOTA_CYCLE)]


def acquire_ticket(ct: Controller, state: BuilderState) -> None:
    """Idempotent: no-op once state.ticket is set.

    Race-free because the Core spawns at most one Builder Bot per round
    (see core.py / toolbox.try_spawn_builder), so at most one new Builder
    reads SLOT_BUILDER_TICKET "cold" in any given round.
    """
    if state.ticket is not None:
        return
    state.ticket = ct.read_store(SLOT_BUILDER_TICKET)
    ct.write_store(SLOT_BUILDER_TICKET, state.ticket + 1)
    state.mode = default_mode_for_ticket(state.ticket)


def _try_join_offence(ct: Controller, state: BuilderState) -> bool:
    """Join OFFENCE if the enemy Core's location is known and there's
    still a free slot, else no-op. One-way -- unlike the DEFENCE
    promotion below, there's no "threat cleared"-equivalent condition
    that should ever pull a Builder back out of an offensive push, so
    this doesn't touch state.promoted at all.

    SLOT_OFFENCE_COUNT is a live-ish census, same accepted-race shape as
    SLOT_DEFENCE_COUNT (see the promotion branch below): several eligible
    Builders can in principle all read count < cap the same round and all
    join, a transient overshoot bounded by that round's eligible
    population. Since nothing here ever decrements it back down (Offence
    never demotes, and a Builder that dies simply stops running -- it
    never gets a chance to self-report that either), an early overshoot
    or a run of losses can leave the census reading higher than the
    truth for the rest of the match, permanently short-circuiting further
    reinforcement. Acceptable for v1: Offence is meant to stay small and
    cheap, not to be topped back up indefinitely.
    """
    if read_position(ct, SLOT_ENEMY_CORE) is None:
        return False
    count = ct.read_store(SLOT_OFFENCE_COUNT)
    if count >= MAX_OFFENCE_UNITS:
        return False
    ct.write_store(SLOT_OFFENCE_COUNT, count + 1)
    state.mode = Mode.OFFENCE
    return True


def maybe_reassign(ct: Controller, state: BuilderState) -> None:
    """Three v1 triggers:

    1. Promote idle ECONOMY builders to DEFENCE while the Core senses a
       threat, demote back once it clears. Only eligible when
       state.ore_target is None (between tasks), so a promotion never
       abandons a claimed ore tile or half-built harvester. Only builders
       this function itself promoted ever demote -- a builder whose
       ticket default is DEFENCE stays put regardless of the flag. Takes
       priority over the two triggers below -- defend home first.

    2. Join OFFENCE once the enemy Core's location is known (see
       _try_join_offence) -- checked for both an ECONOMY builder between
       tasks and a SCOUTING builder (always eligible: it has no
       in-progress task to protect the way a claimed ore tile or
       half-built harvester would be). A Scout that itself just spotted
       the enemy Core is the most common path in here, converting on the
       spot one round later once its own SLOT_ENEMY_CORE write commits,
       rather than reporting home and waiting for some other Builder to
       make the trip.

    3. Reassign an ECONOMY builder to SCOUTING once it's been genuinely
       idle (see state.econ_idle_rounds / modes/economy.py's run()) for
       ECON_IDLE_ROUNDS_BEFORE_SCOUT rounds straight -- ore contention
       near the spawn (several Builders racing for the same few nearby
       tiles) or a map that's just run dry locally otherwise leaves a
       Builder calling explore_randomly forever with nothing to show for
       it. Scouting always has somewhere left to go, and now shares ore
       it finds back too (see modes/scouting.py) -- a real job, not a
       consolation one. Checked last: joining OFFENCE outranks this even
       for a Builder that hasn't been idle long enough to trigger it yet,
       since acting on known enemy Core intel immediately beats waiting
       out a timer first.

    Both (2) and (3) are one-way: neither uses the promoted flag, since
    neither has a "threat cleared"-style condition to revert on.
    """
    if state.ticket is None:
        return
    threatened = ct.read_store(SLOT_THREAT_LEVEL) > 0

    if state.mode == Mode.ECONOMY and not state.promoted:
        if threatened and state.ore_target is None:
            count = ct.read_store(SLOT_DEFENCE_COUNT)
            if count < MAX_PROMOTED_DEFENDERS:
                ct.write_store(SLOT_DEFENCE_COUNT, count + 1)
                state.mode = Mode.DEFENCE
                state.promoted = True
                return
        if state.ore_target is None and _try_join_offence(ct, state):
            return
        if state.econ_idle_rounds >= ECON_IDLE_ROUNDS_BEFORE_SCOUT:
            state.mode = Mode.SCOUTING
        return

    if state.mode == Mode.SCOUTING:
        _try_join_offence(ct, state)
        return

    if state.promoted and not threatened:
        state.mode = default_mode_for_ticket(state.ticket)
        state.promoted = False
        count = ct.read_store(SLOT_DEFENCE_COUNT)
        ct.write_store(SLOT_DEFENCE_COUNT, max(0, count - 1))
