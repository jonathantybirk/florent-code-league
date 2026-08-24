"""The 16-slot global store, as a named schema rather than magic indices.

Two engine facts shape everything here:

* **Writes are buffered.** A value written this round is invisible until the
  next one. So the store cannot be used for within-round arbitration, and a
  per-round accumulator (a live headcount bitmask, say) never accumulates --
  every unit would read the same stale snapshot and clobber it.
* **Last writer in unit order wins.** Units act in ascending spawn order, so the
  highest-id writer's value is the one that survives the round.

Values are u32. A negative value or anything >= 2**32 raises `OverflowError`,
which is *not* a `GameError` and will therefore not be caught by the usual
handler -- it permanently destroys the unit. Every write goes through `_put`,
which clamps, so that can never happen.
"""
from __future__ import annotations

from fcode import Controller, GameError, Position

# Slot map. Keep this table and nothing else as the source of truth.
CORE_X = 0
CORE_Y = 1
ENEMY_CORE_X = 2
ENEMY_CORE_Y = 3
SYMMETRY = 4          # 0 unknown, else index into geom.SYMMETRIES + 1
HARVESTERS = 5        # count we believe are alive
ALARM_ROUND = 6       # round we last saw an enemy near home
BUILDER_TICK = 7      # heartbeat: bumped by any builder, proves someone lives
SIEGE_SEATS = 8       # count of siege turrets we believe are up
CONTACT_ROUND = 9     # round we first saw any enemy
TRUNK_COUNT = 10      # conveyor trunks established
DELIVERED = 11        # our own estimate of stacks landed (tiebreak proxy)
SPARE_12 = 12
SPARE_13 = 13
SPARE_14 = 14
SPARE_15 = 15

_U32_MAX = 4294967295


def _put(ct: Controller, slot: int, value: int) -> None:
    if value < 0:
        value = 0
    elif value > _U32_MAX:
        value = _U32_MAX
    try:
        ct.write_store(slot, int(value))
    except GameError:
        pass


def _get(ct: Controller, slot: int) -> int:
    try:
        return ct.read_store(slot)
    except GameError:
        return 0


def put(ct: Controller, slot: int, value: int) -> None:
    _put(ct, slot, value)


def get(ct: Controller, slot: int) -> int:
    return _get(ct, slot)


def put_pos(ct: Controller, slot_x: int, slot_y: int, pos: Position) -> None:
    _put(ct, slot_x, pos.x + 1)      # +1 so "unset" is distinguishable from x=0
    _put(ct, slot_y, pos.y + 1)


def get_pos(ct: Controller, slot_x: int, slot_y: int):
    x = _get(ct, slot_x)
    y = _get(ct, slot_y)
    if x <= 0 or y <= 0:
        return None
    return Position(x - 1, y - 1)


def bump(ct: Controller, slot: int) -> None:
    """Increment a counter. Racy by construction: two units bumping in the same
    round both read the same value and the later one wins, so this counts
    *rounds in which at least one unit bumped*, not units. That is exactly what
    a heartbeat wants and is not enough for a census."""
    _put(ct, slot, _get(ct, slot) + 1)
