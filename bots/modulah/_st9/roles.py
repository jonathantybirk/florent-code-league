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
ROLE_SIEGE = 3

NAMES = {ROLE_MINER: "miner", ROLE_MENDER: "mender", ROLE_GUARD: "guard",
         ROLE_SIEGE: "siege"}

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

# Builders held on the economy until this many Harvesters are working, no
# matter what is happening -- see the floor in desired_mix.
ECON_FLOOR_HARVESTERS = 4

# Builders sent to besiege the enemy Core once the economy is standing, and
# the round from which it is worth starting. We out-collect steward and still
# lose every game, because it wins ~90% of its matches on a Core kill and we
# have never attacked anything -- surviving a Core-killer is the harder half.
SIEGE_BUILDERS = 0
SIEGE_FROM_ROUND = 60
SIEGE_MIN_HARVESTERS = 2

# Titanium per extra standing guard while unthreatened. A Gunner is 20 base
# plus cost scale, so this is several turrets' worth of slack before another
# Builder is pulled off the economy.
RICH_PER_GUARD = 250


def desired_mix(
    n_builders: int,
    hp: int,
    max_hp: int,
    burst: int,
    dhp: float,
    friendly_turrets: int = 0,
    harvesters: int = 0,
    titanium: int = 0,
    round_no: int = 0,
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
        # Enough to cover the bleed, and no more -- but never the whole team.
        # Matching the bleed exactly with every Builder is a stalemate that
        # builds nothing while the enemy keeps adding turrets; someone has to
        # be removing the source. Traced: 4 Builders against a 16/round rush
        # all read MENDER and no turret was ever placed.
        menders = min(
            n_builders - 1 if n_builders > 1 else n_builders,
            int((incoming + HEAL_AMOUNT - 1) // HEAL_AMOUNT),
        )
    else:
        # Cannot keep up. One Builder buys time; the rest must remove the
        # source, because a turret keeps working after its builder dies.
        menders = 1 if n_builders > 1 else 0

    # Economy floor. Income is the precondition for defence, not a competitor
    # with it: turrets, ammo and replacement Builders are all bought with
    # titanium, so a team with no Harvester cannot defend itself either.
    #
    # Without this, early harassment (dhp < 0 from round ~10) turned both
    # opening Builders into a mender and a guard and left nobody mining. First
    # Harvester slipped to round 30 against the field's 6.5, harvesters-at-100
    # fell 2.29 -> 0.92, and titanium collected more than halved -- while the
    # defensive numbers improved. It bought the wrong thing.
    #
    # Suspended only when the Core is genuinely about to die, where there is
    # no later economy to protect.
    survival = (hp / burst) if burst > 0 else float("inf")
    floor = 0 if survival <= PANIC_ROUNDS else min(
        n_builders, max(0, ECON_FLOOR_HARVESTERS - harvesters)
    )
    if floor:
        menders = min(menders, max(0, n_builders - floor))

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
            # A quiet game with a full treasury should be turning titanium
            # into turrets, not banking it. Earlier builds sat on 400+ while
            # the Core died. Scale the guard count with what we can actually
            # spend, so a strong economy becomes a strong defence instead of
            # a bigger number.
            rich = max(0, titanium // RICH_PER_GUARD)
            guards = min(remaining, max(GUARDS_WHEN_QUIET, rich))

    if floor:
        guards = min(guards, max(0, remaining - floor))

    siege = 0
    left = max(0, remaining - guards)
    if (round_no >= SIEGE_FROM_ROUND
            and harvesters >= SIEGE_MIN_HARVESTERS
            and incoming <= 0
            and left > 1):
        siege = min(SIEGE_BUILDERS, left - 1)

    return {
        ROLE_MENDER: menders,
        ROLE_GUARD: guards,
        ROLE_SIEGE: siege,
        ROLE_MINER: max(0, left - siege),
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
    if rank < mix[ROLE_MENDER] + mix[ROLE_GUARD] + mix.get(ROLE_SIEGE, 0):
        return ROLE_SIEGE
    return ROLE_MINER
