"""Launcher behaviour: ferry attackers or throw enemy raiders back.

Walking a Builder across a 26-tile map costs about twenty rounds, and matches
are usually decided before round seventy. A Launcher throws an adjacent
Builder just over five tiles for 20 Ti, trading titanium for the only currency
that matters in the opening: tempo.

A Builder asks to be thrown by writing its id into SLOT_LAUNCH_ID. Store
writes land a round late, which is exactly when the new Launcher first acts,
and it stops us flinging an economy Builder that happened to walk past.
"""

import os
import sys

from fcode import Controller, GameError, Position

from constants import (LAUNCH_RANGE_SQ, PICKET_SLOTS, SLOT_ENEMY_CORE,
                       SLOT_LAUNCH_ID)
from utils import unpack_pos

# Long enough for the next Builder in the queue to arrive and ask for a ride.
IDLE_ROUNDS_BEFORE_SCRAP = 6


def run(player, ct: Controller) -> None:
    try:
        _run(player, ct)
    except GameError:
        return


def _run(player, ct):
    picket = _is_picket(ct)
    if picket and _repel(ct):
        player.idle = 0
        return
    wanted = ct.read_store(SLOT_LAUNCH_ID)
    if not wanted:
        if picket:
            return
        # A Launcher contributes 10% to the shared cost scale for as long as
        # it lives, taxing every Gunner the siege still has to buy. Once the
        # ferry queue is empty it is worth more dead than standing.
        player.idle = getattr(player, "idle", 0) + 1
        if player.idle >= IDLE_ROUNDS_BEFORE_SCRAP:
            ct.self_destruct()
        return
    player.idle = 0
    passenger = None
    for unit in ct.get_nearby_units(2):
        if unit == wanted and ct.get_team(unit) == ct.get_team():
            passenger = unit
            break
    if passenger is None:
        return

    origin = ct.get_position(passenger)
    target = _destination(ct, ct.get_position())
    best = None
    for tile in ct.get_nearby_tiles(LAUNCH_RANGE_SQ):
        if not ct.can_launch(origin, tile):
            continue
        # Tie-break on coordinates: get_nearby_tiles() has no promised order,
        # and an arbitrary pick here made whole matches irreproducible.
        remaining = (tile.distance_squared(target), tile.x, tile.y)
        if best is None or remaining < best[0]:
            best = (remaining, tile)
    # Never throw a Builder backwards: a hop that loses ground wastes a round.
    if best is None or best[0][0] >= origin.distance_squared(target):
        return
    ct.launch(origin, best[1])
    ct.write_store(SLOT_LAUNCH_ID, 0)


def _is_picket(ct: Controller) -> bool:
    here = (ct.get_position().x, ct.get_position().y)
    return any(unpack_pos(ct.read_store(slot)) == here for slot in PICKET_SLOTS)


def _repel(ct: Controller) -> bool:
    """Throw an adjacent enemy Builder toward its own side of the map."""
    mine = ct.get_team()
    destination = _destination(ct, ct.get_position())
    for unit in sorted(ct.get_nearby_units(2)):
        if ct.get_team(unit) == mine:
            continue
        origin = ct.get_position(unit)
        best = None
        for tile in ct.get_nearby_tiles(LAUNCH_RANGE_SQ):
            try:
                legal = ct.can_launch(origin, tile)
            except GameError:
                legal = False
            if not legal:
                continue
            score = (tile.distance_squared(destination),
                     -tile.distance_squared(ct.get_position()), tile.x, tile.y)
            if best is None or score < best[0]:
                best = (score, tile)
        if best is not None:
            ct.launch(origin, best[1])
            if os.environ.get("UNDERTOW_DEBUG"):
                print(f"r{ct.get_current_round()} picket {ct.get_position()} "
                      f"repelled {origin} to {best[1]}", file=sys.stderr,
                      flush=True)
            return True
    return False


def _destination(ct: Controller, here: Position) -> Position:
    packed = unpack_pos(ct.read_store(SLOT_ENEMY_CORE))
    if packed:
        return Position(*packed)
    # Before the Core is pinned down, aim at the far corner of the map.
    width, height = ct.get_map_width(), ct.get_map_height()
    return Position(0 if here.x * 2 > width else width - 1,
                    0 if here.y * 2 > height else height - 1)
