"""Turret behaviour: the Sentinel line that besieges, and the Launcher relay
that carries Builders to it.

A Launcher is the only unit here that does something every round in a normal
game. See relay.py for why: travel is brokkr's largest expense, and a throw
covers five tiles for one round of reload.
"""

from fcode import EntityType, GameError, Position

import debug
import relay
import siege
import store


def run(player, ct) -> None:
    brain = player.brain
    brain.sense(ct)
    # A turret is spawned mid-match with an empty map and a small vision
    # radius. Without the store it never learns where anything is.
    brain.sync_symmetry(ct, store)
    etype = ct.get_entity_type()
    if etype == EntityType.GUNNER:
        _fire_gunner(ct)
    elif etype == EntityType.SENTINEL:
        _fire_line(player, ct)
    elif etype == EntityType.LAUNCHER:
        _ferry(player, ct)


def _ferry(player, ct) -> None:
    """Throw an adjacent friendly Builder onward, if it gains ground.

    The Launcher decides, not the Builder: it is the unit with the action, and
    a Builder cannot ask to be thrown. So the rule has to be one the Launcher
    can evaluate alone -- is this Builder heading somewhere the throw brings
    it meaningfully closer to. Anything less and we spend a reload flinging a
    miner off its own lane.
    """
    brain = player.brain
    destination = _destination(brain)
    if destination is None:
        return
    me = brain.me
    candidates = relay.throw_candidates(me, brain.width, brain.height)
    ring = _adjacent_ring(me, brain.width, brain.height)
    for tile in ring:
        unit = brain.imap.unit_at(*tile)
        if unit is None or not _STATES[unit].startswith("OUR_BUILDER_BOT"):
            continue
        landing = relay.best_landing(ct, me, tile, destination, candidates)
        if landing is None:
            continue
        if not relay.worth_throwing(tile, landing, destination):
            continue
        if _try(ct.launch, Position(*tile), Position(*landing)):
            debug.intent(brain, ct, "relay", f"THROW {tile}->{landing}",
                         f"toward {destination}")
            return


def _destination(brain):
    """Where the relay is pointed: the enemy Core."""
    enemy = siege.enemy_core_tiles(brain)
    return min(enemy) if enemy else None


def _adjacent_ring(centre, width, height):
    x, y = centre
    return [(x + dx, y + dy)
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            if (dx or dy) and 0 <= x + dx < width and 0 <= y + dy < height]


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


from utils.GCS.Base.protocol import TILE_STATES as _STATES  # noqa: E402


def _try(action, *args) -> bool:
    try:
        action(*args)
        return True
    except GameError:
        return False
