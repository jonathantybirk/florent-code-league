"""Temporary launcher ferries for Builders that cannot find a walking path."""

from fcode import Controller, GameError, Position

from constants import LAUNCH_RANGE_SQ, SLOT_LAUNCH_ID, SLOT_LAUNCH_TARGET
from utils import unpack_pos


IDLE_ROUNDS_BEFORE_SCRAP = 6


def run(player, ct: Controller) -> None:
    try:
        _run(player, ct)
    except GameError:
        return


def _run(player, ct):
    wanted = ct.read_store(SLOT_LAUNCH_ID)
    packed_target = ct.read_store(SLOT_LAUNCH_TARGET)
    if not wanted or not packed_target:
        _wait_or_scrap(player, ct)
        return

    passenger = next(
        (unit for unit in ct.get_nearby_units(2)
         if unit == wanted and ct.get_team(unit) == ct.get_team()),
        None,
    )
    if passenger is None:
        _wait_or_scrap(player, ct)
        return

    player.idle = 0
    origin = ct.get_position(passenger)
    target = Position(*unpack_pos(packed_target))
    choices = []
    for tile in ct.get_nearby_tiles(LAUNCH_RANGE_SQ):
        if ct.can_launch(origin, tile):
            choices.append((tile.distance_squared(target), tile.x, tile.y, tile))
    if not choices:
        _wait_or_scrap(player, ct)
        return

    *_, destination = min(choices)
    if destination.distance_squared(target) >= origin.distance_squared(target):
        _wait_or_scrap(player, ct)
        return
    ct.launch(origin, destination)
    ct.write_store(SLOT_LAUNCH_ID, 0)
    ct.write_store(SLOT_LAUNCH_TARGET, 0)


def _wait_or_scrap(player, ct):
    player.idle = getattr(player, "idle", 0) + 1
    if player.idle >= IDLE_ROUNDS_BEFORE_SCRAP:
        ct.self_destruct()
