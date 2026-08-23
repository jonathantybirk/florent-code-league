"""The Core: put the opening crew down, one Builder a round, on its own tile.

Seat i is spawned onto the ring tile the plan reserved for it, which is the
tile beside the first conveyor of the first lane that seat owns.  That is the
whole of the placement rule -- there is no separate "spawn toward the ore"
heuristic, because the plan already knows which ore this Builder is for.

If the reserved tile is occupied the seat waits rather than taking a different
tile: seats are identified by where they wake up, and a Builder put down on
the wrong tile would read itself as somebody else.
"""

import plan as planning
import walk


def run(player, ct):
    plan = planning.get(ct)
    if plan is None:
        return
    seat = player.spawned
    if seat >= len(plan.spawns):
        return
    tile = plan.spawns[seat]
    if tile is None:
        player.spawned += 1
        return
    spot = walk.at(tile)
    if not ct.can_spawn(spot):
        return
    try:
        ct.spawn_builder(spot)
    except Exception:
        return
    player.spawned += 1
