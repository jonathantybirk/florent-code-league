"""Mixed-radix packing for GCS payloads.

Mixed radix means several small values share one integer by multiplying by
each value's own count instead of rounding up to powers of two:
    pack([a, b, c], [Ra, Rb, Rc]) == (a*Rb + b)*Rc + c
The first digit is the most significant.  unpack() is the exact inverse.

This module knows nothing about the wire format; it only packs and unpacks.
Errors raise CodecError — callers in this package catch it and degrade, so
nothing ever propagates into the bot's turn.
"""

from __future__ import annotations

from .protocol import PAYLOAD_SPACE


class CodecError(ValueError):
    """A digit was out of range or a packed value exceeded the payload space.

    Subclasses ValueError because the engine's bot validator only allows
    builtin exception names in `except` clauses — catch this as ValueError.
    """


def capacity(radices: tuple[int, ...] | list[int]) -> int:
    """Total number of values the radix list can express."""
    total = 1
    for r in radices:
        total *= r
    return total


def pack(digits, radices) -> int:
    """Pack digits (most significant first) into one integer.

    Raises CodecError if any digit is out of range or the result would not fit
    in the payload space (and could therefore collide with a reserved value).
    """
    if len(digits) != len(radices):
        raise CodecError(f"{len(digits)} digits for {len(radices)} radices")
    value = 0
    for digit, radix in zip(digits, radices):
        if not 0 <= digit < radix:
            raise CodecError(f"digit {digit} out of range 0..{radix - 1}")
        value = value * radix + digit
    if value >= PAYLOAD_SPACE:
        raise CodecError(f"packed value {value} exceeds payload space")
    return value


def unpack(value: int, radices) -> tuple[int, ...]:
    """Inverse of pack().  Raises CodecError if value is outside the space."""
    if not 0 <= value < PAYLOAD_SPACE:
        raise CodecError(f"value {value} outside payload space")
    if value >= capacity(radices):
        raise CodecError(f"value {value} exceeds capacity of {radices}")
    digits = [0] * len(radices)
    for i in range(len(radices) - 1, -1, -1):
        value, digits[i] = divmod(value, radices[i])
    return tuple(digits)
