# GENERATED from bots/modulah/lib/roles.py -- edit that file, not this copy.
"""How many Builders should be doing what, given what the Core can see.

Pure policy: no Controller, no side effects, so it can be reasoned about and
tested without a match. The bot decides *how* to mine or mend; this decides
*how many*.

Two findings from the steward lineage's measurement log drive the shape here,
and both are about mending rather than economy:

  * mending on ANY damage, rather than on an hp threshold, was worth +11.0pp
    mean and +16.6pp floor -- the single largest measured change in that bot;
  * a second mender on top of that was worth a further +1.4pp.

The reason a threshold loses is timing. By the time a Core is at 60% it has
already taken 200 damage, and HEAL_AMOUNT is 4 -- a mender claws back 4 hp a
round, so it needs to already be standing there. Reacting to the first hit
buys the fifty rounds that reacting to a threshold does not.

The counterweight is that a mender standing on the Core is a Builder not
mining, and steward's own log records extra miners measuring negative every
time they were tried: 90% of its games end in a Core kill rather than the
round-1000 tiebreak, so economy funds pressure rather than winning on its own.
Hence a mix that leans defensive under fire and only mildly economic when
quiet.
"""

from __future__ import annotations

from fcode import GameConstants

HEAL_AMOUNT = GameConstants.HEAL_AMOUNT

ROLE_MINER = 0
ROLE_MENDER = 1
ROLE_GUARD = 2

NAMES = {ROLE_MINER: "miner", ROLE_MENDER: "mender", ROLE_GUARD: "guard"}

# A Core that has taken any damage at all gets a mender. Not a fraction of max
# hp -- see the module docstring for why a threshold reacts too late.
MEND_ON_ANY_DAMAGE = True

# Second mender once the situation is genuinely bad rather than merely
# scratched. Expressed in rounds-of-survival against the current worst case,
# so it scales with how hard they are actually hitting rather than with a flat
# hp number that means different things at different stages.
SECOND_MENDER_ROUNDS = 25

# Below this, everything that can mend, mends. Losing the Core loses the game
# outright; nothing else on the board is worth a Builder's turn at this point.
PANIC_ROUNDS = 8

# One Builder is kept siting turrets while the game is quiet. Turrets are the
# cheapest permanent answer to pressure, and unlike a mender they keep working
# when the Builder that placed them dies.
GUARDS_WHEN_QUIET = 1


def desired_mix(
    n_builders: int,
    hp: int,
    max_hp: int,
    burst: int,
    dhp: float,
    friendly_turrets: int = 0,
) -> dict:
    """Split `n_builders` across roles.

    `burst` is the worst-case one-round damage from threat.max_burst -- an
    upper bound, deliberately, because this is a survival decision. `dhp` is
    the measured 4-round hp trend, which distinguishes "they are positioned"
    from "they are actually shooting".
    """
    if n_builders <= 0:
        return {ROLE_MINER: 0, ROLE_MENDER: 0, ROLE_GUARD: 0}

    # Measured loss rate, not the worst case. `burst` is an upper bound that
    # ignores enemy ammo and cooldowns, so sizing the mender count off it
    # panics at turrets that are merely pointed at us. dhp is what is actually
    # happening.
    incoming = max(0.0, -dhp)

    # A mender restores HEAL_AMOUNT per round. So mending is worth a Builder's
    # turn only while enough menders could actually stem the loss -- past that
    # they are standing on the Core watching it die at almost the same rate.
    #
    # This is the correction that mattered: against a 21-burst rush with two
    # Builders, the old policy put BOTH on mending (4 hp/round each) and never
    # built a turret, because guards required n_builders >= 2 after menders
    # were taken. Core went 500 -> 42 by round 56 with 400 titanium unspent.
    can_out_heal = incoming <= n_builders * HEAL_AMOUNT

    if incoming <= 0:
        menders = 0
    elif can_out_heal:
        # Enough to cover the bleed, and no more.
        menders = min(n_builders, int((incoming + HEAL_AMOUNT - 1) // HEAL_AMOUNT))
    else:
        # Cannot keep up. One Builder buys time; the rest must remove the
        # source, because a turret keeps working after its builder dies.
        menders = 1 if n_builders > 1 else 0

    remaining = n_builders - menders

    # The FIRST turret is the highest-value build on the board when something
    # is shooting us and we have none -- it is the only thing that makes the
    # damage stop rather than slowing it down. It is not gated on Builder
    # count, because a lone Builder mending into a rush loses the Core.
    guards = 0
    if remaining > 0:
        if incoming > 0 and friendly_turrets == 0:
            guards = 1
        elif incoming > 0:
            guards = min(remaining, 2)
        else:
            guards = min(remaining, GUARDS_WHEN_QUIET)

    return {
        ROLE_MENDER: menders,
        ROLE_GUARD: guards,
        ROLE_MINER: max(0, remaining - guards),
    }


def assign(rank: int, mix: dict) -> int:
    """Which role the Builder at `rank` takes.

    Menders first, then guards, then miners. Ordering by a stable rank rather
    than by who asks first means every Builder derives the same assignment
    from the same snapshot, so two cannot both decide they are the only mender
    -- the store is a round behind, so they cannot coordinate by talking.
    """
    if rank < mix[ROLE_MENDER]:
        return ROLE_MENDER
    if rank < mix[ROLE_MENDER] + mix[ROLE_GUARD]:
        return ROLE_GUARD
    return ROLE_MINER
