"""Shared stateless helpers."""

from fcode import Position


def pack_pos(pos: Position | tuple[int, int]) -> int:
    x, y = pos
    return 1 + x * 32 + y


def unpack_pos(value: int) -> tuple[int, int] | None:
    if value == 0:
        return None
    value -= 1
    return value // 32, value % 32
