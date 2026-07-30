"""Core logic for the custom bot.

The core is the team's spawn point and its loss ends the game. Every function
here takes the Player instance as its first argument (in place of `self`), so
per-unit state still lives on Player while the behaviour lives in this module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from constants import (
    BUILDER_COUNT,
    ATTACK_RESERVE_TITANIUM,
    CLAIM_LEASE_ROUNDS,
    SECTOR_COUNT,
    SLOT_CORE_POSITION,
    SLOT_LATEST_ASSIGNMENT,
    SLOT_COVERAGE_START,
    SLOT_STRATEGY,
    SLOT_TARGET_CLAIM_START,
)
from fcode import Controller, Position
from utils import is_free_ore, pack_claim, pack_pos

if TYPE_CHECKING:
    from main import Player


def run(player: Player, ct: Controller) -> None:
    """Publish our position so builder bots can orient toward us, then try to
    spawn a builder bot each round until we hit the cap.
    """
    # One packed slot handles every valid coordinate, including (0, 0).
    pos = ct.get_position()
    ct.write_store(SLOT_CORE_POSITION, pack_pos(pos))

    completed_lines = sum(
        ct.read_store(SLOT_COVERAGE_START + role) >> 25
        for role in range(BUILDER_COUNT)
    )
    if (
        ct.read_store(SLOT_STRATEGY) == 1
        or (completed_lines >= 4 and ct.get_global_resources() >= ATTACK_RESERVE_TITANIUM)
    ):
        ct.write_store(SLOT_STRATEGY, 1)

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
    ores = [tile for tile in ct.get_nearby_tiles() if is_free_ore(ct, tile)]
    ores.sort(key=lambda tile: (pos.distance_squared(tile), tile.x, tile.y))
    if role < len(ores):
        return ores[role]
    centres = [_sector_centre(ct, index) for index in range(SECTOR_COUNT)]
    centres.sort(key=lambda tile: (pos.distance_squared(tile), tile.x, tile.y))
    return centres[(role - len(ores)) % len(centres)]


def _sector_centre(ct: Controller, index: int) -> Position:
    sx, sy = index % 5, index // 5
    return Position(
        min(ct.get_map_width() - 1, (2 * sx + 1) * ct.get_map_width() // 10),
        min(ct.get_map_height() - 1, (2 * sy + 1) * ct.get_map_height() // 10),
    )
