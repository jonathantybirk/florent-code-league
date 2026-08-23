"""Turning a known deposit into titanium arriving at the Core.

One job at a time, held on the Builder: pick a deposit, plan the lane that
connects it, lay that lane from the sink end outward so the belt is useful
before it is finished, then put the Harvester on the deposit. The Builder that
has no job explores, because a deposit nobody has seen is worth nothing.

Route planning and the question of what counts as a delivery point live in
lanes.py; this module is only the Builder's side of it.
"""
from fcode import Position

import debug
import lanes
import store
from movement import (LETTER, STATES, UNSTICK_ABANDON, any_orthogonal,
                      attempt, manhattan, name_of, orthogonal, step_toward,
                      walk)
CPU_BUDGET_US = 6000



# Turns without getting any closer to the job before a Builder gives it up.
#
# Progress has to be measured as distance to the goal, and neither of the two
# obvious alternatives works. Counting failed moves misses everything: an
# enemy Launcher picks a Builder up and throws it back, so the move succeeds
# every round. Counting repeated tiles misses it too, because the Builder is
# thrown to a slightly different tile each time and oscillates between two.
# On helheim one Builder spent 120 of a 284-round game inside an enemy
# Launcher's ring, walking hard and arriving nowhere, while the game was lost
# 0 titanium to 1700.
STUCK_LIMIT = 8

# The first Builder is the home guard: it only takes deposits inside this
# radius, so it is always a few rounds from the Core. Traced against a Sentinel
# rush on stavkirke, the alarm went up on round 17 and the first mender arrived
# on round 36, by which point the Core was on 28 of 500 HP -- it survived only
# because the attacker ran out of ammunition first. A Builder that never left
# would have been healing from round 18.
GUARD_INDEX = 0
GUARD_RADIUS = 7




def mine(player, ct) -> None:
    brain = player.brain
    job = brain.job
    if job is not None:
        gap = manhattan(brain.me, job["deposit"])
        if gap < job.get("closest", 10 ** 6):
            job["closest"] = gap
            brain.stuck = 0
        else:
            brain.stuck += 1
    if job is not None and brain.frozen >= UNSTICK_ABANDON:
        debug.intent(brain, ct, "mine", "ABANDON",
                     f"pinned {brain.frozen} turns, giving up {job['deposit']}")
        brain.blacklist.add(job["deposit"])
        job = brain.job = None
        brain.stuck = 0
        brain.frozen = 0
    if job is not None and (not job_valid(brain, job) or brain.stuck >= STUCK_LIMIT):
        if brain.stuck >= STUCK_LIMIT:
            debug.intent(brain, ct, "mine", "ABANDON",
                         f"no closer to {job['deposit']} in {brain.stuck} turns")
            brain.blacklist.add(job["deposit"])
        job = brain.job = None
        brain.stuck = 0
    if job is None:
        if ct.get_cpu_time_elapsed() > CPU_BUDGET_US:
            return
        job = brain.job = choose_job(brain, ct)
    if job is None:
        if brain.index == GUARD_INDEX:
            debug.log(f"r{brain.round} b{ct.get_id()} GUARD-HOLD at{brain.me}")
            hold_home(brain, ct)
            return
        debug.intent(brain, ct, "mine", "EXPLORE",
                     f"no job; {len(brain.free_ore())} ore known")
        explore(brain, ct)
        return

    store.claim(ct, brain.index, job["deposit"])
    advance(brain, ct, job)


def job_valid(brain, job) -> bool:
    """A job dies when its deposit is taken or its route is built on."""
    deposit = job["deposit"]
    state = brain.imap.building_at(*deposit)
    name = None if state is None else name_of(state)
    if job.get("repair"):
        # A repair is finished when the belt reaches the Core again, and dead
        # if somebody destroyed the Harvester we were reconnecting.
        if name is not None and name != "OUR_HARVESTER":
            return False
        return deposit in set(lanes.orphaned_harvesters(brain))
    # The deposit is still ours to take while nothing is built on it. EMPTY is
    # the answer the building layer gives for free ore, so it belongs here.
    if name is not None and name != "EMPTY":
        return False
    blocked = brain.terrain.blocked
    return not any(tile in blocked for tile in job["route"] if tile != brain.me)


def choose_job(brain, ct):
    """Pick the deposit with the best payoff, planning routes for a few."""
    free = brain.free_ore()
    if not free:
        return None
    taken = store.claimed(ct, brain.index) | brain.blacklist

    # Reconnect a Harvester of ours whose belt has been cut, before laying any
    # new lane. It is already paid for, so re-linking it is the cheapest
    # titanium on the board -- and leaving it severed is exactly what makes
    # cutting our belt worth more to them than cutting theirs is to us.
    for harvester in lanes.orphaned_harvesters(brain):
        if harvester in taken:
            continue
        planned = lanes.plan_lane(brain, harvester)
        if planned is None:
            continue
        route, sink = planned
        if not route:
            continue
        return {"deposit": harvester, "route": route, "sink": sink,
                "repair": True}

    free = [d for d in free if d not in taken]
    if not free:
        return None

    me = brain.me
    if brain.index == GUARD_INDEX:
        core = brain.core_tiles()
        if core:
            near = [d for d in free
                    if min(manhattan(d, c) for c in core) <= GUARD_RADIUS]
            # The radius is a preference, not a prohibition. Enforcing it
            # absolutely put 1392 of auroraveil's unit-turns into GUARD-HOLD:
            # every deposit on that map is about twelve tiles out, so the
            # guard stood beside the Core for the whole match. Staying home is
            # worth something; it is not worth the guard's entire output.
            if near:
                free = near
    free.sort(key=lambda d: manhattan(d, me))
    best = None
    for deposit in free[:3]:
        planned = lanes.plan_lane(brain, deposit)
        if planned is None:
            continue
        route, sink = planned
        # Prefer payoff, but break ties toward the Builder already standing
        # near the far end -- walking there is the delay the score prices.
        value = lanes.score_deposit(brain, deposit, route) - manhattan(deposit, me)
        if best is None or value > best[0]:
            best = (value, {"deposit": deposit, "route": route, "sink": sink})
        if ct.get_cpu_time_elapsed() > CPU_BUDGET_US:
            break
    return best[1] if best else None


def advance(brain, ct, job) -> None:
    """One turn of laying `job`'s lane, then its Harvester."""
    me = brain.me
    route, deposit, sink = job["route"], job["deposit"], job["sink"]
    facings = lanes.conveyor_facings(route, sink)

    need = None
    for tile in route:
        if not has_conveyor(brain, tile, facings[tile]):
            need = tile
            break

    if need is None:
        if job.get("repair"):
            debug.intent(brain, ct, "mine", f"REPAIRED {deposit}",
                         "belt reconnected")
            brain.job = None
            return
        finish(brain, ct, deposit, route)
        return

    forward = after_tile(route, need, deposit)
    if me == need:
        step = None
        debug.intent(brain, ct, "mine", f"STEPOFF->{forward}",
                     f"lane {deposit} needs {need}, standing on it")
        walk(brain, ct, forward, exact=True)
        return
    if orthogonal(me, need):
        target = Position(*need)
        facing = facings[need]
        if facing is not None and ct.can_build_conveyor(target, facing):
            if attempt(ct.build_conveyor, target, facing):
                debug.intent(brain, ct, "mine", f"CONV {need}",
                             f"lane {deposit}, {len(route)} tiles")
            return
        # Cannot afford it yet, or something arrived on the tile: wait rather
        # than walk away, so the lane does not get abandoned half-built.
        debug.intent(brain, ct, "mine", f"WAIT for {need}",
                     f"conveyor costs {ct.get_conveyor_cost()}, "
                     f"have {ct.get_global_resources()}")
        return
    debug.intent(brain, ct, "mine", f"WALK->{forward}",
                 f"lane {deposit} needs {need}")
    walk(brain, ct, forward, exact=True)


def finish(brain, ct, deposit, route) -> None:
    """Every conveyor is up; put the Harvester on the deposit."""
    me = brain.me
    if me == deposit:
        stand = route[-1] if route else any_orthogonal(brain, deposit)
        if stand is not None:
            step = step_toward(brain, me, stand, exact=True)
            if step is not None:
                attempt(ct.move, step)
        return
    if orthogonal(me, deposit):
        target = Position(*deposit)
        if ct.can_build_harvester(target):
            if attempt(ct.build_harvester, target):
                debug.intent(brain, ct, "mine", f"HARV {deposit}", "lane complete")
            return
        debug.intent(brain, ct, "mine", f"WAIT harvester {deposit}",
                     f"costs {ct.get_harvester_cost()}, "
                     f"have {ct.get_global_resources()}")
        return
    step = step_toward(brain, me, deposit, exact=False)
    if step is not None:
        attempt(ct.move, step)


def hold_home(brain, ct) -> None:
    """The guard with no nearby deposit waits beside the Core.

    Standing still is the point: its value is being one action away from
    healing, not the tiles it would otherwise reveal.
    """
    core = brain.core_tiles()
    if not core:
        return
    me = brain.me
    if any(orthogonal(me, tile) for tile in core):
        return
    home = min(core, key=lambda t: manhattan(t, me))
    step = step_toward(brain, me, home, exact=False)
    if step is not None:
        attempt(ct.move, step)


def explore(brain, ct) -> None:
    """No deposit to work: walk toward the largest unseen region.

    Knowing the map's symmetry converts every tile we look at into two, so the
    heading that reveals most is the one pointing away from what we have
    already seen. This is deliberately crude -- a real frontier search is a
    mining-module concern -- but it stops Builders standing still.
    """
    imap = brain.imap
    me = brain.me
    best, best_score = None, None
    for x in range(0, brain.width, 2):
        for y in range(0, brain.height, 2):
            if (x, y) in imap.tiles:
                continue
            score = -manhattan((x, y), me)
            if best_score is None or score > best_score:
                best, best_score = (x, y), score
    if best is None:
        return
    step = step_toward(brain, me, best, exact=False)
    if step is not None:
        attempt(ct.move, step)


def has_conveyor(brain, tile, facing) -> bool:
    state = brain.imap.building_at(*tile)
    if state is None:
        return False
    name = name_of(state)
    if not name.startswith(("OUR_CONVEYOR_", "OUR_BOT_ON_CONVEYOR_")):
        return False
    if facing is None:
        return True
    return name.endswith("_" + LETTER[facing])


def after_tile(route, tile, deposit):
    index = route.index(tile)
    return route[index + 1] if index + 1 < len(route) else deposit
