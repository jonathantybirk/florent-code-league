"""Shared stateless helpers."""

from fcode import Position

# pack_pos tops out at 1 + 29*32 + 29 = 958 on the largest legal map, so bits
# 10 and up of a store slot are free. The Core rides the doctrine there rather
# than spending a seventeenth slot on it: all sixteen are already allocated.
POSITION_BITS = 10
POSITION_MASK = (1 << POSITION_BITS) - 1


def pack_pos(pos: Position | tuple[int, int]) -> int:
    x, y = pos
    return 1 + x * 32 + y


def unpack_pos(value: int) -> tuple[int, int] | None:
    if value == 0:
        return None
    value -= 1
    return value // 32, value % 32


def pack_core(pos: Position | tuple[int, int], doctrine: int) -> int:
    """Core position plus the doctrine every unit has to agree on."""
    return pack_pos(pos) | (doctrine << POSITION_BITS)


def unpack_core(value: int) -> tuple[tuple[int, int] | None, int]:
    return unpack_pos(value & POSITION_MASK), value >> POSITION_BITS


# The enemy-Core slot carries a guess long before anyone has seen the Core, so
# it also has to say which it is: a sighting is authoritative and no inference
# may overwrite it. Same spare high bits as the doctrine.
ENEMY_SIGHTED = 1 << POSITION_BITS


def pack_enemy(pos: Position | tuple[int, int], sighted: bool = False) -> int:
    return pack_pos(pos) | (ENEMY_SIGHTED if sighted else 0)


def unpack_enemy(value: int) -> tuple[tuple[int, int] | None, bool]:
    return unpack_pos(value & POSITION_MASK), bool(value & ENEMY_SIGHTED)
