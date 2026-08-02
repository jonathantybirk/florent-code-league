"""Shared constants and communication layout for Jonbot."""

from fcode import Direction, EntityType

D8 = tuple(d for d in Direction if d != Direction.CENTRE)

# What a shot is worth, by what it lands on. Weights rather than a strict order
# so the ranking can be tuned without rewriting the comparison: a turret one
# tile away can still outrank a Core across the map, because distance breaks
# ties and unreachable targets never enter the list at all.
TARGET_VALUE = {
    EntityType.CORE: 100,
    EntityType.GUNNER: 60,
    EntityType.SENTINEL: 55,
    EntityType.LAUNCHER: 45,
    EntityType.BUILDER_BOT: 40,
    EntityType.HARVESTER: 20,
    EntityType.SPLITTER: 10,
    EntityType.CONVEYOR: 5,
    EntityType.BARRIER: 1,
}
D4_DELTAS = ((0, -1), (1, 0), (0, 1), (-1, 0))
FACING = dict(zip(D4_DELTAS, (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)))
WALKABLE_BUILDINGS = (EntityType.CONVEYOR, EntityType.SPLITTER)

# One Builder per job: mine, defend, attack. Every Builder Bot adds +20% to
# every build cost the team will ever pay -- the largest single term in cost
# scaling -- so a spare Builder is not free labour, it is a permanent tax on
# the Launchers and Harvesters it was spawned to help build. Six of them took
# the Launcher price from 20 Ti to 44 before the first one went up.
ECONOMY_BUILDERS = 1
SCOUT_BUILDERS = 1
LAUNCHER_BUILDERS = 1
LAUNCHER_BUILDER_INDEX = ECONOMY_BUILDERS + SCOUT_BUILDERS
MAX_OPENING_BUILDERS = ECONOMY_BUILDERS + SCOUT_BUILDERS + LAUNCHER_BUILDERS

# Drop a ring direction when the map edge is this close behind it: nothing can
# approach from off the map, so a Launcher there guards nothing and still costs
# its +10%.
RING_EDGE_MARGIN = 5
# Tiles between the Core footprint and the ring. Launchers block movement, so
# at radius 1 the ring sits on the tiles a conveyor line has to cross to reach
# the Core. Radius 2 leaves that lane open, and a Builder standing on the shell
# between the two is still diagonally adjacent to the ring site, so it remains
# inside the Launcher's pickup radius.
# The reasoning behind RING_COVER_SHELL is sound and the implementation is
# verified: a Gunner reaches 3 tiles and a Builder builds one step from itself,
# so an enemy standing 4 out can plant a turret 3 out and shoot the Core, and
# _shell_cover_targets returns a set of Launcher sites whose pickup zones cover
# that entire shell -- 13/13 tiles on a corner Core, 36/36 on an open one.
#
# It is off because denying that shell with Launchers costs more than the
# attack does. A cover needs 5 sites in a corner and 13 in the open, at 20 Ti
# and +10% scale each; against tempest_reinforcements it scores 20/42 where the
# cheap radius-2 compass ring scores 26/42, and 22 against prospect where the
# compass ring scores 27. Denying the shell with barriers instead is what
# CORE_SEAL_ENABLED does, at 3 Ti and +1% a tile.
RING_COVER_SHELL = True
# Two geometries, two radii, kept separate so flipping the switch cannot leave
# the cover computing against the compass ring's shell.
RING_SHELL_RADIUS = 4   # distance denied by _shell_cover_targets
RING_RADIUS = 2         # where _compass_ring_targets puts its Launchers

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
# Off, on measurement. The seal is correct -- a flood fill from the map edge
# reaches none of the tiles an enemy could shoot the Core from -- but it costs
# five games out of 126 against mistral_fast / mistral / vanguard_oracle,
# 119 with it off against 114 with it on. Those games end around turn 30 and
# the ring Builder lays roughly one barrier per game before the game is over,
# so the perimeter is paid for and never finished, and while it is half-built
# it walls our own economy Builder in as readily as it walls them out.
#
# Kept rather than deleted because the ladder is not this pool: Pantheon's
# wins in match 0a9a756d run 162, 310, 321 and 409 turns, which is the regime
# where a perimeter has time to close. Turn back on to test that.
CORE_SEAL_ENABLED = False

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
# Field Gunners a single Builder will put up away from home, on enemies met
# anywhere including unclaimed ground.
#
# Shipped at 0, i.e. off, against expectation. Measured over the 21 official
# maps in both orders it costs 3 games out of 42 against mistral_fast at a cap
# of 3, and still 1 at a cap of 1, so the cap is not the problem -- answering a
# roaming enemy with a building trades a mobile Builder's turn plus a permanent
# +10% for a turret the enemy simply walks away from. It is left implemented
# because that measurement is against our own pool, not against the ladder bots
# the behaviour was copied from; raise this to switch it back on.
# On, at a small cap. An enemy standing on a deposit is not a pathing problem
# to route around -- the Builder simply never mines it -- and a turret is the
# only answer a Builder has to a unit.
MAX_FIELD_GUNNERS = 2
# How far an attacker will walk to put its escape Launcher on a ring site
# rather than underfoot. Far enough to reach the ring from the Core, short
# enough that it is not a trek back home from the far side of the map.
ESCAPE_RING_DETOUR = 6

# Other Builders move. Treating one as terrain and going around it immediately
# is impatience: the detour is paid for certain, the obstruction usually is not
# there next tick. How long to hold depends on what going around would cost.
BOT_DETOUR_TOLERANCE = 2    # extra steps taken without waiting at all
BOT_WAIT_DETOUR = 1         # ticks held when a cheap way round exists
BOT_WAIT_REPLAN = 3         # ticks held when going around means a new plan

# How far an attacker will walk to reach a Launcher it remembers. A throw
# covers up to sqrt(26) tiles, so a detour of a few tiles still pays.
LAUNCHER_HOP_WALK = 5
# A throw is not free in tempo. Store writes are invisible to other units until
# the next round, so a request written this round is first readable by the
# Launcher next round: the passenger loses the round it announces in and the
# round it stands waiting to be picked up. Any comparison against simply
# walking has to carry that.
LAUNCH_OVERHEAD_ROUNDS = 2
# Throw radius squared is 26, so a throw advances at most five tiles.
LAUNCH_REACH = 5

SLOT_BUILDER_TICKET = 0
# There is one economy Builder, so one ore reservation is sufficient. Slots
# 2..8 are stable per-Builder Launcher requests and cannot overwrite each other.
CLAIM_SLOTS = range(1, 2)
LAUNCH_REQUEST_SLOTS = range(2, 9)
# A request carries the passenger's actual destination, not a compass bearing.
# A bearing was only eight directions wide, and the Launcher answered it by
# throwing as far along that bearing as it could reach -- which for any target
# not exactly on a compass line often landed the passenger further from where
# it was going than where it started.
LAUNCH_TARGET_BITS = 11
LAUNCH_TARGET_MASK = (1 << LAUNCH_TARGET_BITS) - 1
LAUNCH_REJECTION_FLAG = 1 << 31
LAUNCH_REJECTION_POSITION_BITS = 11
LAUNCH_REJECTION_POSITION_MASK = (1 << LAUNCH_REJECTION_POSITION_BITS) - 1
SLOT_SYMMETRY_REJECT_START = 9  # slots 9..10, one writer per opening Builder
SLOT_CONSTRUCTION_LOCK = 11
SLOT_CORE_DAMAGED = 12
SLOT_ENEMY_CORE = 13
SLOT_OWN_CORE = 14
SLOT_BUILDER_HEARTBEAT = 15
# Rounds of failed pathing before a Builder is written off as unable to act.
STUCK_ROUNDS_BEFORE_STANDDOWN = 40
# Rounds blocked before spending a Launcher to jump the blockage outright.
BLOCKED_ROUNDS_BEFORE_LAUNCHER = 5
# A Harvester this close is worth finishing before turning back to repairs:
# four ores in a cluster should not each trigger a trip back down the line.
HARVESTER_FINISH_STEPS = 2

LAUNCH_RANGE_SQ = 26

# Enemy turret coverage, for pathing that weighs damage instead of banning it.
# A Gunner deals 10 a shot and reloads every round; a Sentinel deals 18 every
# three, so six a round, and its line cannot be blocked by anything standing in
# the way.
SENTINEL_RANGE_SQ = 32
GUNNER_DAMAGE_PER_ROUND = 10
SENTINEL_DAMAGE_PER_ROUND = 6
# Leave this much health spare rather than arriving on fumes.
FIRE_SURVIVAL_MARGIN = 10
