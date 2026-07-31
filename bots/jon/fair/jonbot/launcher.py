"""Launcher behavior.

Launchers stay idle until a destination is positively assigned. Blindly
throwing an economy Builder is worse than doing nothing.
"""

from typing import TYPE_CHECKING

from fcode import Controller, Direction, Position

from constants import SLOT_ALERT, SLOT_ENEMY_CORE, SLOT_OWN_CORE
from utils import unpack_pos

if TYPE_CHECKING:
    from main import Player


def run(player: "Player", ct: Controller) -> None:
    builder_id = ct.read_store(SLOT_ALERT)
    if not builder_id:
        return
    launcher = ct.get_position()
    bot_pos = None
    for direction in Direction:
        if direction == Direction.CENTRE:
            continue
        position = launcher.add(direction)
        if not (0 <= position.x < ct.get_map_width()
                and 0 <= position.y < ct.get_map_height()):
            continue
        if ct.get_tile_builder_bot_id(position) == builder_id:
            bot_pos = position
            break
    if bot_pos is None:
        return
    target = unpack_pos(ct.read_store(SLOT_ENEMY_CORE))
    if target is None:
        own_core = unpack_pos(ct.read_store(SLOT_OWN_CORE))
        if own_core is None:
            return
        target = (ct.get_map_width() - 2 - own_core[0],
                  ct.get_map_height() - 2 - own_core[1])
    target_pos = Position(*target)
    candidates = [position for position in ct.get_attackable_tiles()
                  if ct.can_launch(bot_pos, position)]
    if candidates:
        destination = min(candidates, key=lambda position: (
            position.distance_squared(target_pos), position.x, position.y))
        ct.launch(bot_pos, destination)
        ct.write_store(SLOT_ALERT, 0)
