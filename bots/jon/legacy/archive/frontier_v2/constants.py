"""Store slot assignments and custom strategy tuning knobs.

These live in their own module so every unit handler can import them without
importing main.py (which imports the handlers — that would be a cycle).
"""

from fcode import Direction

# All directions except CENTRE — useful for movement and spawning
DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

# Conveyors and splitters can only face cardinal directions, so diagonals snap
# to the cardinal they're closest to.
NEAREST_CARDINAL = {
    Direction.NORTH: Direction.NORTH,
    Direction.NORTHEAST: Direction.NORTH,
    Direction.EAST: Direction.EAST,
    Direction.SOUTHEAST: Direction.EAST,
    Direction.SOUTH: Direction.SOUTH,
    Direction.SOUTHWEST: Direction.SOUTH,
    Direction.WEST: Direction.WEST,
    Direction.NORTHWEST: Direction.WEST,
    Direction.CENTRE: Direction.NORTH,
}

# Four early collectors are cheap enough to leave ample starting titanium for
# harvesters and belts. The core publishes the entity id assigned to each role.
BUILDER_COUNT = 6
DEFENDER_ROLES = (3, 4)
# The first bot is deliberately a collector.  Two later scouts test the two
# axis-reflection hypotheses while the economy comes online behind them.
ATTACKER_ROLES = (0, 1)
DEFENSE_DEPOSIT_THRESHOLD = 3
ATTACK_RESERVE_TITANIUM = 40
SLOT_CORE_POSITION = 0
SLOT_LATEST_ASSIGNMENT = 1
SLOT_TARGET_CLAIM_START = 2       # slots 2..7, one leased target per builder
SLOT_COVERAGE_START = 8           # slots 8..13, one map mask per builder
SLOT_STRATEGY = 14                 # packed relay-attacker entity IDs
SLOT_ENEMY_REPORT = 15

SECTOR_GRID_SIZE = 5
SECTOR_COUNT = SECTOR_GRID_SIZE * SECTOR_GRID_SIZE
SECTOR_MASK = (1 << SECTOR_COUNT) - 1
DEPOSIT_COUNT_MASK = 0x1F
SYMMETRY_REJECT_SHIFT = 30
CLAIM_LEASE_ROUNDS = 12

# Rounds without moving before we give up on the current target
STUCK_LIMIT = 3
