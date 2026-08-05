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
# Ring Launchers one Builder will put up. Superseded: the count now comes from
# RING_MAX_SITES in the Launcher-screen section at the foot of this file, and
# the sites come from a set cover of the approach shell rather than a compass.
# The old value was 8 -- eight compass sites on a radius-2 ring, which is where
# the touching Launchers in the replays came from.

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
# round -- so optional searches have to be bounded.
#
# They are bounded by *work*, never by a clock. A guard that reads
# `get_cpu_time_elapsed` makes the bot's decisions a function of how loaded the
# machine is: identical code on identical boards produced 11 different winners
# in 210 matches, which is larger than most effects measured here, and it cuts
# hardest on the contended machine the ladder actually runs on. See
# SIEGE_SEARCH_EVERY for the deterministic bound that
# replaced it.
# Rounds between attempts at the siege-seat search, the widest in the bot.
SIEGE_SEARCH_EVERY = 10

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

# --- Replacing losses -------------------------------------------------------
# Bank above which the Core replaces a Builder even though one is still alive.
# A working three-Builder team spends its income as it arrives; a bank this
# large means the workforce is too small to spend it, which is the only signal
# available -- the comms store cannot carry a live headcount because writes are
# invisible to other units until the next round.
REPLACEMENT_BANK_THRESHOLD = 260
REPLACEMENT_COOLDOWN_ROUNDS = 12

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

# --- Late economic expansion --------------------------------------------------
# Past the opening this Core only ever replaced the dead: a Builder arrives
# because the bank stopped being spent (REPLACEMENT_BANK_THRESHOLD) or because
# the Core is dying. Both are emergencies, and neither is what a long game is
# decided by.
#
# 2.3.4 made that a hole. Healing restores 4 HP for a flat 1 Ti at any cost
# scale, against the 3.33 Ti of ammunition a Sentinel pays for 6 damage, so
# defence is ~2.2x more titanium-efficient than offence, Cores mostly do not
# die, and the median game reaches the round-1000 tiebreak -- whose first
# criterion is titanium *collected*. In that game a fourth Builder laying belt
# is not a body in an attrition war, it is income.
#
# Measured here, this bot collected 630 titanium a game against vidar's 1548 on
# the same ten maps. The headcount-of-three finding it overrides was about the
# *opening* and still holds: an opening Builder is +20% on the Launchers and
# Harvesters the opening has not bought yet, where the same +20% levied at
# round 200 falls almost entirely on conveyors at 3 Ti -- 0.6 Ti a tile against
# the 2.5 Ti a round a connected Harvester returns for the rest of the match.
ECON_EXPAND_BUILDERS = False
ECON_BUILDER_ROUND = 200
# Only genuine surplus. A Builder is 30 Ti before scale and this holds back
# roughly a Harvester and the belt to reach it on top of the Builder itself, so
# expanding never takes the titanium the existing miners are already waiting on.
ECON_EXPAND_RESERVE = 120
# Total Builders the expansion may ever add, counted from spawns rather than
# from a live headcount -- because a live headcount is not available.
#
# The engine's own documentation settles it: "Writes are buffered: a
# write_store() call becomes visible to all units at the start of the *next*
# round." Every Builder in a round therefore reads the same snapshot, so a
# per-round bitmask cannot accumulate -- each Builder ORs its bit onto the same
# stale value and the last writer's word is the one that survives. A mask built
# that way reads as one Builder no matter how many are alive, which is exactly
# what happened here: the live cap never bound and the Core spawned up to 79
# Builders in a game, each one +20% on every price the team paid afterwards.
#
# So the cap is on spawns, which the Core can count for itself, and it is small.
# Rate-limiting it with the replacement cooldown is what keeps a rich bank from
# converting into the whole allowance in four consecutive rounds.
ECON_MAX_TOTAL_BUILDERS = 6

# --- Defensive turret kind ----------------------------------------------------
# Home defence buys Sentinels, not Gunners. The Aug 4 patch inverted the turret
# table -- see _turret_kind for the row-by-row -- and the load-bearing row is
# cost scale: both turrets now levy the same permanent +20% on every price the
# team pays afterwards, and that tax, not titanium, is what caps how many
# turrets a game can hold. Once the count is fixed by the tax, 10 Ti more a seat
# for 1.71x the damage, 1.6x the HP, 2.46x the range and an unblockable line is
# free. 2.3.3's +10% Gunner against a +20% Sentinel is exactly what made Gunner
# spam correct, and that is the number the patch changed.
#
# Applied to the two home-guard paths only. The field and denial turrets keep
# the Gunner: their seats are bought on whatever the Builder happens to meet,
# where the extra reach buys nothing and rotation -- the one row the Gunner
# still wins -- is worth more.
DEFEND_TURRET_SENTINEL = True
# Answer a live Gunner lane with a 3 Ti barrier before a 20-30 Ti turret. See
# the ordering in _defend_core: the barrier was third behind two turret paths
# that both consume the turn, so on the rounds it mattered it was never reached.
LANE_BARRIER_FIRST = True
# A conveyor we break gets a barrier in the hole on the very next turn, ahead of
# whatever else that Builder was doing. Cutting without plugging is rented
# damage -- they relay the tile for 3 Ti -- and the plug is what converts a
# round of fire into a permanent severance. Required behaviour: this is on
# regardless of what the panels say about it.
PLUG_CUT_IMMEDIATELY = True
# How far a Builder will walk back to plug a hole it made, in Chebyshev tiles.
PLUG_CUT_LEASH = 4
# Every Builder past the opening headcount mines, whatever the opening's role
# arithmetic would have made it.
#
# Both role branches key on `builder_index >= economy_builders`, which is the
# *opening's* way of saying "this one is not a miner". Read by a replacement
# spawned on round 250 it says the opposite of what it means, so every Builder
# the Core bought to recover from a loss walked to the enemy Core as a fourth
# attacker instead of laying belt -- paying +20% on every later price to add
# nothing to the economy. It shows up directly in the ledger: losing games spawn
# 7.5 Builders and hold 1.25 Harvesters, winning games spawn 5.6 and hold 1.63.
LATE_BUILDERS_MINE = False
# Home-guard turret escalation: `1 + damage // HOME_TURRET_STEP`, capped. The
# guard escalates with sustained damage rather than committing a formation
# before it knows one is needed; these two numbers set how fast and how far.
HOME_TURRET_MAX = 4
HOME_TURRET_STEP = 180
# Run the outer barrier seal on every doctrine rather than FORTIFY only. The
# seal is dozens of tiles and often will not finish before the game does, which
# is why it was restricted -- but every loss left is a Core kill.
SEAL_EVERY_DOCTRINE = False
# Turrets the attacker will buy at the enemy base before it falls back to
# harassment. Each one is a permanent +20% on every price the team pays for the
# rest of the game -- including the mending and the defensive seats at home --
# and it is bought at the far end of the map, where losing it is likeliest.
ATTACK_TURRET_CAP = 5

# --- Core mending -------------------------------------------------------------
# The Builder posted at the Core mends it on any damage at all, rather than
# waiting for the Core's own 50-HP `repair_alert`. See the call site: the
# threshold exists to summon a Builder from across the map, and the Builder
# standing on the Core can simply read its HP.
GUARD_HEALS_ON_ANY_DAMAGE = True
# The economy Builder joins the mending detail once the Core is below
# CRITICAL_HP, instead of answering with a further turret. See the call site:
# one mender cancels two thirds of a Gunner, two out-heal it outright, and the
# loss ledger says this bot dies holding turrets rather than short of them.
SECOND_MENDER_ON_CRITICAL = True
# Alarm level at which the economy Builder joins the mending detail. 2 is the
# Core below CRITICAL_HP; 1 is the Core's ordinary 50-HP repair alert.
SECOND_MENDER_ALARM = 2
# Trigger the second mender on any Core damage instead of on the alarm level.
# See the call site: this is vidar_r3's one change over vidar, and vidar_r3 is
# the matchup that holds this bot's floor.
SECOND_MENDER_ON_ANY_DAMAGE = True
# How far from the Core a Builder may be and still be pulled onto mending, in
# Chebyshev tiles. This is a leash, not a recall radius: a miner summoned from
# across the map arrives after the decision has been made, and the tempo it
# gives up costs more games than the healing saves.
MENDER_LEASH = 10

# --- Sentinel target order ----------------------------------------------------
# Let a Sentinel shoot the enemy supply line. `get_nearby_entities` returns
# units, and conveyors, harvesters and barriers are *buildings*, so every
# Sentinel this lineage has ever built simply held its fire whenever no unit
# stood on its line -- with an enemy Harvester sitting on that same line.
#
# In a game that reaches the round-1000 tiebreak the enemy's Harvesters and
# trunk are the win condition, and they are 30 and 20 HP: two shots each.
STARVE_THE_ECONOMY = True
# Rounds of firing at a Core whose HP is not falling before the Sentinel gives
# up on it. One mender restores 4 HP a round for a flat 1 Ti against a single
# Sentinel's 6 damage for 3.33 Ti of ammunition, so a besieged Core that has
# stopped losing HP is not dying slowly, it is being held -- and every further
# shot is 10 ammunition into a Core that will be full again before we return.
SIEGE_STALL_ROUNDS = 12
# A Builder Bot this close outranks everything, at either end of the map.
# Defending, the intruder emplacing at our Core is the whole enemy attack.
# Besieging, it is the mender arithmetic above: shooting a Core past a mender
# is paying to lose slowly, and shooting the mender ends it.
BUILDER_PRIORITY_RADIUS_SQ = 20

SLOT_BUILDER_TICKET = 0
# Two ore reservations: the ring Builder becomes a second miner whenever the
# seal is unaffordable, so two claims can be live at once. Slot 8 was the
# seventh Launcher-request slot; six requests still cover every builder.
CLAIM_SLOTS = (1, 8)
LAUNCH_REQUEST_SLOTS = range(2, 8)
LAUNCH_DIRECTION_BITS = 4
LAUNCH_DIRECTION_MASK = (1 << LAUNCH_DIRECTION_BITS) - 1
# A launch request now carries where the passenger was actually going, not just
# which way it wanted to be thrown. Without it the Launcher can only optimise a
# projection along a compass bearing, which is a straight-line proxy for "close
# to the goal" and is wrong exactly where it matters -- a landing four tiles
# nearer as the crow flies can be twenty tiles further to walk if a wall is in
# between. Layout, low to high: direction (4), goal position (10), passenger id
# (17), rejection flag (bit 31). pack_pos tops out at 958 so 10 bits is exact.
# The Builder now names its landing tile outright, as an index into the pad's
# 89-tile throw field (see utils.THROW_OFFSETS). Seven bits, against the ten an
# absolute position cost -- but the saving is not the point. The point is which
# unit decides: the pad sees only its current vision, while the Builder carries
# a remembered threat map and the route it is trying to walk. Compressing all
# of that into a compass bearing and letting the pad guess is how passengers
# ended up landing in firing lines and beside enemy Launchers.
LAUNCH_LANDING_BITS = 7
LAUNCH_LANDING_MASK = (1 << LAUNCH_LANDING_BITS) - 1
LAUNCH_PASSENGER_SHIFT = LAUNCH_LANDING_BITS
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
# How far the landing-distance flood runs. A throw reaches r^2=26, so a little
# beyond that is enough to price every candidate landing and no more.
WALK_FLOOD_RADIUS_SQ = 64
# Treat a friendly Launcher as an edge in the movement graph rather than an
# obstacle. Standing beside one and asking for a throw covers up to r^2=26 in a
# single round, over anything in between, which is faster than any walk and is
# also the way past a firing line that cannot be crossed on foot.
LAUNCH_HOPS_IN_PATHS = True

# --- Launcher screen: cover the approach, not the compass ---------------------
# The old ring was eight compass sites at RING_RADIUS 2. Around a 2x2 Core that
# radius cannot hold eight things without them touching, which is why replays
# show Launchers built side by side: the geometry, not the placement, was wrong.
#
# What a defensive Launcher actually does is pick a Builder up at range squared
# LAUNCH_PICKUP_SQ and throw it away, so one Launcher covers a 3x3 stamp. The
# tiles worth covering are the ones an enemy must cross to bring a turret into
# range of the Core -- the shell just outside the threat disc. So the screen is
# a minimum set cover of that shell by 3x3 stamps, which is also what stops two
# Launchers landing next to each other: overlapping stamps cover nothing new.
#
# RING_THREAT_SQ is the whole difference between this bot and its sibling:
# 13 sizes the disc to Gunner reach, 32 to Sentinel reach. Sentinel range is
# 2.5x the area, so the sibling's screen is much larger and much more expensive.
RING_THREAT_SQ = 13
LAUNCH_PICKUP_SQ = 2
# How far apart the screen would *like* its Launchers, in Chebyshev tiles. This
# is a preference, not a rule: coverage wins ties against it, so a shell tile
# only one site can reach is still covered even when that site ends up beside
# another. Refusing it would leave a hole an attacker simply walks through.
# Past this distance the screen is spread enough and more buys nothing, so the
# value is a cap on the preference rather than a spacing.
RING_MIN_SEPARATION = 3
# Re-plan the screen once vision has grown by this many tiles. The dead-end
# prune is only as good as the map we have seen, and on round 3 that is nearly
# nothing; re-planning is what turns later vision into Launchers not built.
RING_REPLAN_TILES = 60
# A screen is worth titanium only up to a point: each Launcher is +10% on every
# price the team pays afterwards, so a full Sentinel-range cover would be +80%
# or worse. This cap is the constant to sweep, not the geometry.
# DROPPED. The defensive screen is off: RING_MAX_SITES 1 leaves the single
# enemy-facing pad, which is the attacker's throw platform and the one site in
# this lineage with a measured job. It is not a defensive ring.
#
# The screen was built, measured on r03 and withdrawn. Closing a Core off from
# Sentinel reach in open ground genuinely needs ~9 Launchers -- the geometry is
# in _launcher_ring_targets and it is correct -- and nine Launchers is +90% on
# every price the team pays afterwards. On the map it was traced on the bot
# mined *more* than the build that won (950 against 840) and lost anyway,
# because the titanium went into cost scale instead of defence. Barriers deny
# the same ground at 3 Ti and +1%, which is the direction worth trying next.
#
# The planning code stays. It is right, it is cheap to re-enable, and the
# reachability prune it carries is reusable for anything that needs to know
# which approaches to our Core an enemy can actually walk down.
RING_MAX_SITES = 1
# The "+1": one Launcher of depth behind the cut. A minimum cut is exactly
# tight -- it holds until one site in it dies. The spare goes enemy-facing.
RING_EXTRA_SITES = 0
# A screen must never wall our own units in. After placing a site, the Core's
# spawn ring must still reach this many open tiles, or the site is rejected:
# Launchers are buildings and buildings are not walkable, so every site is a
# wall to us as much as to them.
SELF_SEAL_MIN_OPEN = 40
RING_TITANIUM_RESERVE = 25

# --- Reachability -------------------------------------------------------------
# Lucas's constraint: a direction the enemy cannot walk down does not need
# covering. Shell tiles are kept only if they are reachable from the enemy half
# without crossing the threat disc, so a dead end, a pocket behind terrain, or a
# map edge costs nothing. On a closed map this can cut the screen to two sites.
REACHABILITY_ENABLED = True

# --- Attacker survival --------------------------------------------------------
# An attacker that walks a path through a known firing line arrives dead. Look
# this many steps ahead, charge each threatened step the damage that would land
# on it, and re-plan around the threat when the total would kill us.
PATH_LOOKAHEAD = 12
PATH_DAMAGE_PER_THREAT_STEP = 7
PATH_SAFETY_MARGIN = 7
# How much longer a threat-avoiding route may be before it stops being worth
# it, as a multiple of the short route plus a constant. Rounds are what the
# attacker is short of, so a detour is cheap but not free.
PATH_DETOUR_FACTOR = 1.6
# Rounds a Builder will spend backing away from a lane it cannot walk before it
# pays for a Launcher to go over it instead. A Sentinel does not move, does not
# run dry and cannot rotate off the tile, so waiting is not a plan -- but a
# throw costs 20 Ti and +10%, so it is not the first answer either.
FIRE_BLOCK_LAUNCH_ROUNDS = 3

# --- Logistics under fire -----------------------------------------------------
# Never lay a conveyor, splitter or harvester inside a known enemy firing line:
# it is 3 Ti and +1% to replace something they clear for 4 ammunition, and
# heimdall's bridge trace showed a single such tile rebuilt 22 times for an
# income of 10 titanium in 1000 rounds. Barriers are the exception and go there
# deliberately -- a barrier in their line is 3 Ti that costs them ammunition and
# blocks the lane, which starves the economy the line was protecting.
AVOID_THREAT_FOR_LOGISTICS = False
BARRIER_INTO_THREAT = True
# Rounds between belt patrols. Enemies cut lines and then seat a turret on the
# gap; a miner that keeps rebuilding into that seat is paying rent. On the
# third failure the tile is written off and the route is planned again from
# scratch, avoiding every tile the turret can reach.
BELT_PATROL_ROUNDS = 40
REPAIR_ATTEMPT_LIMIT = 3

# --- Contested logistics ------------------------------------------------------
# Nothing in this lineage has ever contested the enemy's belt. Two halves:
# tap a harvester of theirs into a conveyor of ours (their 2.5 Ti/round becomes
# ours, and it costs them nothing they can see), and cut the conveyor feeding
# their Core (3 Ti of ours deletes a stack of theirs every round it stays down).
STEAL_ENEMY_HARVESTER = True
CUT_ENEMY_BELT = True
CONTEST_MAX_DISTANCE_SQ = 400

# --- Turret fire discipline ---------------------------------------------------
# fire() is an explicit call, so holding fire is possible. A barrier with an
# enemy Builder beside it is a barrier that gets rebuilt for 3 Ti the round
# after we spend 4 ammunition breaking it; that trade loses. Hold, and shoot
# the Builder's own work only once the Builder has left.
HOLD_FIRE_ON_TENDED_BARRIER = True

# Damage per shot, used to price a tile in the threat map. A tile two turrets
# both cover is twice as lethal and the attacker's survival check has to see it.
GUNNER_DAMAGE = 7
SENTINEL_DAMAGE = 18

# --- Launch-request instrumentation -------------------------------------------
# Every stage of a relay request logged to stderr. Stdout is discarded by the
# engine, which is why none of this bot's existing PLAN_FAILED lines have ever
# been readable; stderr survives. Off for upload, on for the benchmark.
DEBUG_LAUNCH = False
# Log every building placed, with whether the tile was known covered, visibly
# covered, or covered by a turret we had ever seen. Off for upload.
DEBUG_BUILD = False
# How long a pad remembers having thrown a passenger. Long enough to cover the
# one-turn lag on a store write, short enough that a relay chain can reuse a pad
# and a ferried Builder can be ferried home again.
THROW_MEMORY_ROUNDS = 3

# --- Sentinel offence ---------------------------------------------------------
# The siege battery is Sentinels, not Gunners. Per titanium a Sentinel is 1.8
# HP/Ti against a Gunner's 1.75, it out-damages one over time (18 every 2 rounds
# against 7 every round), it is 40 HP against 25, and -- the part that decides
# it -- its line is never blocked, so a defender cannot answer it by building
# something in the way.
SENTINEL_SIEGE_FIRST = True
# No two of our siege Sentinels may share a row, a column or a diagonal. Turrets
# fire a single-tile-wide line along one of eight compass directions, so two of
# ours on a shared line are two kills for one enemy turret that never has to
# rotate. This is the non-attacking-queens constraint, and it is the whole of
# "spread out" in a game where every weapon is a ray.
SENTINEL_SPREAD_LINES = True
SIEGE_SENTINEL_TARGET = 4

# --- Guard patrol and trapping ------------------------------------------------
# The ring the guard walks when nothing is attacking. Outside the Core's own
# 2x2 but well inside its r^2=36 vision, so the guard is adding sight of the far
# side rather than duplicating what the Core already sees.
PATROL_RADIUS = 3
# Box a loose enemy Builder in with barriers, then put a Gunner on the box. A
# barrier is 3 Ti against a Builder's 30 Ti and +20% scale, and a boxed Builder
# cannot dodge the ray the way a free one does.
TRAP_ENEMY_BUILDERS = False
TRAP_MAX_DISTANCE_SQ = 64
# The same trick, seen from the other side. A Builder down to this many cardinal
# exits with an enemy Builder within r^2=9 is one 3 Ti barrier from being worth
# nothing for the rest of the game, so it leaves first and argues later.
ESCAPE_ENCIRCLEMENT = True
ESCAPE_MIN_EXITS = 1
# One check at the top of the Builder turn rather than a rule each mechanic has
# to remember. A Builder's tile is a free choice in nearly every job it does, so
# a covered tile is HP spent for nothing. Exempt: a mender beside a Core that is
# under attack, where 4 HP per titanium beats anything the lane can do to it.
LEAVE_FIRING_LINE = True
# Rounds a Builder spends exposed to put up an escape Launcher: one to reach a
# buildable tile and one to build. Used to price launching against walking, so
# the Launcher is only bought when it genuinely saves HP.
LAUNCHER_BUILD_ROUNDS = 2
