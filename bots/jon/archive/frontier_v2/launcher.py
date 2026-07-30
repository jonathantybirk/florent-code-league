"""Map-agnostic launcher relay for the two registered symmetry scouts."""

from fcode import Controller, Direction, Position

from constants import (
    ATTACKER_ROLES,
    SLOT_STRATEGY,
    SLOT_TARGET_CLAIM_START,
)
from utils import on_map, unpack_claim


MAX_THROW_DISTANCE_SQ = 26


def run(player, ct: Controller) -> None:
    packed_ids = ct.read_store(SLOT_STRATEGY)
    attacker_ids = (packed_ids & 0xFFFF, packed_ids >> 16)
    pos = ct.get_position()

    for role, attacker_id in zip(ATTACKER_ROLES, attacker_ids):
        if attacker_id == 0:
            continue
        bot_pos = _adjacent_attacker(ct, pos, attacker_id)
        if bot_pos is None:
            continue
        target = unpack_claim(
            ct.read_store(SLOT_TARGET_CLAIM_START + role),
            ct.get_current_round(),
        )
        if target is None:
            continue
        landing = _best_landing(ct, pos, bot_pos, target)
        if landing is not None:
            ct.launch(bot_pos, landing)
        return


def _adjacent_attacker(
    ct: Controller, launcher: Position, attacker_id: int
) -> Position | None:
    for direction in Direction:
        if direction == Direction.CENTRE:
            continue
        candidate = launcher.add(direction)
        if on_map(ct, candidate) and ct.get_tile_builder_bot_id(candidate) == attacker_id:
            return candidate
    return None


def _best_landing(
    ct: Controller,
    launcher: Position,
    bot_pos: Position,
    target: Position,
) -> Position | None:
    best: Position | None = None
    for dx in range(-5, 6):
        for dy in range(-5, 6):
            distance_sq = dx * dx + dy * dy
            if distance_sq == 0 or distance_sq > MAX_THROW_DISTANCE_SQ:
                continue
            candidate = Position(launcher.x + dx, launcher.y + dy)
            if not on_map(ct, candidate) or not ct.can_launch(bot_pos, candidate):
                continue
            if best is None or candidate.distance_squared(target) < best.distance_squared(target):
                best = candidate
    return best
