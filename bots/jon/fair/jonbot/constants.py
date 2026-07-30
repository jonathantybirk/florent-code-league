"""Shared constants and communication layout for Jonbot."""

from fcode import Direction, EntityType

D8 = tuple(d for d in Direction if d != Direction.CENTRE)
D4_DELTAS = ((0, -1), (1, 0), (0, 1), (-1, 0))
FACING = dict(zip(D4_DELTAS, (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)))
WALKABLE_BUILDINGS = (EntityType.CONVEYOR, EntityType.SPLITTER)

SLOT_BUILDER_TICKET = 0
CLAIM_SLOTS = range(1, 9)
SLOT_SYMMETRY_REJECT_START = 9  # slots 9..10, one writer per opening Builder
SLOT_CONSTRUCTION_LOCK = 11
SLOT_ENEMY_CORE = 13
SLOT_SYMMETRY_MASK = 14         # reserved for a future Core-published aggregate
SLOT_ALERT = 15
MAX_OPENING_BUILDERS = 3
