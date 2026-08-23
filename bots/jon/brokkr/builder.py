"""Builder Bot behaviour: mend when the Core is under fire, otherwise mine.

The mining loop walks a lane outward from the Core laying conveyors behind
itself. Standing on a tile blocks building on it, so the Builder always builds
the tile it has just stepped off -- two rounds per lane tile, against three if
it walked out first and laid the belt on the way home. Ore is walkable, which
is what lets the last conveyor and the Harvester both get built without the
Builder ever needing a tile it cannot reach.

Mending outranks mining unconditionally while the alarm is up. The arithmetic
is the whole reason this bot is an economy at all: healing is 4 HP per
titanium against a Sentinel's 1.8 HP of damage per titanium of ammunition, so
a rusher spending a fixed opening budget cannot out-shoot Builders who come
home. Four menders add ~16 HP a round to a 500 HP Core, which is more than the
~522 damage an all-in Sentinel ring can afford in total.
"""

from fcode import Direction, EntityType, GameError, Position

import debug
import defence
import lanes
import roster
import store
from brain import CARDINALS, DELTA

# Stop planning and just act if we are close to the 10 ms turn limit. The
# engine interrupts a unit that overruns, so the cheap actions have to happen
# before the expensive search, not after it.
CPU_BUDGET_US = 6000



# How far from home a Builder will still answer the mend alarm. Beyond this it
# is worth more finishing its lane than spending twenty rounds walking back.
MEND_RECALL_DIST = 14

# The first Builder is the home guard: it only takes deposits inside this
# radius, so it is always a few rounds from the Core. Traced against a Sentinel
# rush on stavkirke, the alarm went up on round 17 and the first mender arrived
# on round 36, by which point the Core was on 28 of 500 HP -- it survived only
# because the attacker ran out of ammunition first. A Builder that never left
# would have been healing from round 18.
GUARD_INDEX = 0
GUARD_RADIUS = 7


def run(player, ct) -> None:
    brain = player.brain
    brain.sense(ct)

    if brain.index is None:
        brain.index = store.claim_index(ct)
        debug.log(f"r{brain.round} b{ct.get_id()} INDEX={brain.index}")
    _gossip(brain, ct)

    if _mend(player, ct):
        return
    _mine(player, ct)


def _gossip(brain, ct) -> None:
    """Read the ore bulletin, then add one deposit of our own to it.

    Traced on stavkirke, Builders spawned on rounds 2-4 wandered until round
    12 with no deposit in sight, while the Core -- which sees radius 6 from
    round 0 -- had been looking at ore the whole time and had no way to say
    so. Sharing deposits is the cheapest thing the store can carry and it is
    what the opening was missing.
    """
    board = store.ore_board(ct)
    brain.learn_ore(board)
    spare = brain.unreported_ore(board)
    if spare is not None:
        store.publish_ore(ct, brain.index, spare)


# ----------------------------------------------------------------------
# defence
# ----------------------------------------------------------------------
def _mend(player, ct) -> bool:
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
    home = min(spots, key=lambda t: _manhattan(t, me))
    if _manhattan(home, me) > MEND_RECALL_DIST:
        return False

    for direction in CARDINALS:
        target = Position(me[0] + DELTA[direction][0], me[1] + DELTA[direction][1])
        if (target.x, target.y) in brain.core_tiles():
            if ct.can_heal(target):
                _try(ct.heal, target)
                debug.log(f"r{brain.round} b{ct.get_id()} HEAL at{me}")
                return True
            debug.log(f"r{brain.round} b{ct.get_id()} HEAL-BROKE at{me}")
            return True          # adjacent but cannot afford it: hold position
    # Exact: a heal spot is a specific tile, and the eight tiles around one
    # include the three that cannot reach the Core at all.
    step = _step_toward(brain, me, home, exact=True)
    if step is None:
        for spot in sorted(spots, key=lambda t: _manhattan(t, me)):
            step = _step_toward(brain, me, spot, exact=True)
            if step is not None:
                break
    debug.log(f"r{brain.round} b{ct.get_id()} WALKHOME at{me} home={home} step={step}")
    if step is not None:
        _try(ct.move, step)
    return True


# ----------------------------------------------------------------------
# economy
# ----------------------------------------------------------------------
def _mine(player, ct) -> None:
    brain = player.brain
    job = brain.job
    if job is not None and not _job_valid(brain, job):
        job = brain.job = None
    if job is None:
        if ct.get_cpu_time_elapsed() > CPU_BUDGET_US:
            return
        job = brain.job = _choose_job(brain, ct)
    if job is None:
        if brain.index == GUARD_INDEX:
            debug.log(f"r{brain.round} b{ct.get_id()} GUARD-HOLD at{brain.me}")
            _hold_home(brain, ct)
            return
        debug.log(f"r{brain.round} b{ct.get_id()} at{brain.me} NOJOB ore={len(brain.free_ore())} core={sorted(brain.core_tiles())}")
        _explore(brain, ct)
        return

    store.claim(ct, brain.index, job["deposit"])
    debug.log(f"r{brain.round} b{ct.get_id()} at{brain.me} dep{job['deposit']} route{job['route']}")
    _advance(brain, ct, job)


def _job_valid(brain, job) -> bool:
    """A job dies when its deposit is taken or its route is built on."""
    deposit = job["deposit"]
    state = brain.imap.state_at(*deposit)
    if state is not None and _name(state) not in ("ORE_FREE", "UNKNOWN"):
        return _name(state) == "OUR_HARVESTER" and False
    blocked = brain.terrain.blocked
    return not any(tile in blocked for tile in job["route"] if tile != brain.me)


def _choose_job(brain, ct):
    """Pick the deposit with the best payoff, planning routes for a few."""
    free = brain.free_ore()
    if not free:
        return None
    taken = store.claimed(ct, brain.index)
    free = [d for d in free if d not in taken]
    if not free:
        return None

    me = brain.me
    if brain.index == GUARD_INDEX:
        core = brain.core_tiles()
        if core:
            free = [d for d in free
                    if min(_manhattan(d, c) for c in core) <= GUARD_RADIUS]
            if not free:
                return None
    free.sort(key=lambda d: _manhattan(d, me))
    best = None
    for deposit in free[:3]:
        planned = lanes.plan_lane(brain, deposit)
        if planned is None:
            continue
        route, sink = planned
        # Prefer payoff, but break ties toward the Builder already standing
        # near the far end -- walking there is the delay the score prices.
        value = lanes.score_deposit(brain, deposit, route) - _manhattan(deposit, me)
        if best is None or value > best[0]:
            best = (value, {"deposit": deposit, "route": route, "sink": sink})
        if ct.get_cpu_time_elapsed() > CPU_BUDGET_US:
            break
    return best[1] if best else None


def _advance(brain, ct, job) -> None:
    """One turn of laying `job`'s lane, then its Harvester."""
    me = brain.me
    route, deposit, sink = job["route"], job["deposit"], job["sink"]
    facings = lanes.conveyor_facings(route, sink)

    need = None
    for tile in route:
        if not _has_conveyor(brain, tile, facings[tile]):
            need = tile
            break

    if need is None:
        _finish(brain, ct, deposit, route)
        return

    forward = _after(route, need, deposit)
    if me == need:
        step = _step_toward(brain, me, forward, exact=True)
        if step is not None:
            _try(ct.move, step)
        return
    if _orthogonal(me, need):
        target = Position(*need)
        facing = facings[need]
        if facing is not None and ct.can_build_conveyor(target, facing):
            if _try(ct.build_conveyor, target, facing):
                debug.log(f"r{brain.round} b{ct.get_id()} CONV {need}")
            return
        # Cannot afford it yet, or something arrived on the tile: wait rather
        # than walk away, so the lane does not get abandoned half-built.
        return
    step = _step_toward(brain, me, forward, exact=True)
    if step is not None:
        _try(ct.move, step)


def _finish(brain, ct, deposit, route) -> None:
    """Every conveyor is up; put the Harvester on the deposit."""
    me = brain.me
    if me == deposit:
        stand = route[-1] if route else _any_orthogonal(brain, deposit)
        if stand is not None:
            step = _step_toward(brain, me, stand, exact=True)
            if step is not None:
                _try(ct.move, step)
        return
    if _orthogonal(me, deposit):
        target = Position(*deposit)
        if ct.can_build_harvester(target):
            if _try(ct.build_harvester, target):
                debug.log(f"r{brain.round} b{ct.get_id()} HARV {deposit}")
        return
    step = _step_toward(brain, me, deposit, exact=False)
    if step is not None:
        _try(ct.move, step)


def _hold_home(brain, ct) -> None:
    """The guard with no nearby deposit waits beside the Core.

    Standing still is the point: its value is being one action away from
    healing, not the tiles it would otherwise reveal.
    """
    core = brain.core_tiles()
    if not core:
        return
    me = brain.me
    if any(_orthogonal(me, tile) for tile in core):
        return
    home = min(core, key=lambda t: _manhattan(t, me))
    step = _step_toward(brain, me, home, exact=False)
    if step is not None:
        _try(ct.move, step)


# ----------------------------------------------------------------------
# exploration
# ----------------------------------------------------------------------
def _explore(brain, ct) -> None:
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
            score = -_manhattan((x, y), me)
            if best_score is None or score > best_score:
                best, best_score = (x, y), score
    if best is None:
        return
    step = _step_toward(brain, me, best, exact=False)
    if step is not None:
        _try(ct.move, step)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _has_conveyor(brain, tile, facing) -> bool:
    state = brain.imap.state_at(*tile)
    if state is None:
        return False
    name = _name(state)
    if not name.startswith(("OUR_CONVEYOR_", "OUR_BOT_ON_CONVEYOR_")):
        return False
    if facing is None:
        return True
    return name.endswith("_" + _LETTER[facing])


def _after(route, tile, deposit):
    index = route.index(tile)
    return route[index + 1] if index + 1 < len(route) else deposit


def _any_orthogonal(brain, tile):
    for candidate in lanes.orthogonal(tile):
        if brain.terrain.inside(candidate) and candidate not in brain.terrain.blocked:
            return candidate
    return None


def _orthogonal(a, b) -> bool:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


def _manhattan(a, b) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _step_toward(brain, source, target, exact: bool):
    """First cardinal step of a safe route, or None if there is no route."""
    from utils.pathfinding import first_step
    try:
        nxt = first_step(brain.terrain, source, target, exact=exact, hops=False)
    except Exception:
        return None
    if nxt is None or nxt == source:
        return None
    step = (nxt[0] - source[0], nxt[1] - source[1])
    from brain import STEP_DIR
    return STEP_DIR.get(step)


def _try(action, *args) -> bool:
    """Run a Controller action, swallowing a refusal.

    An uncaught exception removes the unit from the match permanently, so
    every call the bot makes is wrapped. can_* is checked first everywhere
    this is used; this is the second line of defence, not the first.
    """
    try:
        action(*args)
        return True
    except GameError:
        return False


_LETTER = {Direction.NORTH: "N", Direction.EAST: "E",
           Direction.SOUTH: "S", Direction.WEST: "W"}

from utils.GCS.Base.protocol import TILE_STATES as _STATES  # noqa: E402


def _name(state: int) -> str:
    return _STATES[state]
