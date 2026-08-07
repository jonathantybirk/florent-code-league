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


def desired_mix(n_builders: int, hp: int, max_hp: int, burst: int, dhp: float) -> dict:
    """Split `n_builders` across roles.

    `burst` is the worst-case one-round damage from threat.max_burst -- an
    upper bound, deliberately, because this is a survival decision. `dhp` is
    the measured 4-round hp trend, which distinguishes "they are positioned"
    from "they are actually shooting".
    """
    if n_builders <= 0:
        return {ROLE_MINER: 0, ROLE_MENDER: 0, ROLE_GUARD: 0}

    survival = (hp / burst) if burst > 0 else float("inf")

    if survival <= PANIC_ROUNDS:
        menders = max(1, n_builders - 1)
    else:
        menders = 0
        if MEND_ON_ANY_DAMAGE and (hp < max_hp or dhp < 0):
            menders = 1
        if survival <= SECOND_MENDER_ROUNDS and n_builders >= 3:
            menders = 2

    menders = min(menders, n_builders)
    remaining = n_builders - menders

    guards = 0
    if remaining > 0 and n_builders >= 2:
        # Under real pressure a second guard pays: turrets outlast the Builder
        # that placed them, which a mender does not.
        guards = min(remaining, 2 if survival <= SECOND_MENDER_ROUNDS else GUARDS_WHEN_QUIET)

    return {
        ROLE_MENDER: menders,
        ROLE_GUARD: guards,
        ROLE_MINER: remaining - guards,
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
