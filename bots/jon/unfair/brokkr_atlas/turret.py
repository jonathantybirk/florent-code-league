"""Turret behaviour. Nothing builds turrets yet, so this is the handler that
keeps one alive and useful if a later version does -- and, more immediately,
guarantees that an unexpected turret type never reaches an empty branch and
raises out of run().
"""

from fcode import EntityType, GameError

import siege


def run(player, ct) -> None:
    player.brain.sense(ct)
    etype = ct.get_entity_type()
    if etype == EntityType.GUNNER:
        _fire_gunner(ct)
    elif etype == EntityType.SENTINEL:
        _fire_line(player, ct)


def _fire_gunner(ct) -> None:
    try:
        target = ct.get_gunner_target()
    except GameError:
        return
    if target is not None and ct.can_fire(target):
        _try(ct.fire, target)


def _fire_line(player, ct) -> None:
    """Sentinels cannot rotate, so the only choice is whether to shoot -- and
    the answer is usually "not yet".

    Shooting the moment a shot is affordable loses to any Core with a Builder
    beside it: 9 damage a round against 4 HP of repair per titanium they
    spend. Damage only sticks when it arrives faster than the mending, so the
    line holds until the bank is full and then empties it. See siege.volley.

    get_attackable_tiles() is the raw pattern -- it ignores ammo, cooldown and
    occupancy -- so every candidate still has to clear can_fire().
    """
    player.firing = siege.volley(ct.get_global_ammo(),
                                 getattr(player, "firing", False))
    if not player.firing:
        return
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
