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
# much as a screen. Two was measured on the *warden_walk* chassis, as maps won
# 2-0 against the two Nash-core agents: cap 8/3/2/1 -> worst matchup
# 29/29/33/24%. Re-measured here on the full 8-bot pool and 40 generated maps:
#
#                 pool                     generated
#     0      286/336  0.851  min 0.76    129/160  0.806
#     1      304/336  0.905  min 0.81    134/160  0.838   <- shipped
#     2      295/336  0.878  min 0.81    122/160  0.762
#
# The old number did not survive the chassis it was tuned on, and the reason is
# MAX_RELAY_LAUNCHERS going to 2. The costs compound: the second ring site is a
# third Launcher, so it raises the price of both relay Launchers by 10% each,
# and _run_launcher_ring returns False for every round the Builder spends
# walking to it -- rounds that Builder owes to the belt and to _guard_home.
# The relay now buys the forward hop the second ring site used to; paying for
# both is paying twice.
#
# Not zero: one site is the pad, and dropping it costs 5 games on the generated
# set and 20 on the pool. The falloff at both edges is the shape a real effect
# has.
RING_MAX_SITES = 1

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

# --- Enemy spawn denial ----------------------------------------------------
# A Core spawns Builder Bots only on passable tiles within spawn radius^2 = 2,
# which is exactly the twelve tiles at Chebyshev distance 1 from its 2x2
# footprint. Wall all twelve and the enemy Core cannot spawn again, cannot be
# healed (healing needs an orthogonally adjacent tile too), and every Builder
# they lose from that point is gone permanently.
# MEASURED AND OFF, on the mechanism rather than on a win rate. Traced against
# vigil on jackpot and longship: their Builder Bots spawn on rounds 0, 1 and 2
# and never again. Every bot on this panel, ours included, buys a fixed opening
# of three Builders and only spawns more on a damage alarm -- so there are no
# spawns to deny, and the attacker spent its rounds walking a ring instead of
# shooting. The code stays because the reasoning is sound and the cost is a
# constant: against an opponent that does replace its losses this is decisive,
# and that is a one-line change rather than a rewrite.
SPAWN_DENIAL_ENABLED = False
# Only bother once the attacker is actually at their Core; walling a ring from
# across the map is a walk, not a plan.
SPAWN_DENIAL_RANGE = 6
# Leave the siege its ammunition. A ring that goes up instead of the Sentinel
# that was about to fire is a trade, not a gain.
SPAWN_DENIAL_RESERVE = 20

# --- Core bulwark ----------------------------------------------------------
# Measured before it was built, on 32 lost Cores over the five maps this
# chassis loses most on: 97.6% of the damage that killed them was Gunner fire,
# 2.4% Sentinel, and enemy Builder Bots dealt exactly zero. They do not walk up
# and hit the Core; they emplace a Gunner near it and shoot. 114 of those went
# up within four tiles of the footprint and each lived a median 34 rounds.
#
# A Gunner's ray "stops at the first targetable tile (a builder bot or a
# building)". The Core is 2x2, so every compass ray that reaches it -- from any
# range, orthogonal or diagonal -- must cross the ring at Chebyshev distance 1.
# That ring is twelve tiles. Put any building on all twelve and no Gunner
# anywhere on the map has a firing line into the Core, ever. Only a Sentinel,
# whose line is never blocked, still reaches: 2.4% of the damage.
#
# Twelve barriers is 36 Ti and +12% scale. It is not the same thing as
# `_run_core_seal` below, which walls the whole threat *disc* -- dozens of
# tiles, FORTIFY-only, and usually unfinished when the game ends.
#
# The first cut of this walled only the eight orthogonal neighbours, on the
# theory that those are the tiles an enemy Builder must stand on to attack. It
# scored 246/336 against a 242 baseline, which is what a correct answer to a
# problem you do not have looks like. The twelve-tile ring, walked as a cycle
# so it actually gets built, scores 250.
BULWARK_ENABLED = False
# Barriers are 3 Ti; there is no scenario in which holding a reserve above
# that is worth leaving the Core's doorstep open.
BULWARK_RESERVE = 0
# How often a Builder re-verifies a ring it remembers as closed. Barriers are
# shot out of our sight, so the memory that lets a Builder leave and mine has
# to expire -- fast while the Core is being hit, slowly when it is quiet.
BULWARK_RECHECK_ALARM = 15
BULWARK_RECHECK_QUIET = 60

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
# The same budget denominated in Sentinels. 4 Gunners are 14 damage a round
# and 100 HP; 2 Sentinels are 12 and 80, at 2.46x the reach and through any
# terrain, for 60 Ti against 80 and the same +80% of cost scale... no: the
# same *count* of +20% steps is what matters, and two Sentinels levy +40%
# where four Gunners levy +80%. Half the tax for most of the damage is the
# whole reason the patch changed which turret this bot buys.
MAX_GUARD_SENTINELS = 2
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

# --- The 2.3.4 turret arithmetic --------------------------------------------
# This whole lineage buys Gunners. The reason is one number, written down in
# `_build_siege_sentinel`'s docstring and repeated in half the comments in this
# file: a Gunner paid "2.78x less per point of damage". Under 2.3.3 that was
# exactly right -- 10 damage for 2 ammunition against 18 for 10 is 5.00 against
# 1.80, and 5.00/1.80 = 2.78.
#
# The Aug 4 patch repriced both turrets, and re-deriving the table from the
# engine's own GameConstants rather than from those comments inverts every row
# but one:
#
#                          Gunner        Sentinel      who wins
#     build cost           20 Ti         30 Ti         Gunner, by 10 Ti
#     cost scale           +20%          +20%          tied
#     HP                   25            40            Sentinel, 1.6x
#     damage/shot          7             18
#     fire cooldown        1             2
#     damage/round         3.5           6.0           Sentinel, 1.71x
#     ammunition/shot      4             10
#     damage/ammunition    1.75          1.80          Sentinel
#     attack radius^2      13            32            Sentinel, 2.46x range
#     blocked by terrain   yes           never         Sentinel
#     can rotate           10 Ti         no            Gunner
#
# The load-bearing row is `cost scale`. Both turrets levy the same permanent
# +20% on every price the team will ever pay, and that tax -- not titanium --
# is what caps how many turrets a game can hold. Once the count is fixed by the
# tax, paying 10 Ti more per seat to get 1.71x the damage, 1.6x the HP, 2.46x
# the range and a line nothing blocks is not a trade, it is free. Under 2.3.3
# the Gunner's +10% against the Sentinel's +20% is what made Gunner spam
# correct; 2.3.4 doubled the Gunner's tax and left the Sentinel's alone.
#
# So the default turret is now the Sentinel and the Gunner is the fallback,
# which is the exact reverse of every comment below this line. A Gunner is
# still right in two situations and they are both encoded as fallbacks rather
# than argued: the bank holds 20 Ti but not 30 at a moment that decides
# something, and the seat needs to be re-aimed later, which only a Gunner can
# do.
SENTINEL_RANGE_SQ = 32
# Per role, because the roles do not have the same failure mode. Each is a
# separate flag so the panel can price them one at a time rather than as a
# single "use Sentinels" switch that cannot be diagnosed when it loses.
#
#   guard   -- the reactive home guard, the biggest mechanic in the record.
#              Its job is killing a 40 HP Builder before it emplaces: Sentinel
#              3 shots / 7 rounds against Gunner 6 shots / 11, and r^2=32
#              answers the intruder eight tiles out instead of three, which is
#              often before it is in range to build anything at all.
#   defend  -- the damage-alarm counter-battery. Same argument.
#   field   -- turrets put on whatever an economy Builder meets in the open.
#   denial  -- turrets bought for the ray rather than the shot. This one is
#              the least obvious: a denial ray is a wall, and the Sentinel's
#              ray is 5.6 tiles long instead of 3.6 and is not cut short by
#              the first building it crosses, so it denies far more ground.
GUARD_TURRET_SENTINEL = True
DEFEND_TURRET_SENTINEL = True
FIELD_TURRET_SENTINEL = False
DENIAL_TURRET_SENTINEL = False
# Ammunition held before a Sentinel seat is bought at all. A Sentinel that
# cannot fire is 30 Ti and +20% of pure tax, so this is deliberately above the
# Gunner's floor of 20 and above one shot's 10: enough for three shots, which
# is a dead Builder.
MIN_AMMO_FOR_SENTINEL_SEAT = 30

# --- Sentinel siege ---------------------------------------------------------
# When the attacker can find no Gunner lane onto the enemy Core -- walls,
# barriers, or a sealed turtle -- it falls back to the one weapon nothing
# blocks: a Sentinel's shot pierces walls, buildings, and bodies (measured:
# a Sentinel behind a two-tile wall band killed a 500 HP Core in exactly
# 500/18*3 rounds).
MIN_AMMO_FOR_SENTINEL = 40
# Siege Sentinels the attacker will stand up at the enemy Core.
#
# One was never a decision -- `_build_siege_sentinel` was the last-resort
# branch for a Core no Gunner lane could reach, so it built the fallback and
# stopped. As the primary weapon it should be sized on arithmetic instead:
#
#   a 500 HP Core dies to N Sentinels in 500 / (6N) rounds
#     N=1  84 rounds    N=2  42 rounds    N=3  28 rounds
#
# and on what the economy can feed. A Sentinel fires every 3 rounds for 10
# ammunition, which is titanium 1:1, so it burns 3.33 Ti/round sustained.
# Passive income is 2.5 Ti/round and one saturated conveyor trunk is 10
# Ti/round, so two Sentinels take two thirds of a working economy and three
# take all of it. Two is the arithmetic answer; the flag exists to check the
# arithmetic against the panel.
SIEGE_SENTINEL_BATTERY = 2
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
# Times one belt tile will be rebuilt before we stop paying for it.
# Traced on bridge: the Harvester at (5,4) is walled in on three sides,
# so its only route home runs through (5,3) -- which lies on row 3, the
# map's one shared corridor, inside an enemy Gunner's ray. We rebuilt
# that single tile 22 times for 66 Ti and +22% scale, and mined 10
# titanium in 1000 rounds. A hole that keeps reappearing is not damage,
# it is a tile the enemy controls, and the belt has to go somewhere else.
# --- Flanking a defended Core ------------------------------------------------
# Remembered enemy turrets within FLANK_RADIUS of their Core, and how many
# before the attacker prefers a seat on the far side of it. 0 disables.
#
# A Gunner fires along one fixed compass ray and rotating costs a flat 10 Ti, so
# a wall built to meet our approach covers that approach and nothing else.
# Ranked *below* the cover tier -- which is about surviving the seat at all --
# and above distance.
#
# Live vision cannot see a wall: a Builder at one face of a 2x2 Core sees the
# turrets on that face only, measured at at most 2 visible from every distance
# including zero, on maps carrying 8 and 10 enemy turrets. Two earlier versions
# read live vision, never fired once, and scored as clean rejections. Turrets do
# not move, so remembering them across turns is sound and it then fires 7-15
# times a game.
FLANK_MIN_TURRETS = 4
FLANK_RADIUS = 8
# Turrets bought purely to deny ground rather than to shoot anyone.
# --- Denial turrets ----------------------------------------------------------
# A turret bought to deny ground rather than to shoot anyone.
#
# Enemy bots route around our firing lines instead of walking down them, so a
# ray is a wall that costs 10 Ti and never has to fire. `_denial_gunner_site`
# scores a seat by how many *uncovered* Core-threat tiles its ray adds -- the
# same disc `_core_seal_targets` seals with barriers -- so a turret is bought
# only when it denies ground no existing one does.
#
# Measured on this chassis, with odin's own baseline taken in the same runs:
#
#                    pool          generated      pantheon   vigil_reinf
#     odin      313/336 0.932   135/160 0.844      33/42       29/42
#     +denial   314/336 0.935   142/160 0.887      33/42       31/42
#     +both     315/336 0.938   139/160 0.869      34/42       32/42  <- shipped
#
# Denial alone is the best generated-map score by a wide margin; with the flank
# it gives back three of those and takes the pool, Pantheon and the worst
# matchup instead. Shipped together because the binding constraint is the tail:
# this is the first build with Pantheon above 0.80, and warden_walk goes
# 0.81 -> 0.88 on the pool.
#
# Traced on quarry against the day3 Pantheon replica: 14 turrets, 69 rounds and
# a loss becomes 10 turrets, 59 rounds and a win. Fewer guns, sooner, because
# the ray does the work of a wall.
#
# The grace round matters for the usual reason -- before round 12 the guard's
# titanium belongs to the opening, and a turret there is a scale bill levied on
# the first Harvester.
# MEASURED AND ZERO under 2.3.4, on both metrics at once, which is rare here.
# 336 games a cell on the relay-0 base:
#
#     denial 1   0.711 / 0.571
#     denial 0   0.738 / 0.619   <- shipped
#
# +2.7pp of mean and +4.8pp of the worst matchup, and better against six of the
# eight opponents including both of the weak ones (prospect 0.571 -> 0.667,
# steward 0.595 -> 0.619).
#
# The mechanic was shipped three commits before the patch and its own note
# above is the reason it died: "a ray is a wall that costs 10 Ti and never has
# to fire". 2.3.4 made that wall cost 20 Ti and +20% permanent scale -- the
# same tax as a Sentinel -- for a turret explicitly bought never to shoot
# anyone. A wall you pay for every round of the rest of the game is not cheap
# ground denial, it is a mortgage on the round-1000 tiebreak.
DENIAL_GUNNERS = 0
DENIAL_MIN_TILES = 3
DENIAL_RESERVE = 30
DENIAL_START_ROUND = 12
REPAIR_ATTEMPT_LIMIT = 3
# How many of the Builder's own last tiles make a step less attractive in
# _move_while_stuck. 0 restores the memoryless greedy step, which oscillates
# forever on an unreachable goal. Ported from heimdall 4c0d92eb2 on the
# parallel session's measured handoff: on odin it is pool -1 / generated +2,
# and pacing falls 3.3% -> 0.4% of Builder-rounds (benchmarks/pathology.py).
TABU_WINDOW = 4
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
# MEASURED AND ZERO under 2.3.4. The relay chain has been in this lineage since
# Aug 1 and its cap was re-tuned to 2 as recently as heimdall, on numbers taken
# when a Gunner cost 10 Ti and +10% scale. Re-measured on this bot, 336 games a
# cell, as a full 2x2 with the ring:
#
#                    ring 1        ring 0
#     relay 2     0.696 / 0.548  0.685 / 0.619
#     relay 0     0.711 / 0.571  0.693 / 0.595
#
# Dropping the relay is +1.2pp of mean with no cost to the worst matchup, which
# makes it free. Dropping the ring is the opposite shape -- -1.5pp of mean for
# +4.75pp of worst matchup, concentrated on prospect and steward, the two
# weakest -- so the ring stays and this note records the trade in case the
# objective ever becomes the tail rather than the mean.
#
# The reason is the same one that keeps the attacker parked: a Launcher is a
# permanent +10% on every price the team pays afterwards, and under 2.3.4 the
# median game is decided by titanium collected at round 1000. Tempo bought with
# scale is a loan against the win condition.
MAX_RELAY_LAUNCHERS = 0

# Prefer Gunner seats outside every visible enemy turret's firing ray. A turret
# built where an enemy turret already points is shot before it has fired much,
# and the seat one tile off the ray usually reaches the same Core tile.
# Measured on the 21 official maps in both seats: against vigil@e267eeb it is
# 26/42 and 8 maps won 2-0, against 24/42 and 7 with it off; against
# ragnarok@79582fc it is unchanged at 26/42.
AVOID_ENEMY_RAYS = False
# --- Line-of-sight discipline -----------------------------------------------
# Lucas's constraint, 2026-08-04: never seat a turret where an enemy turret
# can already shoot it (tier 2), and prefer seats it cannot reach even by
# rotating (tier 0) over ones it could rotate onto (tier 1). Tier 2 is taken
# only when no tier 0/1 seat exists, and then under duel discipline: one such
# turret at a time, built *facing the covering turret* so it kills the threat
# before rotating on, with its Builder standing by healing it (4 HP for a
# flat 1 Ti out-paces the 10 dmg/round it takes) until the duel is decided.
COVER_TIER_SEATS = True
# Rounds the Builder will tend the duel before writing the position off.
DUEL_TEND_ROUNDS = 40

# --- Siege barriers ---------------------------------------------------------
# Barriers soaking enemy Gunner lanes aimed at our forward battery, out at the
# enemy Core. 3 Ti and +1% scale for 30 HP absorbs three Gunner rounds and six
# of their ammunition, which is titanium 1:1 -- the cheapest trade on the board
# and the one thing Pantheon does with barriers (31 of 33 across twenty games).
SIEGE_BARRIER_ENABLED = False
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
# Harvesters one trunk will carry before the Builder stops laying line.
#
# Four was measured on the pre-patch chassis. Re-measured on this one under
# 2.3.4: 4 -> 250/336, 6 -> 254, 8 -> 254. Six and eight are the same number,
# so six is shipped -- the extra Harvesters are +5% scale each and the cap
# stops binding before it reaches eight anyway. Worth taking because the
# round-1000 tiebreak is titanium collected and the wall sends far more games
# there: Core losses fall from 70 to 51 across these changes, and almost all
# of them become full-length games instead.
# Back to 4. Six came from mjolnir 67ed3ab1, measured with the twelve-tile wall
# on -- the one mechanic from that bot that was ruled out entirely -- and the
# wall is what sent those games to the round-1000 tiebreak that six was chosen
# to serve. Re-measured on this bot, 336 games a cell:
#
#     cap 6   0.738 / 0.619
#     cap 4   0.750 / 0.643   <- shipped
#
# Better on both metrics. One conveyor trunk carries one stack a round and a
# Harvester produces one every four, so four is where a trunk saturates: past
# it the extra Harvesters are +5% scale each for titanium that cannot move.
NETWORK_CAP_EARLY = 4
NETWORK_CAP_LATE = 8
ECON_EXPAND_ROUND = 120

# --- Ore re-targeting -------------------------------------------------------
# `_pick` chooses an ore under fog and the Builder then walks, often for twenty
# rounds, revealing ore the choice could not have known about. Committing
# anyway is how a Builder walks past a deposit four tiles away to finish
# reaching the one it picked at spawn.
#
# Re-picking is free until the first conveyor of the line is down; after that
# the tiles already paid for are sunk cost and the line gets finished. The
# margin exists so a one-tile improvement cannot make a Builder oscillate
# between two deposits and never mine either.
RETARGET_ORE = True
# Combined (walk + belt length) tiles the new deposit must beat the current
# one by. One conveyor is 3 Ti, one walk step is a round; the units are not
# the same thing, and treating them as equal is a deliberate simplification
# that only has to be good enough to rank two candidates.
RETARGET_MARGIN = 4
# Rounds between re-checks. Each one costs a BFS per surviving candidate.
RETARGET_INTERVAL = 3

# --- Belt line-of-sight -----------------------------------------------------
# Lucas's constraint, 2026-08-04: a conveyor inside an enemy turret's ray is
# destroyed as fast as it is rebuilt, and rebuilding it is the single most
# expensive habit this lineage has had. REPAIR_ATTEMPT_LIMIT caps the bleeding
# after the fact -- three rebuilds at 3 Ti and +1% scale each, then the tile is
# written off and the line replanned, which is 22 rebuilds better than the
# uncapped version but still nine Ti and a broken line.
#
# Not routing through the ray in the first place costs nothing. The detour is
# taken as a first-choice route and abandoned if it makes the ore unreachable,
# so a deposit that can only be reached through fire is still mined.
BELT_AVOID_ENEMY_RAYS = True
# Also avoid the seven facings a turret is not currently pointing. A rotation
# is 10 Ti to them and re-laying the belt is more than that to us, so a tile
# merely *reachable* by an enemy turret is a tile the belt should not want.
# Second preference: tried after the strict route and before the unrestricted
# one, so it never costs a deposit.
BELT_AVOID_ROTATION = True
# The same rule for the Launcher ring. With RING_MAX_SITES = 1 the ring is one
# Launcher and the sort decides which tile it lands on; the enemy-facing tile
# it preferred unconditionally is the one an enemy turret is most likely to be
# aimed at. Harvesters get no such flag: a Harvester goes on the ore or
# nowhere, so there is no alternative tile to prefer.
LAUNCHER_AVOID_ENEMY_RAYS = True

SLOT_BUILDER_TICKET = 0
# Bits 0-7 of SLOT_BUILDER_TICKET are the ticket itself. The Core spends the
# rest publishing the two ore deposits nearest its own footprint, packed with
# pack_pos, so the opening miners walk at ore the Core can see instead of
# discovering it a tile at a time. The bit layout lives in utils next to
# pack_pos; only the policy is here.
# Publish the Core's own ore sightings to the opening miners.
ORE_HINTS = True
# Two 10-bit positions is 20 bits; with the 8-bit ticket that is 28 of 32, so
# full-resolution coordinates fit and the coarse 2x2 fallback is not needed.
ORE_HINT_COUNT = 2
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
# Bit 3 of SLOT_CORE_DAMAGED: at the damage rate of the last PROJECT_WINDOW
# rounds the Core is dead within PROJECT_HORIZON rounds. Traced on jackpot vs
# ragnarok: the guard Builder died on round 143, the only survivor was the
# attacker across the map, and the Core took 10-20 a round from 157 to 192
# with 762 titanium banked -- rich, undefended, and dead. A Builder spawned
# under this flag becomes a home defender, the same conditional-respawn shape
# that made the income watchdog work where unconditional refill lost 30pp.
CORE_DYING_FLAG = 8
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

# --- Standoff seating for the siege battery ---------------------------------
# Rank siege seats by whether a remembered enemy turret can reach them before
# ranking them by how soon the Builder arrives.
#
# The Sentinel reaches r^2=32 and a Gunner reaches r^2=13, so the annulus
# between the two is ground from which we shoot their Core and nothing they
# own can shoot back -- not on its current facing and not after a 10 Ti
# rotation. `_remembered_turret_cover`'s tier 0 is exactly that set. The old
# sort keyed on walk distance first, and next to a defended Core the nearest
# reachable seat is the one deepest inside their fire.
SIEGE_COVER_TIER = True

# --- Starving the economy ----------------------------------------------------
# Let Sentinels shoot enemy buildings, and give up on a Core they cannot
# out-damage.
#
# Buildings are not units, so they never appear in `get_nearby_entities`, and
# every Sentinel this lineage has ever built has been blind to the enemy
# economy: with no unit on the line it simply held its fire. Under 2.3.4 that
# is the wrong silence. Defence is about 2.2x more titanium-efficient than
# offence -- a mender restores 4 HP for a flat 1 Ti against a Sentinel's 6
# damage for 3.33 -- so most games run to round 1000 and are decided on
# titanium collected, then live Harvesters, then titanium stored. Every one of
# those three is made of the buildings a Sentinel was ignoring.
STARVE_THE_ECONOMY = True
# Rounds of firing at a Core whose HP has not fallen before the battery gives
# up on it and turns to the supply line. Two menders restore 8 HP a round
# against a two-Sentinel battery's 12 and one restores 4 against a single
# Sentinel's 6, so a Core that has stopped losing HP under fire is not slow,
# it is held -- and it will be full again before we come back to it.
SIEGE_STALL_ROUNDS = 12

# --- Late economy expansion --------------------------------------------------
# Spawn Builders for income once a game is clearly going to be decided by
# income.
#
# Past the opening this Core only ever replaced the dead -- income_dead or
# core_dying, both emergencies. Under 2.3.4 that leaves the actual win
# condition unfunded: a mender restores 4 HP for a flat 1 Ti against a
# Sentinel's 6 damage for 3.33, so defence is about 2.2x more efficient than
# offence, Cores mostly do not die, and the median game reaches round 1000
# where the first tiebreak criterion is titanium collected.
#
# This does not overturn the headcount-of-three finding, which was about the
# opening and still holds: an opening Builder levies +20% on the Launchers and
# Harvesters the opening has not bought yet. The same +20% levied at round 250
# falls almost entirely on conveyors at 3 Ti, so it costs 0.6 Ti a tile against
# the 2.5 Ti a round a connected Harvester returns for the rest of the game.
ECON_EXPAND_BUILDERS = True
# Late enough that the opening blitz has demonstrably not ended the game, and
# early enough that a new Harvester still has most of the match to pay back.
ECON_BUILDER_ROUND = 200
ECON_MAX_LIVE_BUILDERS = 7
ECON_MAX_TOTAL_BUILDERS = 12
# Only genuine surplus. A Builder is 30 Ti before scale and this holds back
# roughly a Harvester and the belt to reach it on top of the Builder itself,
# so expanding never takes the titanium the existing miners are waiting on.
ECON_EXPAND_RESERVE = 120
# Bit 4 of SLOT_CORE_DAMAGED: the expansion regime is open, so a Builder
# spawned past the opening is a miner rather than the attacker the spawn-order
# role table would otherwise make it. Same shape as ECONOMY_DEAD_FLAG.
ECON_EXPAND_FLAG = 16
# A Builder with no deposit left to claim harasses instead of walking the
# exploration lattice for the rest of the game. The existing harass fallback is
# keyed on the Builder's *own* network_load, which is zero for one the Core
# spawned late, so the surplus miners never reached it.
HARASS_WHEN_UNEMPLOYED = True
# Rounds a Builder will wait for the construction lock before laying anyway.
# The holder refreshes its lease every round it is laying, so with seven
# Builders the queue behind one long belt is the rest of the game: traced on
# quarry, one Builder idled 582 rounds of 750. Colliding is a cheaper failure
# than never laying.
LOCK_WAIT_LIMIT = 40
