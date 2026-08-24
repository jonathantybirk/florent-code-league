"""Answering the Core's alarm: come home and heal.

The sizing of the mend squad, and the arithmetic that makes healing the
correct answer to a rush at all, live in defence.py. This module is only what
one Builder does about it -- decide whether the alarm is addressed to it, walk
to a tile it can actually heal from, and heal.
"""
from fcode import Position

import debug
import defence
import roster
import store
from brain import CARDINALS, DELTA
from movement import attempt, manhattan, step_toward
# How far from home a Builder will still answer the mend alarm. Beyond this it
# is worth more finishing its lane than spending twenty rounds walking back.
MEND_RECALL_DIST = 14



def mend(player, ct) -> bool:
    """Return True if this Builder spent its turn on the Core's HP."""
    brain = player.brain
    wanted = store.alarm_level(ct)
    if not wanted:
        return False
    target = roster.econ_target(brain.width, brain.height)
    if brain.index is None or not roster.is_mender(brain.index, wanted, target):
        return False
    if brain.imap.our_core is None:
        return False
    me = brain.me
    spots = defence.heal_spots(brain)
    if not spots:
        return False
    home = min(spots, key=lambda t: manhattan(t, me))
    if manhattan(home, me) > MEND_RECALL_DIST:
        return False

    for direction in CARDINALS:
        target = Position(me[0] + DELTA[direction][0], me[1] + DELTA[direction][1])
        if (target.x, target.y) in brain.core_tiles():
            if ct.can_heal(target):
                attempt(ct.heal, target)
                debug.intent(brain, ct, "mend", "HEAL")
                return True
            debug.intent(brain, ct, "mend", "HOLD", "cannot afford to heal")
            return True          # adjacent but cannot afford it: hold position
    # Exact: a heal spot is a specific tile, and the eight tiles around one
    # include the three that cannot reach the Core at all.
    step = step_toward(brain, me, home, exact=True)
    if step is None:
        for spot in sorted(spots, key=lambda t: manhattan(t, me)):
            step = step_toward(brain, me, spot, exact=True)
            if step is not None:
                break
    debug.intent(brain, ct, "mend", f"WALK->{home}",
                 "no route home" if step is None else "coming home")
    if step is not None:
        attempt(ct.move, step)
    return True
