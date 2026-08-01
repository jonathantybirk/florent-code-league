"""Gunner behaviour.

Hold fire only when the ray stops on a building of ours -- shooting our own
barrier ring or supply line is never useful. Everything else is worth a shot,
including a tile whose occupant we cannot identify: a Core reports no building
id on the three footprint tiles that are not its anchor, and a Gunner that
refused those would never damage the thing it was built to kill.

Measured over the full 180-game field, additionally sparing a *friendly
Builder* standing in the line is not worth it (99-81 against 105-75): it burns
a firing window on a unit that walks out of the way by itself.

A Gunner whose line is empty is dead weight for the rest of the match, and
2.3.3 lets it re-aim: ct.rotate() costs a flat 10 Ti against roughly 25 plus
another 10% of shared cost scale for a fresh one. So a Gunner that has seen
nothing for a while turns to face the enemy Core instead of standing idle.
"""

from fcode import Controller, Direction, GameError

from constants import SLOT_ENEMY_CORE
from utils import unpack_pos

# Rounds of an empty firing line before a Gunner pays to turn round.
IDLE_BEFORE_ROTATE = 25


def run(player, ct: Controller) -> None:
    try:
        target = ct.get_gunner_target()
        if target is None:
            _consider_rotating(player, ct)
            return
        player.idle_rounds = 0
        # A Builder standing on a building soaks the hit, so it owns the tile.
        if ct.get_tile_builder_bot_id(target) is None:
            building = ct.get_tile_building_id(target)
            if building is not None and ct.get_team(building) == ct.get_team():
                return
        if ct.can_fire(target):
            ct.fire(target)
    except GameError:
        return


def _consider_rotating(player, ct: Controller) -> None:
    player.idle_rounds = getattr(player, "idle_rounds", 0) + 1
    if player.idle_rounds < IDLE_BEFORE_ROTATE:
        return
    enemy = unpack_pos(ct.read_store(SLOT_ENEMY_CORE))
    if not enemy:
        return
    here = ct.get_position()
    want = (enemy[0] - here.x, enemy[1] - here.y)
    if want == (0, 0):
        return
    best = max(Direction, key=lambda d: (
        0 if d == Direction.CENTRE
        else d.delta()[0] * want[0] + d.delta()[1] * want[1]))
    if best == ct.get_direction():
        player.idle_rounds = 0
        return
    if ct.can_rotate(best):
        ct.rotate(best)
        player.idle_rounds = 0
