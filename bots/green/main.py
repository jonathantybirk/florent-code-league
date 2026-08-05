import random

from fcode import Controller, Direction, EntityType, Environment, Position

from toolbox import (
    DIRECTIONS,
    StuckTracker,
    auto_fire,
    read_position,
    share_ore,
    try_build_conveyor_facing,
    try_build_conveyor_toward,
    try_build_gunner_facing,
    try_build_harvester_on_ore,
    try_heal_adjacent,
    try_move_toward,
    try_spawn_builder,
    write_position,
)

# --- Communication store slot assignments ---
# The store has 16 slots (indices 0-15), each holding a u32 value.
# Writes are buffered: a write_store() call becomes visible to all units
# at the start of the *next* round.
SLOT_CORE = 0
SLOT_HARVESTER_COUNT = 1
SLOT_ORE_LOCATION = 2

# How many builder bots the core will spawn over the course of the game
MAX_BUILDERS = 1

# How many harvesters we want before switching builder bots to defense duty
TARGET_HARVESTERS = 3


class Player:
    def __init__(self):
        # Core tracks how many builder bots it has spawned
        self.num_spawned = 0

        # Builder bot navigation state
        self.target: Position | None = None   # where we're trying to walk to
        self.stuck = StuckTracker()

        # Cached core position (read from the store once, then reused)
        self.core_pos: Position | None = None

    def run(self, ct: Controller) -> None:
        """Entry point called by the engine every round for each unit.

        We check what type of entity we are and dispatch to the right handler.
        Each entity type (core, builder bot, gunner) has its own run logic.
        """
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)
        elif etype == EntityType.GUNNER:
            self._run_gunner(ct)

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def _run_core(self, ct: Controller) -> None:
        """Core logic: publish our position so builder bots can orient toward us,
        then try to spawn a builder bot each round until we hit the cap.
        """
        # Write our position into the store every round so newly spawned bots
        # can read it. Store writes are buffered — they become visible next round.
        write_position(ct, SLOT_CORE, ct.get_position())

        # Don't spawn more than MAX_BUILDERS total
        if self.num_spawned >= MAX_BUILDERS:
            return

        if try_spawn_builder(ct) is not None:
            self.num_spawned += 1

    # ------------------------------------------------------------------
    # Builder bot
    # ------------------------------------------------------------------

    def _run_builder(self, ct: Controller) -> None:
        """Builder bot logic, executed each round. Priority order:
        1. Build a harvester if adjacent to uncovered ore
        2. Build a gunner if we already have enough harvesters
        3. Heal any damaged friendly buildings nearby
        4. Move toward the next target (ore or exploration)
        5. Broadcast any visible ore to teammates via the store
        """
        pos = ct.get_position()

        # On our first turn, read the core's position from the store.
        # We cache it so we don't have to read every round.
        if self.core_pos is None:
            self.core_pos = read_position(ct, SLOT_CORE)

        # Stuck detection: if we haven't moved in 3 rounds, we'll pick a new
        # target in _move_toward_target to avoid getting permanently stuck.
        self.stuck.update(pos)

        # --- Build phase (requires action cooldown == 0) ---
        # Try to build a harvester first; if none available, consider a gunner
        if ct.get_action_cooldown() == 0:
            if not self._try_build_harvester(ct):
                # Only build gunners once our economy is up (enough harvesters)
                harvester_count = ct.read_store(SLOT_HARVESTER_COUNT)
                if harvester_count >= TARGET_HARVESTERS:
                    self._try_build_gunner(ct)

        # If we still have an action left (didn't build anything), heal nearby
        if ct.get_action_cooldown() == 0:
            try_heal_adjacent(ct)

        # --- Move phase (requires move cooldown == 0) ---
        self._move_toward_target(ct)

        # --- Communication phase (no cooldown needed) ---
        # Share any visible ore location with teammates
        share_ore(ct, SLOT_ORE_LOCATION)

    def _try_build_harvester(self, ct: Controller) -> bool:
        """Try to build a harvester on an adjacent ore tile, then start
        routing its output toward the core with a conveyor.
        """
        build_pos = try_build_harvester_on_ore(ct)
        if build_pos is None:
            return False

        # Update the shared harvester counter so other bots know
        count = ct.read_store(SLOT_HARVESTER_COUNT)
        ct.write_store(SLOT_HARVESTER_COUNT, count + 1)

        # Try to add a conveyor next to the harvester to route resources
        if self.core_pos is not None:
            try_build_conveyor_toward(ct, build_pos, self.core_pos)

        # Clear our target so we move on instead of lingering near this
        # harvester. Without this the bot would try to walk onto the
        # (non-passable) harvester tile for 3 rounds before stuck
        # detection finally kicks in.
        self.target = None
        return True

    def _try_build_gunner(self, ct: Controller) -> bool:
        """Build a gunner turret on an adjacent tile, facing away from the core.

        Gunners fire in a straight line in their facing direction, so pointing
        them outward from the core gives them the best chance of hitting
        approaching enemies. We only build if we're close to the core
        (within ~4 tiles) so gunners end up defending the base.

        Note: gunners need ammo delivered via conveyors to fire. This starter
        bot doesn't set up ammo supply — that's an exercise for the player!
        """
        if self.core_pos is None:
            return False

        pos = ct.get_position()
        # Face the gunner away from the core (toward incoming enemies)
        facing = pos.direction_to(self.core_pos).opposite()
        if facing == Direction.CENTRE:
            facing = random.choice(DIRECTIONS)

        return try_build_gunner_facing(ct, facing, near=self.core_pos, max_dist_sq=18) is not None

    # ------------------------------------------------------------------
    # Builder bot — movement
    # ------------------------------------------------------------------

    def _move_toward_target(self, ct: Controller) -> None:
        """Navigate toward our current target, picking a new one if needed.

        Target priority: visible ore > ore shared via store > random position.
        If we've been stuck for 3+ rounds, we give up on the current target
        and pick a fresh one.
        """
        if ct.get_move_cooldown() != 0:
            return

        pos = ct.get_position()

        # Pick a new target if we don't have one, reached it, or are stuck
        if self.target is None or pos == self.target or self.stuck.stuck_rounds >= 3:
            self.target = self._pick_target(ct)
            self.stuck.stuck_rounds = 0
        if self.target is None:
            return

        try_move_toward(
            ct, self.target,
            before_step=lambda next_pos: self._lay_conveyor_while_walking(ct, next_pos),
        )

    def _lay_conveyor_while_walking(self, ct: Controller, next_pos: Position) -> None:
        """Opportunistically drop a conveyor toward the core on any tile
        we're about to step onto -- doubles our walking paths as part of
        the resource network. Optional, not required for movement.
        """
        if self.core_pos is not None:
            try_build_conveyor_facing(ct, next_pos, self.core_pos)

    def _pick_target(self, ct: Controller) -> Position:
        """Choose the next position to navigate toward.

        Priority:
        1. Closest visible ore tile without a harvester on it — go build one
        2. If economy is established (enough harvesters), head back toward
           the core so we can build gunners for defense
        3. Ore location shared by a teammate via the store — head that way
        4. Random map position — pure exploration
        """
        pos = ct.get_position()

        # 1. Scan visible tiles for the nearest uncovered ore
        best_ore = None
        best_dist = float("inf")
        for tile in ct.get_nearby_tiles():
            if ct.get_tile_env(tile) != Environment.ORE_TITANIUM:
                continue
            # Skip ore that already has a building (harvester or otherwise) on it
            if ct.get_tile_building_id(tile) is not None:
                continue
            d = pos.distance_squared(tile)
            if d < best_dist:
                best_dist = d
                best_ore = tile
        if best_ore is not None:
            return best_ore

        # 2. Once we have enough harvesters, head back to the core so we can
        #    build gunners nearby.  _try_build_gunner requires being within
        #    distance² 18 of the core, so we navigate there.
        harvester_count = ct.read_store(SLOT_HARVESTER_COUNT)
        if harvester_count >= TARGET_HARVESTERS and self.core_pos is not None:
            if pos.distance_squared(self.core_pos) > 8:
                return self.core_pos

        # 3. Check the store for an ore location shared by a teammate
        shared = read_position(ct, SLOT_ORE_LOCATION)
        if shared is not None and pos.distance_squared(shared) > 4:
            return shared

        # 4. No known ore — pick a random position to explore
        w, h = ct.get_map_width(), ct.get_map_height()
        return Position(random.randrange(w), random.randrange(h))

    # ------------------------------------------------------------------
    # Gunner
    # ------------------------------------------------------------------

    def _run_gunner(self, ct: Controller) -> None:
        """Gunner logic: fire at the first enemy in our line of sight."""
        auto_fire(ct)
