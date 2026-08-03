"""Shared constants and communication layout for Jonbot."""

from fcode import Direction, EntityType

D8 = tuple(d for d in Direction if d != Direction.CENTRE)
D4_DELTAS = ((0, -1), (1, 0), (0, 1), (-1, 0))
FACING = dict(zip(D4_DELTAS, (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)))
WALKABLE_BUILDINGS = (EntityType.CONVEYOR, EntityType.SPLITTER)

# One Builder per job: mine, defend, attack. Every Builder Bot adds +20% to
# every build cost the team will ever pay -- the largest single term in cost
# scaling -- so a spare Builder is not free labour, it is a permanent tax on
# the Launchers and Harvesters it was spawned to help build. Six of them took
# the Launcher price from 20 Ti to 44 before the first one went up.
# That tax is also why the doctrine in doctrine.py reallocates these three
# rather than adding a fourth: which of them mines and which attacks is free
# to vary with the map, how many there are is not. Both doctrines put the
# Launcher-ring Builder last, so this index and the total hold either way.
LAUNCHER_BUILDERS = 1
LAUNCHER_BUILDER_INDEX = 2
MAX_OPENING_BUILDERS = LAUNCHER_BUILDER_INDEX + LAUNCHER_BUILDERS

# Spawn the Launcher-ring Builder first instead of last, so the throw pad
# exists before the attacker needs it.
#
# MEASURED AND OFF. The reasoning was that ragnarok documents its ring as "a
# throw pad for the ferry" and then spawns the builder for it third, so the pad
# lands around round 6 while the attacker, spawned on round 1, has already
# started building its own Launcher to escape from. Pantheon (#1) pulls exactly
# this lever: Launcher on round 1, throwing from round 2.
#
# It costs 25 games out of 252. Scored against the six-bot ablation panel over
# the whole map pool in both seats, ragnarok and this bot with the flag off both
# take 209/252; with it on, 184/252.
#
# The reason is in the economy columns, not the combat ones: putting the pad
# first pushes the miner from spawn index 0 to index 2, which moves the first
# Harvester from round 7 to round 9 and drops delivered titanium from 696 to
# 470 -- a third of the economy, every game, to buy a pad a few rounds earlier.
# Tempo bought with the opening Harvester is not tempo, it is a loan.
PAD_FIRST_ORDER = False
# Ring Launchers one Builder will put up, out of the eight compass sites.
#
# The same shape as MAX_RELAY_LAUNCHERS and for the same reason: a Launcher is
# +10% on every price the team pays thereafter, so the ring is a scale bill as
# much as a screen. Measured on the warden_walk chassis over the 21 official
# maps in both seats, as maps won 2-0 against the two Nash-core agents:
#
#   cap 8 (all of it)   6 vs ragnarok, 6 vs vigil   worst 29%
#   cap 3               6, 6                        worst 29%
#   cap 2               7, 7                        worst 33%   <- shipped
#   cap 1               7, 5                        worst 24%
#
# Two is the pad plus one more approach. Below that the screen stops covering
# anything; above it the extra sites are bought with the Gunners and Harvesters
# that would otherwise have been built.
RING_MAX_SITES = 2

# Ferry toward the symmetry inference's committed guess as well as toward a
# Core a unit has actually seen.
#
# This has now been measured three times on three different bots and the answer
# has changed twice, which is the whole lesson: a flag measured on a chassis is
# not measured for the chassis it becomes.
#
#   atlas-carrying ancestors            17/42 on  against 21/42 off   -> OFF
#   this bot, before the home guard    128/168 on against 119/168 off -> ON
#   this bot, as it now stands         282/336 off against 271/336 on -> OFF
#
# The third measurement is the one that matters and it is not close. Full
# 8-bot pool, 21 official maps both seats, and 40 generated maps:
#
#                    pool            generated
#     ferry on     271/336  0.807    109/160  0.681
#     ferry off    282/336  0.839    115/160  0.719
#
# Per opponent the gain is concentrated exactly where this bot was weakest:
# warden_walk 26/42 -> 32/42, warden 32 -> 34, ragnarok 30 -> 33.
#
# The reason is recorded further up this file and was found long before this
# bot existed: `ragnarok_fair` beats `valkyrie` where `ragnarok` only draws,
# because the atlas-free twin *cannot* ferry and is therefore forced to walk --
# and the walking bot ends with more Gunners and Harvesters where the chaining
# one ends with more Launchers. Every Launcher is +10% on every price the team
# pays thereafter. Committing the attacker to a guessed Core buys tempo and
# pays for it in the only two things that win.
FERRY_ON_INFERENCE = False

# Drop a ring direction when the map edge is this close behind it: nothing can
# approach from off the map, so a Launcher there guards nothing and still costs
# its +10%.
RING_EDGE_MARGIN = 5
# Tiles between the Core footprint and the ring. Launchers block movement, so
# at radius 1 the ring sits on the tiles a conveyor line has to cross to reach
# the Core. Radius 2 leaves that lane open, and a Builder standing on the shell
# between the two is still diagonally adjacent to the ring site, so it remains
# inside the Launcher's pickup radius.
RING_RADIUS = 2

# --- Core seal -------------------------------------------------------------
# A Gunner's attack radius squared. Any tile this close to the Core footprint
# is a tile an enemy turret could shoot the Core from, so the seal has to keep
# enemy Builders out of it -- and out of the shell around it too, since a
# Builder builds onto an orthogonally adjacent tile rather than its own.
CORE_THREAT_RADIUS_SQ = 13
# Barriers are 3 Ti base and +1% scale, against a Launcher's 20 Ti and +10%,
# and they block line of sight as well as movement. They are the only building
# cheap enough to run a closed perimeter out of.
SEAL_TITANIUM_RESERVE = 25

# --- Turret meta -----------------------------------------------------------
# Rounds a Gunner must go without seeing any enemy at all before it removes
# itself. Long, deliberately: standing down is irreversible, and a turret that
# has been quiet for a while is not the same as one that will stay quiet.
TURRET_QUIET_ROUNDS = 60
# Turrets within this of our Core never stand down whatever they have seen.
# They are insurance, and the round they are needed is too late to rebuild.
HOME_GUARD_RADIUS_SQ = 36
# Rotation costs a flat 10 Ti. Hold back more than that so a turret turning to
# face a scout cannot spend the titanium a Harvester was waiting on.
ROTATE_TITANIUM_RESERVE = 40
# --- Home guard -------------------------------------------------------------
# How close to our own Core footprint an enemy has to come before the Builder
# already standing there answers it with a turret, rather than waiting for the
# Core to lose 50 HP and raise the damage alarm. Measured on the 21 official
# maps in both seats against valkyrie, vigil, ragnarok and vanguard:
#
#   off      118/168
#   r^2 64   142/168
#   r^2 36   145/168
#
# ...on the chassis of the day. Re-measured after the opening ferry was turned
# off, on the full 8-bot pool and 40 generated maps, the order reverses:
#
#                 pool            generated
#     r^2 25    (worse)           --
#     r^2 36    282/336  0.839    115/160  0.719
#     r^2 64    288/336  0.857    117/160  0.731   <- shipped
#     r^2 81    287/336  0.854    (worse)
#     r^2 100   287/336  0.854
#
# Which follows: with no ferry the attacker walks, so enemy attackers arrive on
# foot and are in sight for longer before they emplace, and eight tiles of
# warning is now worth what six was when both sides were being thrown across
# the map. Past r^2 64 it starts paying turrets for scouts again.
GUARD_RADIUS_SQ = 64
# Turrets this Builder will put up for that job.
#
# This is the one constant chosen to maximise the *worst* matchup rather than
# the total, because that is what the goal asks for. On the full 8-bot pool,
# with the ferry off and the chase at six:
#
#     cap 2   294/336  0.875   but warden_walk 32/42 = 0.76
#     cap 3   291/336  0.866   but warden_walk 33/42 = 0.79
#     cap 4   290/336  0.863   and every opponent >= 0.81
#
# Four games of total buy the minimum going from 0.76 to 0.83. On 40 generated
# maps the two are level (120/160 against 121/160). If the objective ever
# becomes mean win rate rather than worst-case, cap 2 is the better answer and
# this comment is the reason to change it back.
MAX_GUARD_GUNNERS = 4
# Steps it will take toward an intruder to find a firing seat.
#
# Four was chosen when the attacker was ferried across the map and the guard's
# other jobs were all at home. With the ferry off both sides walk, so an
# intruder is in sight far longer before it emplaces and there is time to close
# on it. Re-measured on the full 8-bot pool and 40 generated maps:
#
#              pool            generated
#     2      (worse)           --
#     4    288/336  0.857    117/160  0.731
#     6    294/336  0.875    121/160  0.756   <- shipped
#
# It is worth +2 games against valkyrie and +1 against vigil, ragnarok, warden
# and gobbleglitch each -- a broad gain, not one map.
GUARD_CHASE_STEPS = 6

# Field Gunners are now set per doctrine in doctrine.py: 0 on open ground
# (measured: a roaming enemy walks away from the turret), 2 under FORTIFY
# where the enemy has to come down a lane.

# --- CPU budget -------------------------------------------------------------
# Each unit gets 10 ms of CPU per round, plus a 5% bank. Overrunning does not
# truncate the work -- the unit is interrupted and does not act at all that
# round -- so optional searches stop here and leave the rest of the turn for
# the ordinary action. Deliberately well under the limit: the ladder runs on
# AWS Graviton3 rather than this machine, and the measurement that set this
# number is a local one.
CPU_SOFT_BUDGET_US = 4000

# --- Sentinel siege ---------------------------------------------------------
# When the attacker can find no Gunner lane onto the enemy Core -- walls,
# barriers, or a sealed turtle -- it falls back to the one weapon nothing
# blocks: a Sentinel's shot pierces walls, buildings, and bodies (measured:
# a Sentinel behind a two-tile wall band killed a 500 HP Core in exactly
# 500/18*3 rounds). It is 2.78x worse per titanium than a Gunner, so it is a
# fallback, never the first choice.
SENTINEL_RANGE_SQ = 32
MIN_AMMO_FOR_SENTINEL = 40
# Barriers laid around a fresh siege Sentinel so return fire cannot reach it;
# its own shot does not care. Skipped when the bank is thinner than this.
SENTINEL_WRAP_RESERVE = 20

# --- Ported back from vigil --------------------------------------------------
# Two mechanics the ragnarok line lost when it was assembled from "the best
# measured mechanic from every lineage": vigil@e267eeb still has both, and
# vigil@e267eeb is the strategy that beats ragnarok in the Nash core.
#
# REPAIR_NETWORK: mend a hole shot in our own conveyor line. Every Harvester
# upstream of a gap mines into a dead end, so one 3 Ti tile restores the whole
# line's income. ragnarok cannot do this at all.
# WRITE_OFF_STUCK_BUILDERS: self-destruct a Builder that has failed to path for
# this many rounds, refunding its +20% scale and letting the Core respawn it
# somewhere not walled in. ragnarok never calls self_destruct.
REPAIR_NETWORK = True
WRITE_OFF_STUCK_BUILDERS = True
STUCK_ROUNDS_BEFORE_STANDDOWN = 40
# A Harvester this close is worth finishing before turning back to repairs, so
# four ores in a cluster do not each trigger a trip back down the line.
HARVESTER_FINISH_STEPS = 2

# --- Relay cap ---------------------------------------------------------------
# Escape Launchers one Builder will buy to throw itself forward. 0 disables the
# relay chain entirely and the attacker walks, which is what the atlas-free
# ragnarok_fair is forced to do -- and ragnarok_fair takes 25/42 off valkyrie
# where ragnarok itself only draws 21/42. On aurora the chaining bot ends with
# 6 Launchers, 1 Harvester and 4 Gunners against the walking bot's 3, 2 and 7.
# Escape Launchers one Builder will buy to throw itself forward.
#
# One, from warden_walk, chosen when the relay fired from round 2 on a guessed
# Core. With FERRY_ON_INFERENCE off the relay only runs once a unit has
# physically *seen* the enemy Core -- so it fires late, when the attacker is
# already close and a hop is worth more than the walk it replaces. Re-measured
# on the current chassis, full 8-bot pool and 40 generated maps:
#
#                 pool                     generated
#     0        (much worse)                --
#     1      290/336  0.863  min 0.81    120/160  0.750
#     2      295/336  0.878  min 0.81    122/160  0.762   <- shipped
#     3      291/336  0.866  min 0.81    (level)
#
# Better on both arms without giving anything back on the worst matchup.
MAX_RELAY_LAUNCHERS = 2

# Prefer Gunner seats outside every visible enemy turret's firing ray. A turret
# built where an enemy turret already points is shot before it has fired much,
# and the seat one tile off the ray usually reaches the same Core tile.
# Measured on the 21 official maps in both seats: against vigil@e267eeb it is
# 26/42 and 8 maps won 2-0, against 24/42 and 7 with it off; against
# ragnarok@79582fc it is unchanged at 26/42.
AVOID_ENEMY_RAYS = True

# --- Siege barriers ---------------------------------------------------------
# Barriers soaking enemy Gunner lanes aimed at our forward battery, out at the
# enemy Core. 3 Ti and +1% scale for 30 HP absorbs three Gunner rounds and six
# of their ammunition, which is titanium 1:1 -- the cheapest trade on the board
# and the one thing Pantheon does with barriers (31 of 33 across twenty games).
SIEGE_BARRIER_ENABLED = True
# Held back so soaking never eats the Gunner that the soaking is protecting.
SIEGE_BARRIER_RESERVE = 12

# --- Launcher retirement ----------------------------------------------------
# A field Launcher (escape ferry, relay) that has serviced no request and seen
# no enemy for this long hands its +10% scale back. Ring Launchers sit within
# HOME_GUARD_RADIUS_SQ of the Core and never retire: they are the throw pad
# and the displacement screen, and the round they are needed is too late.
LAUNCHER_QUIET_ROUNDS = 45

# --- Late-game economy ------------------------------------------------------
# One conveyor trunk saturates at 4 Harvesters (1 stack/round vs 10 Ti per 4
# rounds each). Early game the cap is exactly that; once the opening blitz
# has clearly not ended the game, a second trunk is allowed. The round-1000
# tiebreak order is titanium_collected -> live harvesters -> titanium_stored,
# so in a long game delivered income is literally the win condition.
NETWORK_CAP_EARLY = 4
NETWORK_CAP_LATE = 8
ECON_EXPAND_ROUND = 120

SLOT_BUILDER_TICKET = 0
# Two ore reservations: the ring Builder becomes a second miner whenever the
# seal is unaffordable, so two claims can be live at once. Slot 8 was the
# seventh Launcher-request slot; six requests still cover every builder.
CLAIM_SLOTS = (1, 8)
LAUNCH_REQUEST_SLOTS = range(2, 8)
LAUNCH_DIRECTION_BITS = 4
LAUNCH_DIRECTION_MASK = (1 << LAUNCH_DIRECTION_BITS) - 1
LAUNCH_REJECTION_FLAG = 1 << 31
LAUNCH_REJECTION_POSITION_BITS = 11
LAUNCH_REJECTION_POSITION_MASK = (1 << LAUNCH_REJECTION_POSITION_BITS) - 1
SLOT_SYMMETRY_REJECT_START = 9  # slots 9..10, one writer per opening Builder
SLOT_CONSTRUCTION_LOCK = 11
SLOT_CORE_DAMAGED = 12
# Bit 2 of SLOT_CORE_DAMAGED: titanium has stopped arriving. Bits 0-1 are
# the Core's own damage alarm and are read separately.
ECONOMY_DEAD_FLAG = 4
SLOT_ENEMY_CORE = 13
SLOT_OWN_CORE = 14
SLOT_BUILDER_HEARTBEAT = 15
# Heartbeat layout: (round + 1) << HEARTBEAT_SHIFT, with one bit per Builder
# index below it. Eight bits is more Builders than the scale factor will ever
# make worth spawning.
HEARTBEAT_SHIFT = 8
HEARTBEAT_MASK = (1 << HEARTBEAT_SHIFT) - 1
# Builders the Core will field at once, replacements included. The opening
# headcount is three and is not in question -- this is the ceiling on replacing
# one the enemy killed.
MAX_LIVE_BUILDERS = 3
# Total Builders one game may spawn. A replacement is +20% on every price the
# team pays for the rest of the game, so an attrition war fought by respawning
# is one we lose on cost even while winning it on bodies.
MAX_TOTAL_BUILDERS = 5
# Held back before a replacement is bought, so reinforcing never starves the
# turrets and ammunition that the dead Builder was on its way to buy.
REINFORCE_RESERVE = 40

LAUNCH_RANGE_SQ = 26
