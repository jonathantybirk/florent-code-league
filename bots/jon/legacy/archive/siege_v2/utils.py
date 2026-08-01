"""Small stateless helpers shared by custom unit handlers in main.py."""

from fcode import Controller, Direction, Environment, Position


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


def pack_claim(pos: Position, expires_round: int) -> int:
    """Pack a <=30x30 coordinate and a 10-bit lease into one u32."""
    return 1 | (pos.x << 1) | (pos.y << 6) | (expires_round << 11)


def unpack_claim(value: int, current_round: int) -> Position | None:
    """Return a live claimed position, or None for an empty/expired lease."""
    if value == 0 or (value >> 11) < current_round:
        return None
    return Position((value >> 1) & 0x1F, (value >> 6) & 0x1F)


def on_map(ct: Controller, pos: Position) -> bool:
    """True if pos is inside the map. Tile queries raise GameError off-map."""
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


def is_free_ore(ct: Controller, tile: Position) -> bool:
    """True if the tile is ore with no building (harvester or otherwise) on it."""
    return ct.get_tile_env(tile) == Environment.ORE_TITANIUM and ct.get_tile_building_id(tile) is None


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


def sector_index(ct: Controller, pos: Position, grid_size: int = 5) -> int:
    """Map a position into a grid_size × grid_size coverage cell."""
    sx = min(grid_size - 1, pos.x * grid_size // ct.get_map_width())
    sy = min(grid_size - 1, pos.y * grid_size // ct.get_map_height())
    return sy * grid_size + sx


def sector_centre(ct: Controller, index: int, grid_size: int = 5) -> Position:
    """Return an in-bounds integer centre for a coverage cell."""
    sx, sy = index % grid_size, index // grid_size
    denominator = 2 * grid_size
    return Position(
        min(
            ct.get_map_width() - 1,
            (2 * sx + 1) * ct.get_map_width() // denominator,
        ),
        min(
            ct.get_map_height() - 1,
            (2 * sy + 1) * ct.get_map_height() // denominator,
        ),
    )
