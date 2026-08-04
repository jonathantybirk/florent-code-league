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
# Pantheon's shape, not ragnarok's. Ragnarok spawns three Builders and puts the
# Launcher Builder last, so the pad lands around round 6. Pantheon spawns four,
# one per round on r0-r3, and the *first* Builder puts the pad up on round 1 --
# 150 of 150 replays, every map, every opponent. Everything the pad is worth
# comes from being early: it throws on r2-r5 and is gone by r6.
LAUNCHER_BUILDERS = 1
LAUNCHER_BUILDER_INDEX = 0
MAX_OPENING_BUILDERS = 4

# Drop a ring direction when the map edge is this close behind it: nothing can
# approach from off the map, so a Launcher there guards nothing and still costs
# its +10%.
# Passengers the opening pad ferries before it razes itself. Pantheon throws
# exactly four in 122 of 150 games, on rounds 2-5, one per round.
PANTHEON_FERRY_PASSENGERS = 4
# Roles follow throw order, not ragnarok's economy-first convention: the first
# two passengers off the pad raid the enemy Core, the last two go to ore.
# 81 of 150 games are exactly RREE and RR is the prefix of every pattern seen.
# Builder 0 builds the pad on r1 and is then thrown off it on r2 as raider one.
# Last round a Builder will stand on the pad waiting to be thrown. Pantheon's
# four throws land on r2-r5 in 116 of 116 v20 games; past that a Builder still
# waiting is a Builder that is never getting picked up.
PANTHEON_FERRY_LAST_ROUND = 6
# Pickup is dist_sq <= 2 from the Launcher.
PICKUP_RANGE_SQ = 2
# Throw range, measured from the Launcher rather than the passenger.
THROW_RANGE_SQ = 26

PANTHEON_RAIDERS = 2
# Launchers built per game. Pantheon builds exactly one -- 151 across 150
# replays -- and it is the throw pad, not a ring. Ragnarok rings the Core with
# three or four, each 20 Ti and a permanent +10% on every later build, for a
# displacement screen this opening never gets to use because every Builder is
# already gone by round 5.
PANTHEON_RING_SITES = 1
# ...except where the pad has to double as a displacement screen. bridge is a
# 21x8 corridor with our Core in the corner: capped to one pad we lose the Core
# on round 50, with two we hold. The real Pantheon does not kill on bridge
# either -- its win there ran the full 1000 rounds on the tiebreak -- so a
# second Launcher on closed ground is consistent with what it actually does.
PANTHEON_RING_SITES_FORTIFY = 2

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
