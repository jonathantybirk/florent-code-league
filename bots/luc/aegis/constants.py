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
# Ring Launchers one Builder will put up. The pad is the enemy-facing site and
# it is the only one with a measured job; the remaining seven are a
# displacement screen. Spawning the pad Builder first gives it the rounds to
# build all eight, so this is what stops it.
RING_MAX_SITES = 8

# Ferry toward the symmetry inference's committed guess as well as toward a
# Core we have actually seen. Measured and OFF: the inference is right on 28 of
# 42 published map-sides, and the reasoning that the two wrong candidates still
# lie in the enemy half is simply not worth what a wrong throw costs. Played
# atlas-free over the 21 official maps in both orders against the same bot with
# this off, ferrying on the guess scores 17/42 where refusing scores 21/42.
#
# So the original `p.atlas is None` gate was right to refuse a guess and wrong
# only about what counts as knowing: a Core a unit has physically seen is not a
# guess, and that case is now allowed (see `_opening_ferry`). That widening is
# worth 0 games on the published pool, where the atlas already knew, and is
# kept because off the pool the atlas knows nothing.
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

# Routine ferry hops one Builder will buy. Does NOT limit the Launcher a
# Builder reaches for after PATH_FAILURES_BEFORE_LAUNCHER rounds of failing to
# path -- being walled out by a turtle is the one case where the chain is worth
# its cost scale. See _build_escape_launcher for the per-opponent measurement.
MAX_ROUTINE_RELAY_LAUNCHERS = 1
# Prefer Gunner seats outside every visible enemy turret's ray.
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
SLOT_ENEMY_CORE = 13
SLOT_OWN_CORE = 14
SLOT_BUILDER_HEARTBEAT = 15

LAUNCH_RANGE_SQ = 26
