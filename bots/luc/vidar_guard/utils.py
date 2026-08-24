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


# The Builder ticket is a small counter -- MAX_TOTAL_BUILDERS never approaches
# 256 -- so the slot that carries it has 24 spare bits and nothing to spend
# them on. The Core spends them on the ore it can see from its own footprint:
# two pack_pos coordinates at full resolution, 8 + 10 + 10 = 28 bits of 32.
# Coarsening to 2x2 tiles was the fallback if they had not fit; they fit.
#
# Hints are advisory. A Builder claims a hinted deposit through the ordinary
# CLAIM_SLOTS path and re-verifies it is really ore before building, so a
# stale or contested hint costs a wasted look and nothing else.
TICKET_BITS = 8
TICKET_MASK = (1 << TICKET_BITS) - 1
ORE_HINT_BITS = 10
ORE_HINT_MASK = (1 << ORE_HINT_BITS) - 1


def pack_ticket(ticket: int, ores: "list | tuple" = ()) -> int:
    value = ticket & TICKET_MASK
    for index, ore in enumerate(ores[:2]):
        value |= (pack_pos(ore) & ORE_HINT_MASK) << (
            TICKET_BITS + index * ORE_HINT_BITS)
    return value


def unpack_ticket(value: int) -> tuple[int, list[tuple[int, int]]]:
    """Return (ticket, ore hints). Hints survive the ticket's increment."""
    hints = []
    for index in range(2):
        packed = (value >> (TICKET_BITS + index * ORE_HINT_BITS)) & ORE_HINT_MASK
        ore = unpack_pos(packed)
        if ore is not None:
            hints.append(ore)
    return value & TICKET_MASK, hints


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
