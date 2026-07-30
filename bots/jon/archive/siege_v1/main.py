"""Custom bot — economy-first strategy with light defense.

Each unit gets its own Player instance; the engine calls run() once per round.
Use ct.get_entity_type() to branch on what kind of unit you are.

Strategy:
  1. Core spawns builder bots and publishes its position via the store
  2. Builder bots explore, build harvesters on ore, and lay conveyors toward
     the core so titanium flows back automatically
  3. Once the economy is running (3+ harvesters), builder bots place gunners
     near the core for defense
  4. Gunners auto-fire at the closest visible enemy

Entity types used:  Core, Builder Bot, Harvester, Conveyor, Gunner

Layout — every file in a submission is importable, so the logic is split up:
  main.py       this file: per-unit state and the entity-type dispatch
  core.py       core behaviour
  builder.py    builder bot behaviour
  gunner.py     gunner behaviour
  constants.py  store slots and strategy tuning knobs
  utils.py      small stateless helpers

Unit modules expose run(player, ct): the Player instance is passed in as the
first argument (in place of `self`) so state stays on Player while behaviour
lives in the per-unit file.

Communication store slots (see constants.py):
  0  SLOT_CORE_X          Core X position (written by core on round 1)
  1  SLOT_CORE_Y          Core Y position
  2  SLOT_HARVESTER_COUNT Total harvesters built by the team
  3  SLOT_ORE_LOCATION    Packed (x, y) of an uncovered ore tile
  Slots 4-15 are free — use them for your own coordination logic.

Ideas for improvement:
  - Build full conveyor chains from distant harvesters back to the core
  - Feed ammo to gunners via conveyors so they can actually fire
  - Add sentinels or launchers for stronger defense
  - Explore the map systematically instead of picking random targets
  - Use more store slots to coordinate roles between builder bots
"""

import builder
import core
import gunner
import sentinel
from fcode import Controller, EntityType, Position

# Which module handles which entity type. Add an entry here when you start
# building a new unit type (sentinels, launchers, splitters, ...).
HANDLERS = {
    EntityType.CORE: core.run,
    EntityType.BUILDER_BOT: builder.run,
    EntityType.GUNNER: gunner.run,
    EntityType.SENTINEL: sentinel.run,
}


class Player:
    """Per-unit state. One instance per entity, kept alive across rounds."""

    def __init__(self):
        # Core: how many builder bots it has spawned
        self.num_spawned = 0

        # Builder bot navigation state
        self.target: Position | None = None    # where we're trying to walk to
        self.last_pos: Position | None = None  # position last round (for stuck detection)
        self.stuck = 0                         # consecutive rounds without moving

        # Cached core position (read from the store once, then reused)
        self.core_pos: Position | None = None

        # Economy-only opening state.
        self.role: int | None = None
        self.ore_target: Position | None = None
        self.harvester_pos: Position | None = None
        self.phase = "explore"
        self.route_seen: set[Position] = set()
        self.coverage_mask = 0
        self.deposits_built = 0
        self.target_started_round = 0
        self.defense_anchor: Position | None = None
        self.defense_direction = None
        self.gunners_built = 0
        self.attack_core: Position | None = None
        self.attack_ore: Position | None = None
        self.attack_candidate = 0
        self.attack_turrets_built = 0
        self.attack_direct = False
        self.attack_confirmed_round = 0
        self.attack_viable_round = 0
        self.threat_until = 0

    def run(self, ct: Controller) -> None:
        """Entry point called by the engine every round for each unit.

        Dispatches to the handler for whatever type of entity we are; unit
        types without a handler simply do nothing this round.
        """
        handler = HANDLERS.get(ct.get_entity_type())
        if handler is not None:
            handler(self, ct)
