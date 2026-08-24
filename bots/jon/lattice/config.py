"""Every tunable in the bot, in one file.

The rule for this directory: **no other module may contain a bare number that
encodes a decision.** Engine facts (costs, damage, cooldowns) are read from
`GameConstants` at runtime and never copied here; what lives here is only the
policy we chose on top of them. Retuning the bot for a new meta should mean
editing this file, or swapping one behaviour module, and nothing else.

Each block records *why* the value is what it is, so that a later session can
tell a measured constant from a guess. Anything marked GUESS has not been swept.
"""

# ---------------------------------------------------------------------------
# Win condition
# ---------------------------------------------------------------------------
# Killing a 500 HP Core costs ~280 Ti of ammunition whichever turret does it
# (500/18 = 27.8 Sentinel shots x 10 ammo; 500/7 = 71.4 Gunner shots x 4).
# A Builder heals 4 HP for 1 Ti, so defence buys 4 HP/Ti against offence's 1.8 --
# a 2.2x edge that makes a tended Core close to unkillable. So the default plan
# is to win the round-1000 tiebreak on titanium *collected*, and take a Core kill
# only when it is actually available.
PLAY_FOR_TIEBREAK = True

# Only stacks that physically land on a Core tile count toward `titanium_collected`;
# passive income does not. Delivery, not mining, is the scoreboard.

# ---------------------------------------------------------------------------
# Opening
# ---------------------------------------------------------------------------
# A Builder is +20% cost scale for as long as it lives, and the scale is a live
# census of everything we own. Three is the inherited figure from the warden line
# and is not re-derived here; the fourth Builder taxes the Harvesters and turrets
# the opening has not bought yet.
OPENING_BUILDERS = 3

# Past the opening the same +20% falls mostly on 3 Ti conveyors (0.6 Ti a tile)
# while every Harvester it connects returns 2.5 Ti/round for the rest of the
# match, so late headcount is cheap in a way opening headcount is not.
INCOME_BUILDER_ROUND = 200
INCOME_BUILDER_MAX = 3
INCOME_BUILDER_BANK = 120          # only add one while we are visibly cash-rich

# Spawn replacements whenever we drop below the opening count -- a team that
# loses two of three Builders mines into a bank nothing is left to spend.
REPLACE_LOST_BUILDERS = True

# ---------------------------------------------------------------------------
# Economy
# ---------------------------------------------------------------------------
# A conveyor holds one stack and advances it one tile per round, so a single
# trunk carries at most one stack/round. A Harvester emits one stack per 4
# rounds, so four Harvesters saturate a trunk. Past that, stacks jam and the
# fifth Harvester is dead titanium.
HARVESTERS_PER_TRUNK = 4

# Distance beyond which an ore tile is not worth a trunk of its own. A Harvester
# at path distance d costs 20 + 3d and returns 2.5 Ti/round, so payback is
# (20+3d)/2.5 rounds: d=10 pays back in 20 rounds, d=25 in 38. Both are fine in a
# 1000-round game; the real limit is that a long trunk is more to defend.
MAX_TRUNK_LENGTH = 18

# Stop laying new economy once we are this far ahead on delivered titanium and
# the round is late -- extra conveyors are +1% each and give the enemy targets.
ECON_SOFT_CAP_ROUND = 800

# ---------------------------------------------------------------------------
# Defence
# ---------------------------------------------------------------------------
# Healing is flat-priced (1 Ti for 4 HP) and immune to cost scale, which makes it
# the cheapest titanium in the game. One mender absorbs two thirds of a Sentinel.
MENDER_MIN_DAMAGE = 4              # one heal is 4 HP; below that the action is wasted
CORE_ALARM_HP_FRACTION = 0.90      # below this, the Core is "under attack"

# Answer an enemy Builder on *sighting* near home rather than after the Core has
# already lost HP: their attack is usually one Builder, and their Core will not
# replace it while any of their Builders lives.
GUARD_RADIUS_SQ = 36
GUARD_CHASE_RADIUS_SQ = 25
# A Sentinel reaches r^2=32 (5.7 tiles), so an enemy turret seated within this
# of our Core is already shooting it, or one rotation away from doing so.
GUARD_TURRET_RADIUS_SQ = 64

# ---------------------------------------------------------------------------
# Siege
# ---------------------------------------------------------------------------
# Under 2.3.4 the Gunner and the Sentinel carry the same +20% scale, and the
# Sentinel wins every other row: 6.0 dmg/round against 3.5, 40 HP against 25,
# r^2=32 against 13, 1.80 dmg/ammo against 1.75, and a line nothing blocks. The
# Gunner's only remaining edge is 10 Ti of build cost and the ability to rotate.
PREFER_SENTINEL = True

# Turrets are +20% each, so the count is capped by the tax rather than by cash.
MAX_SIEGE_TURRETS = 2
MAX_GUARD_TURRETS = 1

# Do not seat a turret where an enemy turret already covers the tile; a Sentinel
# that loses the opening exchange is 30 Ti and 20% of scale for nothing.
AVOID_COVERED_SEATS = True

# Shoot the supply line, never the turrets: destroying an enemy turret refunds
# its +20% and makes everything they build cheaper for the rest of the match.
TARGET_SUPPLY_NOT_TURRETS = True

# ---------------------------------------------------------------------------
# Ammunition
# ---------------------------------------------------------------------------
# convert_ammo is 1:1, flat-priced, once per team per turn, and usable the same
# turn. A team that cannot shoot loses faster than one that cannot build, so a
# floor is kept -- but the floor must not eat the construction reserve, which is
# what starves the opening economy.
AMMO_FLOOR = 20
AMMO_TOPUP = 40
AMMO_RESERVE_ROUND = 30            # before this, building matters more

# ---------------------------------------------------------------------------
# Behaviour ceilings
# ---------------------------------------------------------------------------
# Every behaviour reports a score strictly below its ceiling, and the kernel
# evaluates them in descending ceiling order, stopping as soon as the best score
# so far cannot be beaten. Reordering priorities is an edit to this table alone.
CEILINGS = {
    "guard": 9.0,      # an enemy is on our doorstep
    "mend": 8.0,       # something of ours is damaged
    "siege": 7.0,      # seat a turret that shoots their economy
    "route": 6.0,      # connect a Harvester to the Core
    "harvest": 5.0,    # put a Harvester on secured ore
    "secure": 4.0,     # deny the tiles around our ore
    "explore": 1.0,    # nothing better to do
}

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
# 10 ms per unit per round, with a 5% banked buffer. Perception is rebuilt each
# turn, so the budget is checked before any optional work.
CPU_BUDGET_US = 10_000
CPU_SAFE_US = 6_500                # stop starting optional work past this
