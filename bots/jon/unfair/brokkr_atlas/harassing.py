"""Cutting the enemy economy, and founding the relay on the way out.

The sequence is approach, hit a belt tile until it is gone, then sit a barrier
on it: a cut without a barrier is repaired by a 3 Ti conveyor and the ten
rounds of hitting bought nothing. Which tile is worth cutting is harass.py's
question; this module is the Builder that goes and does it.
"""
from fcode import Position

import debug
import harass
import lanes
import relay
import roster
import siege
import store
from movement import STATES, attempt, manhattan, orthogonal, step_toward, walk


def harass_turn(player, ct) -> bool:
    """Cut one enemy belt tile and leave a barrier on it. True if we acted.

    The sequence is approach, hit until it is gone, then occupy. Occupying is
    not optional: a cut without a barrier is repaired by a 3 Ti conveyor and
    the ten rounds of hitting bought nothing.
    """
    brain = player.brain
    if brain.index is None:
        return False
    target_count = roster.econ_target(brain.width, brain.height)
    allowed = harass.ready(brain.round, ct.get_global_resources(),
                           store.team_income(ct))
    if not roster.is_harasser(brain.index, target_count, allowed):
        return False

    enemy_core = siege.enemy_core_tiles(brain)
    if not enemy_core:
        return False
    if build_relay(player, ct, enemy_core):
        return True
    return harass_action(player, ct, enemy_core)


def build_relay(player, ct, enemy_core) -> bool:
    """Put a Launcher on the corridor if we are standing next to a station.

    Built opportunistically by whoever is passing, rather than by sending
    somebody: the harassers already walk this line every trip, so the cost is
    one build action from a Builder that was going that way anyway.
    """
    brain = player.brain

    # Once a Builder commits to founding a station it stays committed until
    # the Launcher exists. Re-deciding every turn on the current balance made
    # it oscillate: harassment spends titanium at 2 Ti a hit, so the reserve
    # test flickered and the Builder turned back every second round. Six
    # detours were started on midgard and none ever arrived.
    if brain.station is not None and relay.has_launcher_near(brain, brain.station):
        brain.station = None
    if brain.station is None:
        if ct.get_global_resources() < ct.get_launcher_cost() + relay.RESERVE:
            return False
        for wanted in relay.station_targets(brain, enemy_core):
            if relay.has_launcher_near(brain, wanted):
                continue
            spot = relay.free_station(brain, wanted)
            if spot is not None and manhattan(brain.me, spot) <= relay.DETOUR:
                brain.station = spot
                break
        if brain.station is None:
            return False

    spot = brain.station
    if orthogonal(brain.me, spot):
        position = Position(*spot)
        if ct.can_build_launcher(position):
            if attempt(ct.build_launcher, position):
                debug.intent(brain, ct, "harass", f"LAUNCHER {spot}",
                             "relay station")
                brain.station = None
                return True
        return True                     # in place; wait for the titanium

    stands = [t for t in lanes.orthogonal(spot)
              if brain.terrain.inside(t) and t not in brain.terrain.blocked]
    if not stands:
        brain.station = None
        return False
    stands.sort(key=lambda t: manhattan(t, brain.me))
    debug.intent(brain, ct, "harass", f"STATION->{spot}", "founding the relay")
    for stand in stands:
        if walk(brain, ct, stand, exact=True):
            return True
    brain.station = None
    return False


def harass_action(player, ct, enemy_core) -> bool:
    """The cut-and-seal behaviour itself, without the role check.

    Attackers borrow this. An attacker that has walked to its firing spot and
    cannot yet afford a Sentinel is standing in the enemy half with nothing to
    do -- traced on yggdrasil, one waited 180 rounds that way, from round 120
    to round 300, while belt it could have been cutting ran past it.
    """
    brain = player.brain
    spot = brain.harass_target
    if spot is not None and not harass.still_there(brain, spot):
        # It is gone. Put the barrier on it before anything else -- this is
        # the half that makes the cut permanent.
        if orthogonal(brain.me, spot):
            position = Position(*spot)
            if ct.can_build_barrier(position):
                if attempt(ct.build_barrier, position):
                    debug.intent(brain, ct, "harass", f"BARRIER {spot}",
                                 "sealing the cut")
                    brain.harass_target = None
                    return True
            brain.harass_target = None      # cannot seal it; move on
        else:
            brain.harass_target = None

    if brain.harass_target is None:
        options = harass.targets(brain, enemy_core)
        brain.harass_target = options[0][0] if options else None

    spot = brain.harass_target
    if spot is None:
        # Nothing of theirs in sight. Their belt is probably the mirror of
        # ours -- same map, same problem -- so walk at that rather than at
        # their Core and hope.
        guesses = harass.mirrored_guess(brain)
        approach = (guesses[0] if guesses
                    else min(enemy_core, key=lambda t: manhattan(t, brain.me)))
        debug.intent(brain, ct, "harass", f"SCOUT->{approach}",
                     "mirrored guess" if guesses else "no target known")
        walk(brain, ct, approach, exact=False, hops=True)
        return True

    if orthogonal(brain.me, spot):
        position = Position(*spot)
        if ct.can_fire(position):
            attempt(ct.fire, position)
            debug.intent(brain, ct, "harass", f"CUT {spot}", "hitting the belt")
            return True
        debug.intent(brain, ct, "harass", "WAIT", "cannot afford to fire")
        return True
    debug.intent(brain, ct, "harass", f"WALK->{spot}", "closing on the belt")
    if not walk(brain, ct, spot, exact=False, hops=True):
        brain.harass_target = None
    return True
