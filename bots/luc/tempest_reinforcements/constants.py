"""Shared constants and communication layout for Jonbot."""

from fcode import Direction, EntityType

D8 = tuple(d for d in Direction if d != Direction.CENTRE)
D4_DELTAS = ((0, -1), (1, 0), (0, 1), (-1, 0))
FACING = dict(zip(D4_DELTAS, (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)))
WALKABLE_BUILDINGS = (EntityType.CONVEYOR, EntityType.SPLITTER)

ECONOMY_BUILDERS = 1
SCOUT_BUILDERS = 3
LAUNCHER_BUILDERS = 1
LAUNCHER_BUILDER_INDEX = ECONOMY_BUILDERS + SCOUT_BUILDERS
MAX_OPENING_BUILDERS = ECONOMY_BUILDERS + SCOUT_BUILDERS + LAUNCHER_BUILDERS

SLOT_BUILDER_TICKET = 0
# There is one economy Builder, so one ore reservation is sufficient. Slots
# 2..8 are stable per-Builder Launcher requests and cannot overwrite each other.
CLAIM_SLOTS = range(1, 2)
LAUNCH_REQUEST_SLOTS = range(2, 9)
LAUNCH_DIRECTION_BITS = 4
LAUNCH_DIRECTION_MASK = (1 << LAUNCH_DIRECTION_BITS) - 1
SLOT_SYMMETRY_REJECT_START = 9  # slots 9..10, one writer per opening Builder
SLOT_CONSTRUCTION_LOCK = 11
SLOT_CORE_DAMAGED = 12
SLOT_ENEMY_CORE = 13
SLOT_OWN_CORE = 14
SLOT_BUILDER_HEARTBEAT = 15

LAUNCH_RANGE_SQ = 26
