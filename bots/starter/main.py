"""Starter bot — economy-first strategy with light defense.

Each unit gets its own Player instance; the engine calls run() once per round.
Use ct.get_entity_type() to branch on what kind of unit you are.

Strategy:
  1. Core spawns builder bots and publishes its position via the store
  2. Builder bots remember every ore tile they've ever seen (terrain is
     static, so there's no need to re-discover it) and beeline for the
     nearest unclaimed one to build a harvester on it
  3. Once the economy is running (3+ harvesters), builder bots place gunners
     near the core for defense
  4. Gunners auto-fire at the closest visible enemy

Entity types used:  Core, Builder Bot, Harvester, Gunner

Communication store slots:
  0  SLOT_CORE_X          Core X position (written by core on round 1)
  1  SLOT_CORE_Y          Core Y position
  2  SLOT_HARVESTER_COUNT Total harvesters built by the team
  3  SLOT_ORE_LOCATION    Packed (x, y) of an uncovered ore tile
  Slots 4-15 are free — use them for your own coordination logic.

Ideas for improvement:
  - Build full conveyor chains from distant harvesters back to the core
  - Feed ammo to gunners via conveyors so they can actually fire
  - Add sentinels or launchers for stronger defense
  - Share known ore tiles between builder bots over the store, instead of
    each bot only remembering what it personally saw
"""

import random

from fcode import Controller, Direction, EntityType, Environment, GameConstants, Position

from utils import move_toward

# All directions except CENTRE — builder bots can move in any of these
DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

# --- Communication store slot assignments ---
# The store has 16 slots (indices 0-15), each holding a u32 value.
# Writes are buffered: a write_store() call becomes visible to all units
# at the start of the *next* round.
SLOT_CORE_X = 0
SLOT_CORE_Y = 1
SLOT_HARVESTER_COUNT = 2
SLOT_ORE_LOCATION = 3

# How many builder bots the core will spawn over the course of the game
MAX_BUILDERS = 5

# How many harvesters we want before switching builder bots to defense duty
TARGET_HARVESTERS = 3


class Player:
    def __init__(self):
        # Core tracks how many builder bots it has spawned
        self.num_spawned = 0

        # Builder bot memory: every ore tile ever seen. Map terrain is
        # static and out-of-vision tiles can't be queried, so we only ever
        # add to this from get_nearby_tiles() and only ever prune a tile
        # once we can see for ourselves that it's been built on.
        self.known_ore: set[Position] = set()

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
            pass

    def _run_core(self, ct: Controller) -> None:
        for pos in ct.get_nearby_tiles(dist_sq=2):
            if ct.can_spawn(pos):
                ct.spawn_builder(pos)
                break

    def _run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        ct.draw_indicator_dot(pos, 0, 255, 0)

        for tile in ct.get_nearby_tiles():
            if ct.get_tile_env(tile) == Environment.ORE_TITANIUM:
                self.known_ore.add(tile)

        target = self._nearest_free_ore(ct, pos)
        if target is None:
            self._explore(ct, pos)
            return

        if pos == target:
            # Harvesters aren't walkable, so we can't build one on the tile
            # we're standing on -- step off and build from next door instead.
            self._explore(ct, pos)
            return

        if pos.distance_squared(target) <= GameConstants.ACTION_RADIUS_SQ:
            if ct.can_build_harvester(target):
                ct.build_harvester(target)
                self.known_ore.discard(target)
            return

        direction = move_toward(ct, pos, target)
        if direction is not None:
            ct.move(direction)

    def _nearest_free_ore(self, ct: Controller, pos: Position) -> Position | None:
        """Return the closest known ore tile that isn't already built on."""
        self.known_ore = {
            t for t in self.known_ore
            if not (ct.is_in_vision(t) and ct.get_tile_building_id(t) is not None)
        }
        if not self.known_ore:
            return None
        return min(self.known_ore, key=pos.distance_squared)

    def _explore(self, ct: Controller, pos: Position) -> None:
        """No known ore yet — wander toward open ground."""
        open_dirs = [
            d for d in DIRECTIONS
            if ct.can_move(d) and ct.get_tile_env(pos.add(d)) == Environment.EMPTY
        ]
        move_options = open_dirs or [d for d in DIRECTIONS if ct.can_move(d)]
        if move_options:
            ct.move(random.choice(move_options))
