"""Core logic for the custom bot.

The core is the team's spawn point and its loss ends the game. Every function
here takes the Player instance as its first argument (in place of `self`), so
per-unit state still lives on Player while the behaviour lives in this module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from constants import (
    BUILDER_COUNT,
    CLAIM_LEASE_ROUNDS,
    SECTOR_COUNT,
    SLOT_CORE_POSITION,
    SLOT_LATEST_ASSIGNMENT,
    SLOT_STRATEGY,
    SLOT_TARGET_CLAIM_START,
)
from fcode import Controller, Position
from utils import is_free_ore, pack_claim, pack_pos, sector_centre

if TYPE_CHECKING:
    from main import Player


def run(player: Player, ct: Controller) -> None:
    """Publish our position so builder bots can orient toward us, then try to
    spawn a builder bot each round until we hit the cap.
    """
    # One packed slot handles every valid coordinate, including (0, 0).
    pos = ct.get_position()
    ct.write_store(SLOT_CORE_POSITION, pack_pos(pos))

    ct.write_store(SLOT_STRATEGY, player.attacker_ids[0] | (player.attacker_ids[1] << 16))

    if player.num_spawned >= BUILDER_COUNT:
        return

    # Check we can afford a builder bot before trying
    if ct.get_global_resources() < ct.get_builder_bot_cost():
        return

    role = player.num_spawned
    target = _initial_target(ct, role)
    spawn_tiles = sorted(
        ct.get_nearby_tiles(dist_sq=8),
        key=lambda tile: (tile.distance_squared(target), tile.x, tile.y),
    )
    for spawn_pos in spawn_tiles:
        if ct.can_spawn(spawn_pos):
            builder_id = ct.spawn_builder(spawn_pos)
            if role < 2:
                player.attacker_ids[role] = builder_id
            ct.write_store(SLOT_LATEST_ASSIGNMENT, (builder_id << 3) | (role + 1))
            ct.write_store(
                SLOT_TARGET_CLAIM_START + role,
                pack_claim(target, ct.get_current_round() + CLAIM_LEASE_ROUNDS),
            )
            player.num_spawned += 1
            return


def _initial_target(ct: Controller, role: int) -> Position:
    """Prefer distinct ore visible to Core, then distinct nearby sectors."""
    pos = ct.get_position()
    if role == 0:
        return Position(ct.get_map_width() - 2 - pos.x, pos.y)
    if role == 1:
        return Position(pos.x, ct.get_map_height() - 2 - pos.y)
    ores = [tile for tile in ct.get_nearby_tiles() if is_free_ore(ct, tile)]
    ores.sort(key=lambda tile: (pos.distance_squared(tile), tile.x, tile.y))
    if role < len(ores):
        return ores[role]
    centres = [sector_centre(ct, index) for index in range(SECTOR_COUNT)]
    centres.sort(key=lambda tile: (pos.distance_squared(tile), tile.x, tile.y))
    return centres[(role - len(ores)) % len(centres)]
