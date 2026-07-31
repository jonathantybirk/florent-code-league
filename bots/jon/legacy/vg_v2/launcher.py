"""Launcher behaviour: a one-shot ferry that buys the siege several rounds.

Walking a Builder across a 26-tile map costs about twenty rounds, and matches
are usually decided before round seventy. A Launcher throws an adjacent
Builder just over five tiles for 20 Ti, trading titanium for the only currency
that matters in the opening: tempo.

A Builder asks to be thrown by writing its id into SLOT_LAUNCH_ID. Store
writes land a round late, which is exactly when the new Launcher first acts,
and it stops us flinging an economy Builder that happened to walk past.
"""

from fcode import Controller, GameError, Position

from constants import LAUNCH_RANGE_SQ, SLOT_ENEMY_CORE, SLOT_LAUNCH_ID
from utils import unpack_pos

# Long enough for the next Builder in the queue to arrive and ask for a ride.
IDLE_ROUNDS_BEFORE_SCRAP = 6


def run(player, ct: Controller) -> None:
    try:
        _run(player, ct)
    except GameError:
        return


def _run(player, ct):
    wanted = ct.read_store(SLOT_LAUNCH_ID)
    if not wanted:
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


def _destination(ct: Controller, here: Position) -> Position:
    packed = unpack_pos(ct.read_store(SLOT_ENEMY_CORE))
    if packed:
        return Position(*packed)
    # Before the Core is pinned down, aim at the far corner of the map.
    width, height = ct.get_map_width(), ct.get_map_height()
    return Position(0 if here.x * 2 > width else width - 1,
                    0 if here.y * 2 > height else height - 1)
