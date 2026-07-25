"""Small stateless helpers shared by unit handlers in main.py."""

from fcode import Controller, Direction, Position


def pack_pos(pos: Position) -> int:
    """Encode a position into a single u32 for the communication store.

    We offset by +1 so that position (0, 0) doesn't encode as 0,
    which we reserve to mean "no data".
    """
    return ((pos.x + 1) << 16) | (pos.y + 1)


def unpack_pos(val: int) -> Position | None:
    """Decode a position from the communication store. Returns None if empty (0)."""
    if val == 0:
        return None
    return Position((val >> 16) - 1, (val & 0xFFFF) - 1)


def move_toward(ct: Controller, pos: Position, target: Position) -> Direction | None:
    """Pick a legal movement direction that closes the distance to target.

    Builder bots can move in all 8 directions (unlike conveyors/splitters,
    which are cardinal-only), so we go straight at the target and only
    sidestep if something blocks the direct line.
    """
    direction = pos.direction_to(target)
    if ct.can_move(direction):
        return direction
    for candidate in (direction.rotate_left(), direction.rotate_right()):
        if ct.can_move(candidate):
            return candidate
    return None
