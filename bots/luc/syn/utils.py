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


# --- Launch protocol ----------------------------------------------------------
# One owner for the whole wire format. It used to be spread across the Builder,
# the Launcher and here, with no single place defining what a word means -- so
# the pad decoded a landing offset against its own position while the Builder
# had encoded it against a different pad, and nothing made the contradiction
# visible. Both halves now call the same encode/decode pair.
#
# A slot holds one of three things, and which one is readable from the word:
#
#   0                       empty
#   bit 31 clear, non-zero  a request   (Builder -> pad)
#   bit 31 set              a response  (pad -> Builder)
#
# The Builder may only write over empty or a response; the pad only ever writes
# in reply to a request. So no round has both of them writing, and nothing is
# lost to a same-round collision.
#
# REQUEST   bits 0-6   landing, as an index into the pad's throw field
#           bits 7-30  passenger entity id
#
# RESPONSE  bit  30    1 = launched, 0 = refused
#           bits 24-29 six-bit hash of the passenger id
#           bits 0-23  on a refusal, two enemies: offset from the pad (4+4),
#                      facing (3), kind (1)
#
# Nothing names the pad, because the rule already does: a tile is served by the
# *lowest-id* friendly Launcher whose pickup radius covers it. Both sides derive
# that identically, so the pad that decodes an offset is always the pad that
# encoded it.
LAUNCH_PICKUP_SQ = 2

MSG_RESPONSE = 1 << 31
MSG_LAUNCHED = 1 << 30
LANDING_BITS = 7
LANDING_MASK = (1 << LANDING_BITS) - 1
HASH_SHIFT = 24
HASH_MASK = 0x3F
ENTRY_BITS = 12
MAX_ENTRIES = 2
OFFSET_BIAS = 8

THROW_OFFSETS = tuple(
    (dx, dy)
    for dx in range(-5, 6)
    for dy in range(-5, 6)
    if dx * dx + dy * dy <= 26
)
THROW_INDEX = {offset: index for index, offset in enumerate(THROW_OFFSETS)}


def pad_owner(pads, tile):
    """The pad that serves `tile`: lowest id whose pickup radius covers it.

    `pads` maps position -> entity id, with None for a pad remembered but not
    currently in vision. A pad of unknown id cannot be compared, so it only wins
    when nothing identifiable covers the tile -- which is the right answer while
    approaching, and resolves the moment the pad comes into sight.
    """
    covering = [(pos, ident) for pos, ident in pads.items()
                if (pos[0] - tile[0]) ** 2 + (pos[1] - tile[1]) ** 2
                <= LAUNCH_PICKUP_SQ]
    if not covering:
        return None
    known = [(ident, pos) for pos, ident in covering if ident is not None]
    if known:
        return min(known)[1]
    return min(covering)[0]


def landing_index(pad, tile):
    return THROW_INDEX.get((tile[0] - pad[0], tile[1] - pad[1]))


def landing_tile(pad, index):
    if not 0 <= index < len(THROW_OFFSETS):
        return None
    dx, dy = THROW_OFFSETS[index]
    return (pad[0] + dx, pad[1] + dy)


def is_request(value):
    return value != 0 and not value & MSG_RESPONSE


def is_response(value):
    return bool(value & MSG_RESPONSE)


def writable_by_builder(value):
    """A Builder may claim a slot that is empty or already answered."""
    return value == 0 or is_response(value)


def passenger_hash(entity_id):
    return entity_id & HASH_MASK


def pack_request(passenger, index):
    return (passenger << LANDING_BITS) | (index & LANDING_MASK)


def unpack_request(value):
    return value >> LANDING_BITS, value & LANDING_MASK


def pack_response(pad, passenger, launched, entries=()):
    value = MSG_RESPONSE | (passenger_hash(passenger) << HASH_SHIFT)
    if launched:
        return value | MSG_LAUNCHED
    for slot, (pos, facing, kind) in enumerate(tuple(entries)[:MAX_ENTRIES]):
        dx = pos[0] - pad[0] + OFFSET_BIAS
        dy = pos[1] - pad[1] + OFFSET_BIAS
        if not (0 <= dx < 16 and 0 <= dy < 16):
            continue
        entry = dx | (dy << 4) | ((facing & 0x7) << 8) | ((kind & 1) << 11)
        value |= entry << (slot * ENTRY_BITS)
    return value


def unpack_response(pad, value):
    """Return (launched, passenger_hash, [(position, facing, kind), ...])."""
    entries = []
    if not value & MSG_LAUNCHED:
        for slot in range(MAX_ENTRIES):
            entry = (value >> (slot * ENTRY_BITS)) & 0xFFF
            if entry == 0:
                continue
            dx = (entry & 0xF) - OFFSET_BIAS
            dy = ((entry >> 4) & 0xF) - OFFSET_BIAS
            entries.append(((pad[0] + dx, pad[1] + dy),
                            (entry >> 8) & 0x7, (entry >> 11) & 0x1))
    return (bool(value & MSG_LAUNCHED),
            (value >> HASH_SHIFT) & HASH_MASK, entries)
