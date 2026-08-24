"""Planting the Sentinel line once the Core declares the siege open.

An attacker walks to a firing spot chosen by siege.py, builds a Sentinel, and
digs out whatever is adjacent while it waits for the titanium for the next
one. The decision to open the siege at all is the Core's; see core.py.
"""
from fcode import Position

import debug
import defence
import harass
import lanes
import roster
import siege
import store
from brain import CARDINALS, DELTA
from movement import (attempt, manhattan, orthogonal,
                      step_toward, walk)


def besiege(player, ct) -> bool:
    """Plant the Sentinel line at the enemy Core. True if this turn was spent.

    The Sentinel goes on a tile sharing a row or column with a Core tile, as
    far back as its range allows, so it is shooting from outside the ring of
    Builders and turrets that defends the base. Build reaches orthogonally,
    so the Builder stops one tile short of the spot rather than standing on
    it and having to step off again.
    """
    brain = player.brain
    if brain.index is None:
        return False
    target = roster.econ_target(brain.width, brain.height)
    if not roster.is_attacker(brain.index, target, store.siege_sentinels(ct) > 0):
        return False

    core = siege.enemy_core_tiles(brain)
    spots = siege.firing_spots(brain)
    if not spots:
        return False
    # Attackers take different spots by index so two do not walk to one tile.
    rank = max(0, target - 1 - brain.index) % len(spots)
    spot, facing = spots[rank]
    me = brain.me

    if me == spot:
        # Standing on the tile we mean to build on. Build reaches orthogonally
        # and never onto our own tile, so step off first -- towards the Core we
        # are shooting at, which keeps the next spot in reach.
        for direction in CARDINALS:
            step_to = (me[0] + DELTA[direction][0], me[1] + DELTA[direction][1])
            if step_to not in brain.terrain.blocked and ct.can_move(direction):
                attempt(ct.move, direction)
                return True
        return True
    if orthogonal(me, spot):
        position = Position(*spot)
        if ct.can_build_sentinel(position, facing):
            if attempt(ct.build_sentinel, position, facing):
                store.note_sentinel(ct, store.siege_sentinels(ct) + 1)
                debug.intent(brain, ct, "attack", f"SENTINEL {spot}",
                             f"facing {facing}")
                return True
        # In position but cannot pay for the turret yet. Cut belt while we
        # wait instead of standing in their half doing nothing -- traced on
        # yggdrasil, an attacker waited from round 120 to round 300 that way
        # while the belt it could have been cutting ran past it.
        # Cut whatever is already beside us, but do not walk off to find
        # something: an attacker that leaves its firing spot to chase belt
        # never comes back to build, which measured 54/90 -> 50/90.
        for neighbour in lanes.orthogonal(me):
            if not harass.still_there(brain, neighbour):
                continue
            if brain.imap.state_at(*neighbour) is None:
                continue
            position = Position(*neighbour)
            if ct.can_fire(position):
                attempt(ct.fire, position)
                debug.intent(brain, ct, "attack", f"CUT {neighbour}",
                             "waiting on Sentinel titanium")
                return True
        debug.intent(brain, ct, "attack", "WAIT",
                     f"Sentinel costs {ct.get_sentinel_cost()}, "
                     f"have {ct.get_global_resources()}")
        return True
    debug.intent(brain, ct, "attack", f"WALK->{spot}", "closing on a firing spot")
    walk(brain, ct, spot, exact=True, hops=True)
    return True
