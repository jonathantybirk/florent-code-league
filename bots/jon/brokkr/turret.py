"""Turret behaviour. Nothing builds turrets yet, so this is the handler that
keeps one alive and useful if a later version does -- and, more immediately,
guarantees that an unexpected turret type never reaches an empty branch and
raises out of run().
"""

from fcode import EntityType, GameError


def run(player, ct) -> None:
    player.brain.sense(ct)
    etype = ct.get_entity_type()
    if etype == EntityType.GUNNER:
        _fire_gunner(ct)
    elif etype == EntityType.SENTINEL:
        _fire_line(ct)


def _fire_gunner(ct) -> None:
    try:
        target = ct.get_gunner_target()
    except GameError:
        return
    if target is not None and ct.can_fire(target):
        _try(ct.fire, target)


def _fire_line(ct) -> None:
    """Sentinels cannot rotate, so the only choice is whether to shoot.

    get_attackable_tiles() is the raw pattern -- it ignores ammo, cooldown and
    occupancy -- so every candidate still has to clear can_fire().
    """
    try:
        tiles = ct.get_attackable_tiles()
    except GameError:
        return
    for tile in tiles:
        if ct.can_fire(tile):
            _try(ct.fire, tile)
            return


def _try(action, *args) -> bool:
    try:
        action(*args)
        return True
    except GameError:
        return False
