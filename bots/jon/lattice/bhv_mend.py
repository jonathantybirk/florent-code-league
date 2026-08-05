"""Mend: heal damaged friendly entities.

This is the cheapest titanium in the game and the reason the bot is built the way
it is. Healing restores 4 HP for a flat 1 Ti and is **immune to cost scale**,
while a Sentinel spends 10 ammo (10 Ti) to deal 18 damage. Defence therefore buys
4 HP per titanium against offence's 1.8 -- a 2.2x edge.

The consequence is strategic, not tactical: one Builder standing on a Core and
healing absorbs two thirds of a Sentinel indefinitely, so a tended Core does not
die, so most games run to the round-1000 tiebreak. Everything else in this bot is
downstream of that.

A heal hits *all* friendly entities on the target tile, so a Builder standing on
a damaged conveyor is healed together with it in one action.
"""
from __future__ import annotations

from fcode import EntityType, GameError

import config
import geom
import nav

NAME = "mend"

# What healing an adjacent thing is worth, keyed on its priority tier. Deliberately
# below `route` (5.5) for anything but the Core and turrets: the belt is the win
# condition, and a scratched conveyor can wait for a round with nothing better.
ADJACENT_SCORE = {6: 7.4, 5: 5.8, 4: 3.4, 3: 3.0, 2: 2.4, 1: 2.0}

# What is worth spending the round on, most valuable first. The Core is the game;
# turrets are the win condition; carriers are the tiebreak.
PRIORITY = {
    EntityType.CORE: 6,
    EntityType.SENTINEL: 5,
    EntityType.GUNNER: 5,
    EntityType.HARVESTER: 4,
    EntityType.LAUNCHER: 3,
    EntityType.CONVEYOR: 2,
    EntityType.SPLITTER: 2,
    EntityType.BARRIER: 1,
}


def _targets(ctx):
    """Damaged friendly things on orthogonally adjacent tiles."""
    ct, wm = ctx.ct, ctx.wm
    if wm.me is None:
        return []
    out = []
    for nb in geom.orth_neighbours(wm.me, wm.w, wm.h):
        key = (nb.x, nb.y)
        s = wm.buildings.get(key)
        if s is None or s.team != wm.team:
            continue
        try:
            hp = ct.get_hp(ct.get_tile_building_id(nb))
            mx = ct.get_max_hp(ct.get_tile_building_id(nb))
        except GameError:
            continue
        missing = mx - hp
        if missing < config.MENDER_MIN_DAMAGE:
            continue
        out.append((PRIORITY.get(s.etype, 1), missing, nb))
    out.sort(reverse=True, key=lambda t: (t[0], t[1]))
    return out


def _wounded_remote(ctx):
    """Damaged friendly buildings we are *not* standing next to.

    Healing only reaches an orthogonally adjacent tile, so without this the bot
    can watch its Core be shelled from across the map and never walk home. That
    is the whole defence: a Sentinel deals 6 HP a round and a mender restores 4,
    so two Builders on a Core out-heal a two-Sentinel battery outright.
    """
    ct, wm = ctx.ct, ctx.wm
    out = []
    for s in wm.my_buildings():
        prio = PRIORITY.get(s.etype, 1)
        if prio < 5:
            # Only the Core and turrets justify abandoning what we are doing.
            # Walking across the map to heal a shelled conveyor is exactly the
            # losing exchange: they spend ammunition, we spend the Builder-rounds
            # that were supposed to be laying the belt that wins the tiebreak.
            continue
        try:
            hp = ct.get_hp(s.eid)
            mx = ct.get_max_hp(s.eid)
        except GameError:
            continue
        missing = mx - hp
        if missing < config.MENDER_MIN_DAMAGE:
            continue
        out.append((prio, missing, s.pos))
    out.sort(reverse=True, key=lambda t: (t[0], t[1]))
    return out


def score(ctx) -> float:
    if ctx.titanium() < 1 or ctx.wm.me is None:
        return 0.0

    if ctx.can_act():
        hits = _targets(ctx)
        if hits:
            ctx.scratch["mend"] = hits[0][2]
            prio, missing, _ = hits[0]
            base = ADJACENT_SCORE.get(prio, 2.0)
            if missing >= 20:
                base += 0.8
            return min(base, config.CEILINGS[NAME] - 0.01)

    # Nothing adjacent needs us, but something valuable elsewhere might.
    if not ctx.can_move():
        return 0.0
    remote = _wounded_remote(ctx)
    if not remote:
        return 0.0
    prio, missing, pos = remote[0]
    ctx.scratch["mend_walk"] = pos
    d = geom.manhattan(pos, ctx.wm.me)
    # A dying Core pulls Builders home from anywhere, and pulls harder the worse
    # it is: at 100 HP down this outranks every economic behaviour on the board.
    urgency = 3.0 + min(missing, 200) * 0.02 - 0.04 * min(d, 40)
    if prio < 6:
        urgency -= 1.5
    if ctx.role == "warden" and prio == 6:
        urgency += 3.0        # the warden's whole job; distance does not excuse it
    return max(0.0, min(urgency, config.CEILINGS[NAME] - 0.02))


def run(ctx) -> bool:
    pos = ctx.scratch.get("mend")
    if pos is not None:
        try:
            if ctx.ct.can_heal(pos):
                ctx.ct.heal(pos)
                return True
        except GameError:
            pass

    walk = ctx.scratch.get("mend_walk")
    if walk is not None:
        approach = set()
        for nb in geom.orth_neighbours(walk, ctx.wm.w, ctx.wm.h):
            nk = (nb.x, nb.y)
            if nk in ctx.wm.walls:
                continue
            s = ctx.wm.buildings.get(nk)
            if s is not None and s.etype in nav._BLOCKERS:
                continue
            approach.add(nk)
        if approach:
            return nav.step_toward(ctx.ct, ctx.wm, approach, avoid_threat=False)
    return False
