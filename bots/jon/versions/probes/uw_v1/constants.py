"""Shared constants and communication layout for Undertow."""

from fcode import Direction, EntityType

D8 = tuple(d for d in Direction if d != Direction.CENTRE)
D4_DELTAS = ((0, -1), (1, 0), (0, 1), (-1, 0))
D8_DELTAS = ((0, -1), (1, -1), (1, 0), (1, 1),
             (0, 1), (-1, 1), (-1, 0), (-1, -1))
FACING = dict(zip(D4_DELTAS, (Direction.NORTH, Direction.EAST,
                              Direction.SOUTH, Direction.WEST)))
FACING8 = {
    (0, -1): Direction.NORTH, (1, -1): Direction.NORTHEAST,
    (1, 0): Direction.EAST, (1, 1): Direction.SOUTHEAST,
    (0, 1): Direction.SOUTH, (-1, 1): Direction.SOUTHWEST,
    (-1, 0): Direction.WEST, (-1, -1): Direction.NORTHWEST,
}
WALKABLE_BUILDINGS = (EntityType.CONVEYOR, EntityType.SPLITTER)

# A Gunner turns 1 Ti of delivered ammunition into 5 damage, so a siege is
# throughput-limited: one forward Harvester (2.5 Ti/round) sustains roughly
# 12.5 damage/round, i.e. a 500 HP Core in 40 rounds.
GUNNER_RANGE_SQ = 13
LAUNCH_RANGE_SQ = 26

# Three Builders coordinate extraction; a fourth stays home as the picket and
# repair engineer. Rich-reserve Builders become the delayed counterattack.
ECONOMY_BUILDERS = 3
OPENING_HOME_BUILDERS = 4

SLOT_BUILDER_TICKET = 0
CLAIM_SLOTS = range(1, 6)        # home ore claims
SLOT_LAUNCH_ID = 6               # Builder id asking to be thrown
SLOT_ENEMY_CORE = 7
SLOT_SYMMETRY_A = 8              # rejected-symmetry mask, writer = ticket 0
SLOT_SYMMETRY_B = 9              # rejected-symmetry mask, writer = ticket 1
SIEGE_SLOTS = range(10, 12)      # forward deposits, one claim per attacker
PICKET_SLOTS = range(12, 14)     # packed positions of defensive Launchers
SLOT_ECON_LINES = 14
SLOT_HOME_UNDER_FIRE = 15

# How far from the enemy Core a deposit may sit and still be worth mining for
# ammunition, and how long a forward conveyor creep may get before the battery
# costs more than it delivers.
# A Gunner must sit within about three tiles of the Core and touch its
# feeder, so a forward deposit further out than this can never supply one
# directly and only earns its cost through a conveyor creep.
SIEGE_ORE_RADIUS = 4
# Fallback reach when nothing sits close to their Core at all.
SIEGE_ORE_FAR = 10

# Launcher hops per attacker, and the range at which walking is faster than
# paying 20 Ti to be thrown.
LAUNCH_HOPS = 2
LAUNCH_MIN_GAP = 8

# The Core spawns Builders onto its own ring, so it must finish the opening
# before we brick that ring up.
FORTIFY_ROUND = 5


# How far from our Core a damaged building is still worth a Builder's round.
# A belt cut beyond the repair crew's reach is severed for good, and a
# purpose-built raider (`probes/reaver`) exploited exactly that: it cut
# lines past the old radius of 4 and out-delivered us four to one.
REPAIR_RADIUS = 7

# Below this share of its hit points the Core outranks everything else.
CORE_PANIC_PERCENT = 55

# Core health below which the whole team switches to defending it.
HOME_ALARM_PERCENT = 85

# Bank above which the Core buys emergency repair crew without hesitation.
EMERGENCY_RESERVE = 120

# Bank above which standing still costs more than the cost scale does.
RICH_RESERVE = 300

# Bank above which a Builder may pay for a long home supply belt.
LONG_LINE_RESERVE = 100000

# Rounds spent failing to reach a firing position before trying another.
BLOCKED_TILE_PATIENCE = 6
SIEGE_LINE_MAX = 8

PICKET_LAUNCHERS = 2

HOME_THREAT_RADIUS = 10
