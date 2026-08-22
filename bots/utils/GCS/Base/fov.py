"""Per-entity-type FOV index tables.

A FOV index names a tile by its rank in a fixed scan of the full geometric
vision disc (all offsets (dx, dy) with dx*dx + dy*dy <= radius_sq), in reading
order: top-to-bottom (dy ascending), then left-to-right (dx ascending).

The tables always cover the full disc — line-of-sight occlusion never changes
the numbering, a sender simply never announces a tile it cannot see — so
sender and receiver agree on every index with no engine-behaviour dependency.

Both directions are O(1) lookups after import.
"""

from __future__ import annotations

from .protocol import FOV_TILES, VISION_RADIUS_SQ

# kind -> tuple of (dx, dy) in scan order
OFFSETS: dict[str, tuple[tuple[int, int], ...]] = {}
# kind -> {(dx, dy): index}
INDEX: dict[str, dict[tuple[int, int], int]] = {}

for _kind, _rsq in VISION_RADIUS_SQ.items():
    _r = int(_rsq**0.5)
    _offsets = tuple(
        (dx, dy)
        for dy in range(-_r, _r + 1)
        for dx in range(-_r, _r + 1)
        if dx * dx + dy * dy <= _rsq
    )
    OFFSETS[_kind] = _offsets
    INDEX[_kind] = {off: i for i, off in enumerate(_offsets)}
    # protocol.py's budget arithmetic depends on these counts; fail at import
    # if the engine's radii ever shift them.
    assert len(_offsets) == FOV_TILES[_kind], (
        f"{_kind}: disc has {len(_offsets)} tiles, protocol says {FOV_TILES[_kind]}"
    )


def offset_of(kind: str, index: int) -> tuple[int, int]:
    """(dx, dy) of a FOV index relative to the unit's position."""
    return OFFSETS[kind][index]


def index_of(kind: str, dx: int, dy: int) -> int | None:
    """FOV index for an offset, or None if outside the disc."""
    return INDEX[kind].get((dx, dy))
