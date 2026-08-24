"""Builder behaviour: home economy, forward siege, and exploration."""

import os
import sys

from fcode import (Controller, Environment, EntityType, GameError,
                   Position)

import plan
import world
from constants import (
    CLAIM_SLOTS,
    WALKABLE_BUILDINGS,
    D4_DELTAS,
    D8,
    ECONOMY_BUILDERS,
    FACING8,
    GUNNER_RANGE_SQ,
    LAUNCH_HOPS,
    LAUNCH_MIN_GAP,
    FORTIFY_ROUND,
    HOME_GUNNERS,
    PICKET_LAUNCHERS,
    ECON_BEFORE_DEFENCE,
    REPAIR_RADIUS,
    CORE_PANIC_PERCENT,
    LONG_LINE_RESERVE,
    BLOCKED_TILE_PATIENCE,
    OUTHEALED_PATIENCE,
    SLOT_HOME_UNDER_FIRE,
    SLOT_BUILDER_TICKET,
    SLOT_ECON_LINES,
    SLOT_LAUNCH_ID,
    RAID_MIN_GAP,
    SLOT_SYMMETRY_A,
    SLOT_SYMMETRY_B,
)
from utils import pack_pos

DEBUG = bool(os.environ.get("VANGUARD_DEBUG"))

# A single trunk saturates at four Harvesters, but deposits far enough apart
# get their own line into the Core, and once the barrier ring and the repair
# crew hold the base the long game is decided on titanium mined.
MAX_HOME_HARVESTERS = 10

# A long trunk is both expensive and a gift: the enemy only has to stand on it
# to convert our income into their firing line.
HOME_LINE_MAX = 7


def log(ct, *args):
    if DEBUG:
        print(f"r{ct.get_current_round()}", *args, file=sys.stderr, flush=True)


def run(p: "object", ct: Controller) -> None:
    try:
        _run(p, ct)
    except GameError as error:
        log(ct, "GameError", error)
    except Exception as error:  # noqa: BLE001 - an escape would kill the unit
        log(ct, "ERROR", type(error).__name__, error)


def _run(p, ct):
    if not hasattr(p, "ticket"):
        _init(p, ct)
    world.sense(p, ct)
    world.update_symmetry(p, ct,
                          SLOT_SYMMETRY_A if p.ticket % 2 == 0 else SLOT_SYMMETRY_B)
    world.refresh_prediction(p, ct)
    if p.core is None:
        return
    if DEBUG and ct.get_current_round() % 25 == 0:
        log(ct, f"t{p.ticket} atk={p.attacker} phase={p.phase} "
                f"pos={tuple(ct.get_position())} enemy={p.enemy_core} "
                f"ore={p.siege_ore} feed={len(p.feeders)} gun={len(p.gunners)} ti={ct.get_global_resources()} gcost={ct.get_gunner_cost()} scale={ct.get_scale_percent():.2f}")
    if p.attacker and not p.gunners and ct.read_store(SLOT_HOME_UNDER_FIRE):
        # An attacker with no battery is contributing nothing, while at home
        # its heals are worth more titanium-for-titanium than their Gunners.
        p.attacker = False
    if p.attacker and p.raider:
        _raid(p, ct)
    elif p.attacker:
        _siege(p, ct)
    else:
        _economy(p, ct)


def _init(p, ct):
    p.ticket = ct.read_store(SLOT_BUILDER_TICKET)
    ct.write_store(SLOT_BUILDER_TICKET, p.ticket + 1)
    world.init(p, ct)
    # A Builder bought while the Core is already being shot is bought to save
    # it: healing is the cheapest damage-per-titanium in the game and the
    # siege is not going to arrive in time to matter.
    p.attacker = (p.ticket >= ECONOMY_BUILDERS
                  and not ct.read_store(SLOT_HOME_UNDER_FIRE))
    # The first attacker builds the battery; later ones raid instead of
    # queueing behind it. A standalone raider probe (`probes/reaver`) won an
    # economy 963 stacks to 256 by cutting belts beyond the enemy repair
    # radius, and one battery already saturates a forward Harvester.
    p.raider = p.attacker and p.ticket >= ECONOMY_BUILDERS + 2
    p.job = None            # claimed ore
    p.line = None           # planned conveyor chain
    p.phase = "idle"
    p.explored = set()
    p.siege_ore = None
    p.feeders = set()        # our producers near the enemy Core
    p.gunners = set()
    p.rejected_ores = set()
    p.stalls = 0
    p.clear_target = None
    p.hops = 0
    p.blacklist = set()
    p.chip_hp = {}
    p.chip_fails = {}
    p.fails = {}
    p.fortified = set()
    p.home_gunners = 0
    p.pickets = 0
    p.awaiting_launch = 0


# --------------------------------------------------------------------------
# Movement


def _step(p, ct, goals):
    """Descend a distance field toward `goals`; True when we actually moved.

    Builder Bots cannot walk through each other, and two of ours converging on
    the same corridor will otherwise stand face to face forever. Choosing the
    best *legal* move rather than only the shortest-path move lets one of them
    sidestep, and the id jitter stops both from picking the same detour.
    """
    if not goals:
        return False
    here = (ct.get_position().x, ct.get_position().y)
    if here in goals:
        return False
    field = world.distance_field(p, set(goals))
    current = field.get(here)
    options = []
    for index, direction in enumerate(D8):
        dx, dy = direction.delta()
        nxt = (here[0] + dx, here[1] + dy)
        reach = field.get(nxt)
        if reach is None or not ct.can_move(direction):
            continue
        options.append((reach, (ct.get_id() + dx * 3 + dy) % 7, index))
    if not options:
        return False
    reach, _, index = min(options)
    if current is not None and reach >= current + 2:
        return False
    ct.move(D8[index])
    return True


def ask(query, *args):
    """A can_* probe that answers False instead of raising out of vision."""
    try:
        return query(*args)
    except GameError:
        return False


def _build_from(p, ct, target, attempt):
    """Stand orthogonally adjacent to `target`, then run `attempt()`.

    Returns True once the building exists. Probing legality needs the tile in
    vision, so approach first and only then ask the engine.
    """
    here = (ct.get_position().x, ct.get_position().y)
    if ct.is_in_vision(Position(*target)) and attempt():
        return True
    spots = {t for t in world.adjacent4(p, target)
             if t not in world.blocked_tiles(p)}
    if here not in spots:
        _step(p, ct, spots)
    return False


# --------------------------------------------------------------------------
# Home economy


def _economy(p, ct):
    # Come home when the Core is under fire. `_repair` only sees damage inside
    # this Builder's own vision, so a Builder that wandered off to explore or
    # to mine never learns the base is dying and keeps wandering while the
    # Core burns down. The alarm is published in the store precisely so that
    # units with no line of sight can act on it.
    if ct.read_store(SLOT_HOME_UNDER_FIRE):
        here = (ct.get_position().x, ct.get_position().y)
        if world.cheb(here, p.core) > REPAIR_RADIUS:
            if _step(p, ct, world.adjacent4(p, p.core) - world.blocked_tiles(p)):
                return
    if p.phase == "explore" and ct.get_current_round() % 5 == 0:
        # New ground gets seen while wandering; re-offer the deposit search.
        p.phase = "idle"
    if _repair(p, ct):
        return
    # Income first, fortification second. Under 2.3.3 titanium *is* ammunition
    # is damage, so a deposit outranks a Barrier -- and this ordering was
    # letting Builders lay the ring while the strongest opponent out-mined us
    # five Harvesters to two.
    if (ct.read_store(SLOT_ECON_LINES) >= ECON_BEFORE_DEFENCE
            and p.phase in ("idle", "explore")):
        if _home_gunner(p, ct):
            return
        if _fortify(p, ct):
            return
    if p.phase in ("idle", "explore") and _picket(p, ct):
        return
    if p.phase == "idle":
        _pick_job(p, ct)
    if p.phase == "line":
        _lay_line(p, ct)
    elif p.phase == "harvester":
        _place_harvester(p, ct)
    elif p.phase == "done":
        if not _fortify(p, ct):
            _support(p, ct)
    else:
        _explore(p, ct)


def _pick_job(p, ct):
    if ct.read_store(SLOT_ECON_LINES) >= MAX_HOME_HARVESTERS:
        p.phase = "done"
        return
    here = (ct.get_position().x, ct.get_position().y)
    taken = world.home_claims(ct) | (p.ores & p.solids)
    # Among equally close deposits, take the one on the far side of the base.
    # The supply line to it then runs away from the enemy instead of laying a
    # row of 20 HP Conveyors across the ring tiles they walk in through -- and
    # a captured belt tile beside our Core is how these matches are lost.
    def exposure(ore):
        if p.enemy_core is None:
            return 0
        return -world.cheb(ore, p.enemy_core)

    candidates = sorted(p.ores - taken,
                        key=lambda ore: (world.cheb(ore, p.core),
                                         exposure(ore), ore))
    for ore in candidates[:6]:
        if world.walk_distance(p, here, world.adjacent8(p, ore)) is None:
            continue
        line = plan.plan_line(p, ore, p.foot, joinable=p.conveyors,
                              max_length=HOME_LINE_MAX)
        if line is None and ct.get_global_resources() > LONG_LINE_RESERVE:
            # Nothing close is left. An unresolved match is decided on
            # titanium delivered, so once the bank is deep a long belt is
            # better than a Builder standing still for eight hundred rounds.
            line = plan.plan_line(p, ore, p.foot, joinable=p.conveyors,
                                  max_length=HOME_LINE_MAX * 3)
        if line is None:
            continue
        slot = world.claim(ct, CLAIM_SLOTS, ore)
        if slot is None:
            continue
        p.job, p.line, p.claim_slot = ore, line, slot
        p.phase = "line" if line else "harvester"
        log(ct, f"econ ticket{p.ticket} ore={ore} line={len(line)}")
        return
    p.phase = "explore"


def _lay_line(p, ct):
    index = plan.next_unbuilt(p, p.line)
    if index is None:
        p.phase = "harvester"
        _place_harvester(p, ct)
        return
    # Build from the Core end backwards so a Harvester is never stranded.
    index = max(i for i, (tile, facing) in enumerate(p.line)
                if p.conveyors.get(tile) != facing)
    tile, facing = p.line[index]
    if tile in p.solids or tile in p.walls:
        replacement = plan.plan_line(p, p.job, p.foot, joinable=p.conveyors)
        if replacement is None:
            _release(p, ct)
            return
        p.line = replacement
        return
    target = Position(*tile)
    if ask(ct.can_build_conveyor, target, facing):
        ct.build_conveyor(target, facing)
        p.conveyors[tile] = facing
        if index == 0:
            p.phase = "harvester"
        return
    # Never step onto the tile itself. 2.2.0 let a Builder stand on a walkable
    # building and lay it under its own feet; 2.3.3 requires an orthogonally
    # adjacent target, so a Builder that walks on is stranded there for good --
    # this was silently costing us a third of the economy for whole matches.
    _step(p, ct, {t for t in world.adjacent4(p, tile)
                  if t not in world.blocked_tiles(p)})


def _place_harvester(p, ct):
    target = Position(*p.job)
    if ask(ct.can_build_harvester, target):
        ct.build_harvester(target)
        p.solids.add(p.job)
        ct.write_store(SLOT_ECON_LINES, ct.read_store(SLOT_ECON_LINES) + 1)
        log(ct, f"econ ticket{p.ticket} harvester at {p.job}")
        _release(p, ct, keep_claim=True)
        return
    if ct.get_tile_building_id(target) is not None:
        _release(p, ct, keep_claim=True)
        return
    _step(p, ct, {t for t in world.adjacent4(p, p.job)
                  if t not in world.blocked_tiles(p)})


def _release(p, ct, keep_claim=False):
    if not keep_claim and p.job is not None:
        packed = pack_pos(p.job)
        for slot in CLAIM_SLOTS:
            if ct.read_store(slot) == packed:
                ct.write_store(slot, 0)
                break
    p.job, p.line, p.phase = None, None, "idle"


def _repair(p, ct):
    """Out-heal the siege. Healing is strictly cheaper than shooting.

    A heal restores 4 HP for 1 Ti; a Gunner deals 10 damage for 2 Ti and can
    only fire every other round, so it averages 5 damage a round for 1 Ti. One
    Builder standing on our Core therefore very nearly cancels one Gunner, and
    two cancel two -- while their titanium is spent for good and ours keeps the
    Core alive. Barriers are worth mending for the same reason: their Builders
    chip at 2 damage a round, which a single heal beats outright.
    """
    # Sorted, fully-tie-broken selection everywhere: the engine does not
    # promise a stable order for its nearby-* queries, and an order-dependent
    # choice makes the whole match irreproducible and unmeasurable.
    hurt = None
    for building in ct.get_nearby_buildings():
        if ct.get_team(building) != ct.get_team():
            continue
        hp, full = ct.get_hp(building), ct.get_max_hp(building)
        if hp >= full:
            continue
        position = ct.get_position(building)
        tile = (position.x, position.y)
        # Only defend the home cluster; forward buildings are expendable.
        if world.cheb(tile, p.core) > REPAIR_RADIUS:
            continue
        # Triage by what is closest to dying, not by what looks important.
        # The Core has 500 HP of slack and we can always heal it later, but a
        # 20 HP Conveyor that falls leaves a hole in the ring -- and the hole
        # is exactly where they plant the Gunner that kills the Core.
        core = ct.get_entity_type(building) == EntityType.CORE
        urgent = core and hp * 100 < full * CORE_PANIC_PERCENT
        score = (0 if urgent else (2 if core else 1), hp, tile)
        if hurt is None or score < hurt[0]:
            hurt = (score, tile)
    if hurt is None:
        return False
    tile = hurt[1]
    target = Position(*tile)
    if ask(ct.can_heal, target):
        ct.heal(target)
        return True
    spots = world.adjacent4(p, tile) - world.blocked_tiles(p)
    return _step(p, ct, spots)


def _picket(p, ct):
    """Launchers beside our own Harvesters, to throw raiders off them.

    Make Fire ran six of these at Cambridge. A Launcher needs no ammunition at
    all, which under 2.3.3 means it is the only defence that costs nothing to
    keep firing, and a thrown Builder leaves the map rather than dying slowly.
    """
    if p.pickets >= PICKET_LAUNCHERS or ct.get_current_round() < FORTIFY_ROUND:
        return False
    if not p.my_harvesters:
        return False
    if ct.get_global_resources() < ct.get_launcher_cost() + 60:
        return False
    occupied = p.solids | set(p.conveyors) | set(p.enemy_buildings)
    for harvester in sorted(p.my_harvesters):
        for delta in D4_DELTAS:
            spot = (harvester[0] + delta[0], harvester[1] + delta[1])
            if not world.inside(p, spot) or spot in occupied or spot in p.foot:
                continue
            if spot in world.known_walls(p) or spot in world.known_ores(p):
                continue
            target = Position(*spot)

            def attempt(target=target, spot=spot):
                if ask(ct.can_build_launcher, target):
                    ct.build_launcher(target)
                    p.solids.add(spot)
                    p.pickets += 1
                    log(ct, f"picket t{p.ticket} launcher {spot}")
                    return True
                return False

            if _build_from(p, ct, spot, attempt):
                return True
            return True
    return False


def _home_gunner(p, ct):
    """Post a fed Gunner over the approach.

    This was measured as worse than nothing early on and removed -- but only
    against opponents whose assault was already dying to the barrier ring. A
    purpose-built counter (`probes/nemesis2`, this bot plus these Gunners) then
    beat us 16-14, and the diagnostics showed why: the Gunners are not really
    defence. Every attacker is a 40 HP Builder that cannot shoot back, so
    killing them on approach suppresses the enemy siege outright -- their Gunner
    count fell to 1.3 and ours rose, first battery landing on round 13 instead
    of 42. Re-measure removals against an opponent that can punish them.
    """
    if p.home_gunners >= HOME_GUNNERS or ct.get_current_round() < FORTIFY_ROUND:
        return False
    if p.enemy_core is None or not p.my_harvesters:
        return False
    if ct.get_global_resources() < ct.get_gunner_cost() + 40:
        return False
    occupied = p.solids | set(p.conveyors) | set(p.enemy_buildings)
    guarded = {tile for tile in p.conveyors
               if world.cheb(tile, p.core) <= REPAIR_RADIUS}
    # Kept beside a Harvester deliberately. Freeing the placement to any tile
    # near the Core -- the obvious move now that turrets need no supply -- won
    # the head-to-head against our own previous build 24-18 and still lost
    # overall, 165-45 against 174-36 across the shared panel.
    best = None
    for harvester in sorted(p.my_harvesters):
        for delta in D4_DELTAS:
            spot = (harvester[0] + delta[0], harvester[1] + delta[1])
            if not world.inside(p, spot) or spot in occupied or spot in p.foot:
                continue
            if spot in world.known_walls(p) or spot in world.known_ores(p):
                continue
            # Aim down our own belt by preference. It is a trap, not friendly
            # fire: a Gunner holds fire while the tile is merely a Conveyor,
            # and a raider has to *stand on* that tile to chip it, at which
            # point the Builder soaks the shot instead. Opponents now win by
            # cutting supply -- 1918 damage to our belts in one match -- and
            # this is the only thing that punishes it.
            facing = _ray_onto(p, spot, guarded, occupied)
            if facing is not None:
                score = (0, world.dist_sq(spot, p.enemy_core), spot)
            else:
                facing = _open_ray_toward(p, spot, p.enemy_core, occupied)
                if facing is None:
                    continue
                score = (1, world.dist_sq(spot, p.enemy_core), spot)
            if best is None or score < best[0]:
                best = (score, spot, facing)
    if best is None:
        return False
    _, spot, facing = best
    target = Position(*spot)

    def attempt():
        if ask(ct.can_build_gunner, target, facing):
            ct.build_gunner(target, facing)
            p.solids.add(spot)
            p.home_gunners += 1
            log(ct, f"nemesis t{p.ticket} home gunner {spot} {facing}")
            return True
        return False

    if _build_from(p, ct, spot, attempt):
        return True
    return world.cheb((ct.get_position().x, ct.get_position().y), spot) > 1


def _ray_onto(p, spot, wanted, occupied):
    """A facing whose ray stops exactly on one of `wanted`, nothing between."""
    if not wanted:
        return None
    for delta, facing in FACING8.items():
        for step in range(1, 4):
            tile = (spot[0] + delta[0] * step, spot[1] + delta[1] * step)
            if not world.inside(p, tile) or tile in world.known_walls(p):
                break
            if tile in wanted:
                return facing
            if tile in occupied or tile in p.foot:
                break
    return None


def _open_ray_toward(p, spot, threat, occupied):
    """A facing whose whole line is clear ground pointing at `threat`."""
    want = (threat[0] - spot[0], threat[1] - spot[1])
    ordered = sorted(FACING8.items(),
                     key=lambda kv: -(kv[0][0] * want[0] + kv[0][1] * want[1]))
    for delta, facing in ordered[:3]:
        for step in range(1, 4):
            tile = (spot[0] + delta[0] * step, spot[1] + delta[1] * step)
            if not world.inside(p, tile):
                break
            if tile in occupied or tile in world.known_walls(p) or tile in p.foot:
                break
        else:
            return facing
    return None


def _fortify(p, ct):
    """Wall the Core's ring so no Gunner can ever draw a bead on it.

    A Gunner's ray stops at the first building, and a Barrier is not walkable,
    so twelve Barriers (3 Ti each, +1% scale) turn point-blank Core sniping --
    the way every strong opponent here wins -- into a fifteen-round demolition
    job first. Tiles our own Conveyors and Harvesters occupy already block the
    ray, so only the gaps need paying for.
    """
    if ct.get_current_round() < FORTIFY_ROUND:
        return False
    if ct.get_global_resources() < ct.get_barrier_cost() + 30:
        return False
    ring = _core_ring(p)
    here = (ct.get_position().x, ct.get_position().y)
    open_tiles = [t for t in ring
                  if t not in p.solids and t not in world.known_walls(p)
                  and t not in p.conveyors and t not in p.fortified]
    if not open_tiles:
        return False
    # Brick the side they walk in from first: a half-finished ring that covers
    # the approach is worth more than a complete one that arrives too late.
    if p.enemy_core is not None:
        open_tiles.sort(key=lambda t: (world.dist_sq(t, p.enemy_core),
                                       world.cheb(t, here)))
    else:
        open_tiles.sort(key=lambda t: world.cheb(t, here))
    for tile in open_tiles[:3]:
        target = Position(*tile)
        if ct.is_in_vision(target) and ct.get_tile_building_id(target) is not None:
            p.fortified.add(tile)
            continue

        def attempt(target=target, tile=tile):
            if ask(ct.can_build_barrier, target):
                ct.build_barrier(target)
                p.solids.add(tile)
                p.fortified.add(tile)
                log(ct, f"fortify t{p.ticket} barrier {tile}")
                return True
            return False

        if _build_from(p, ct, tile, attempt):
            return True
        return True
    return False


def _core_ring(p, radius=1):
    """Tiles within `radius` of our 2x2 Core footprint."""
    x, y = p.core
    ring = set()
    for dx in range(-radius, 2 + radius):
        for dy in range(-radius, 2 + radius):
            tile = (x + dx, y + dy)
            if tile in p.foot or not world.inside(p, tile):
                continue
            ring.add(tile)
    return ring


def _support(p, ct):
    """Economy is saturated: reinforce, then help the siege."""
    p.attacker = True
    _siege(p, ct)


# --------------------------------------------------------------------------
# Forward siege
#
# Damage is throughput, not firepower: a Gunner converts 1 Ti of delivered
# ammunition into 5 damage, so a battery is worth exactly the titanium its
# supply can push into it. A Harvester round-robins its output into every
# adjacent building, which makes "Harvester on a forward deposit, Gunners
# packed around it" the cheapest 12.5 damage/round in the game -- no conveyor,
# no splitter, nothing for the defender to cut.


def _raid(p, ct):
    """Cut their supply where their repair crew will never reach it."""
    if p.enemy_core is None:
        _explore(p, ct)
        return
    if _ferry(p, ct):
        return
    here = (ct.get_position().x, ct.get_position().y)
    targets = sorted(
        (t for t, kind in p.enemy_buildings.items()
         if kind in WALKABLE_BUILDINGS and t not in p.blacklist),
        key=lambda t: (0 if world.cheb(t, p.enemy_core) > RAID_MIN_GAP else 1,
                       world.cheb(t, here), t))
    for tile in targets[:3]:
        if ask(ct.can_fire, Position(*tile)):
            ct.fire(Position(*tile))
            p.stalls, p.clear_target = 0, None
            return
        if p.clear_target != tile:
            p.clear_target, p.stalls = tile, 0
        p.stalls += 1
        if p.stalls > BLOCKED_TILE_PATIENCE:
            p.stalls, p.clear_target = 0, None
            p.blacklist.add(tile)
            continue
        # Stand *beside* it: 2.3.3 attacks an orthogonally adjacent tile, so
        # walking onto the belt means never being able to cut it.
        if _step(p, ct, world.adjacent4(p, tile) - world.blocked_tiles(p)):
            return
    _assist(p, ct)


def _siege(p, ct):
    """Put Gunners on their Core. Nothing else is needed any more.

    2.3.3 pays every turret from one team-wide pool, so a siege needs a firing
    line and titanium at home -- not a supply. The forward Harvester, the
    conveyor creep and the parasitism that 2.2.0 demanded are now pure
    overhead: rounds spent mining beside their base instead of placing another
    Gunner on their Core.
    """
    if p.enemy_core is None:
        _explore(p, ct)
        return
    if _ferry(p, ct):
        return
    if _add_gunner(p, ct, without_travel=True):
        return
    if _add_gunner(p, ct):
        return
    _assist(p, ct)


def _ferry(p, ct):
    """Build a Launcher beside us and ride it toward the enemy Core."""
    if p.hops >= LAUNCH_HOPS:
        return False
    here = (ct.get_position().x, ct.get_position().y)
    if world.cheb(here, p.enemy_core) < LAUNCH_MIN_GAP:
        p.hops = LAUNCH_HOPS
        return False
    if p.awaiting_launch:
        # The Launcher acts after us; hold still for the round it needs.
        p.awaiting_launch -= 1
        if p.awaiting_launch == 0:
            p.hops += 1
        ct.write_store(SLOT_LAUNCH_ID, ct.get_id())
        return True
    if ct.get_global_resources() < ct.get_launcher_cost() + 40:
        return False
    for delta in D4_DELTAS:
        spot = (here[0] + delta[0], here[1] + delta[1])
        if not world.inside(p, spot) or spot in world.blocked_tiles(p):
            continue
        position = Position(*spot)
        if ask(ct.can_build_launcher, position):
            ct.build_launcher(position)
            p.solids.add(spot)
            ct.write_store(SLOT_LAUNCH_ID, ct.get_id())
            p.awaiting_launch = 2
            log(ct, f"siege t{p.ticket} launcher {spot} hop {p.hops + 1}")
            return True
    return False


def _add_gunner(p, ct, without_travel=False):
    """Build one Gunner that both sees the Core and touches a supply.

    Returns True only when the round was actually spent on this: a Gunner
    placed, an enemy building chipped, or a step taken toward the tile. A
    truthful answer here matters, because the caller falls through to mining
    a forward deposit and an optimistic True starves the whole siege.
    """
    core_tiles = set(world.footprint(p.enemy_core))
    # Any tile with a firing line will do now. Under 2.2.0 a Gunner had to sit
    # beside a producer, because ammunition was a physical stack somebody had
    # to hand it; 2.3.3 feeds every turret from one team-wide pool, so the only
    # question left is whether the tile can see the Core.
    seats = set()
    for tile in core_tiles:
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                spot = (tile[0] + dx, tile[1] + dy)
                if world.dist_sq(spot, tile) <= GUNNER_RANGE_SQ:
                    seats.add(spot)
    candidates = []
    for spot in sorted(seats):
        if True:
            if not world.inside(p, spot) or spot in core_tiles:
                continue
            if spot in p.blacklist or spot in p.gunners:
                continue
            if spot in world.known_walls(p) or spot in world.known_ores(p):
                continue
            if spot not in world.known_seen(p):
                continue
            aim = _ray_to_core(p, spot, core_tiles)
            if aim is None:
                continue
                # No line to the Core yet -- still worth taking if the tile sits
                # on one of *their* producers. It gets fed by them, it shoots
                # whatever walks past, and buildings die and open lines as the
                # match goes on. A counter built on this rule (`probes/baiter`)
                # fielded 8.1 Gunners to our 6.8 and beat us 16-14.
                if feeder not in p.enemy_output:
                    continue
                towards = (p.enemy_core[0] - spot[0], p.enemy_core[1] - spot[1])
                step = (max(-1, min(1, towards[0])), max(-1, min(1, towards[1])))
                if step == (0, 0):
                    continue
                facing, obstacles = FACING8[step], 9
            else:
                facing, obstacles = aim
            # Prefer a clear line, but take a blocked one over no siege at all.
            candidates.append((obstacles, _flank_bias(p, spot),
                               world.dist_sq(spot, p.enemy_core), spot, facing))
    if not candidates:
        return False
    candidates.sort()
    for _, _, _, spot, facing in candidates[:4]:
        target = Position(*spot)
        if not ct.is_in_vision(target):
            if without_travel:
                continue
            if _step(p, ct, world.adjacent4(p, spot) - world.blocked_tiles(p)):
                return True
            continue
        holder = ct.get_tile_building_id(target)
        if holder is not None:
            if ct.get_team(holder) == ct.get_team():
                if ct.get_entity_type(holder) == EntityType.GUNNER:
                    p.gunners.add(spot)
                else:
                    p.blacklist.add(spot)
                continue
            # Their walkable building is squatting a firing position; two
            # damage a round clears it and their supply then feeds our Gunner.
            if ct.get_entity_type(holder) in WALKABLE_BUILDINGS:
                if without_travel:
                    continue
                return _clear_tile(p, ct, spot)
            p.blacklist.add(spot)
            continue
        here = (ct.get_position().x, ct.get_position().y)
        if here == spot:
            # Only Conveyors and Splitters may share a tile with a Builder, so
            # a Gunner can never be built under our own feet -- and the tile we
            # walked to in order to reach the Core ring is very often exactly
            # the tile we want to shoot from. Step off first.
            # Eight-connected: their ring often boxes us in cardinally while a
            # diagonal escape is open, and a Builder moves diagonally.
            away = world.adjacent8(p, spot) - world.blocked_tiles(p) - {spot}
            if _step(p, ct, away):
                return True
            p.blacklist.add(spot)
            continue
        if ask(ct.can_build_gunner, target, facing):
            ct.build_gunner(target, facing)
            p.solids.add(spot)
            p.gunners.add(spot)
            log(ct, f"siege t{p.ticket} gunner {spot} {facing}")
            return True
        spots = world.adjacent4(p, spot) - world.blocked_tiles(p)
        if here not in spots:
            if without_travel:
                continue
            if _step(p, ct, spots):
                return True
            continue
        # Adjacent, in vision, still refused: almost always unaffordable.
        p.fails[spot] = p.fails.get(spot, 0) + 1
        if p.fails[spot] > 6:
            p.blacklist.add(spot)
        return False
    return False


def _flank_bias(p, spot):
    """Push successive attackers onto opposite sides of the enemy Core.

    Attackers that all pick the same best tile queue up behind each other, and
    a defender only has to deny that one square. Splitting the approach means
    a single parked Builder can no longer stall the whole siege, and it forces
    their repair crew to cover two fronts at once.
    """
    if p.enemy_core is None:
        return 0
    rank = max(0, p.ticket - ECONOMY_BUILDERS)
    side = (spot[0] - p.enemy_core[0]) + (spot[1] - p.enemy_core[1]) >= 0
    return 0 if side == (rank % 2 == 0) else 1


def _ray_to_core(p, spot, core_tiles):
    """A facing whose ray reaches the Core, and how much is in the way.

    Returns (facing, obstacles) or None. Only walls and our own buildings block
    permanently -- an enemy building in the line is a 20-to-30 HP speed bump
    that the Gunner itself demolishes at 10 damage a shot before carrying on
    into the Core. A defender who bricks up their Core ring is buying about
    three shots, not immunity, and refusing those firing positions is how a
    siege stalls against a turtle forever.
    """
    walls = world.known_walls(p)
    best = None
    for delta, facing in FACING8.items():
        obstacles = 0
        for step in range(1, 4):
            tile = (spot[0] + delta[0] * step, spot[1] + delta[1] * step)
            if world.dist_sq(spot, tile) > GUNNER_RANGE_SQ:
                break
            # The Core is itself a building, so it must be tested before any
            # blocker check or every ray "stops on an obstacle" at the target.
            if tile in core_tiles:
                if best is None or obstacles < best[1]:
                    best = (facing, obstacles)
                break
            if not world.inside(p, tile) or tile in walls:
                break
            if tile in p.enemy_buildings:
                obstacles += 1
                continue
            if tile in p.solids:
                break                    # one of ours, and we will not shoot it
            # Empty ground: keep tracing.
    return best


def _clear_tile(p, ct, tile):
    """Chip an enemy walkable building off a tile we want (2 Ti for 2 damage).

    A defender can deny the tile outright by parking a Builder on it -- a
    Builder is not a building, so it cannot be shot off and cannot be walked
    through. Give up on that tile rather than queue behind it forever: the
    conveyor one step upstream is the next candidate and feeds the same
    battery, so the blockade only costs them the tile they are standing on.
    """
    here = (ct.get_position().x, ct.get_position().y)
    # 2.3.3 inverted the attack rule: a Builder may only damage an orthogonally
    # adjacent tile, never the one it stands on. can_fire() enforces that, so
    # ask it rather than reimplementing the geometry.
    if ask(ct.can_fire, Position(*tile)):
        # Give up on anything they out-heal. A Builder deals 2 damage a round
        # and a heal restores 4, so a repaired target can never fall and every
        # round spent on it is wasted. Make Fire published the same heuristic
        # after Cambridge -- they abandoned conveyors that had been healed.
        hp = ask(ct.get_hp, ct.get_tile_building_id(Position(*tile)))
        seen = p.chip_hp.get(tile)
        if seen is not None and hp is not False and hp >= seen:
            p.chip_fails[tile] = p.chip_fails.get(tile, 0) + 1
            if p.chip_fails[tile] >= OUTHEALED_PATIENCE:
                p.blacklist.add(tile)
                p.clear_target = None
                log(ct, f"t{p.ticket} abandons out-healed {tile}")
                return False
        p.chip_hp[tile] = hp if hp is not False else 0
        ct.fire(Position(*tile))
        p.stalls, p.clear_target = 0, None
        return True
    # Count rounds spent wanting this tile, not failed moves: a Builder denied
    # the tile still shuffles between the two squares beside it every round,
    # and a counter that resets on movement would never notice.
    if p.clear_target != tile:
        p.clear_target, p.stalls = tile, 0
    p.stalls += 1
    if p.stalls > BLOCKED_TILE_PATIENCE:
        p.stalls, p.clear_target = 0, None
        p.blacklist.add(tile)
        log(ct, f"siege t{p.ticket} gives up on denied tile {tile}")
        return False
    _step(p, ct, world.adjacent4(p, tile) - world.blocked_tiles(p))
    return True


def _assist(p, ct):
    """Nothing to build here yet: close on the Core, then damage what we can.

    Every producer we can shoot from has to be *seen* first, and a Harvester on
    a deposit near their Core is the usual one. An attacker that wanders when
    it finds no forward deposit never brings their base into vision at all --
    on maps whose deposits sit away from the Cores it simply explored for a
    thousand rounds while both economies idled to a tiebreak.
    """
    # Close until the Core is genuinely in vision rather than to a fixed
    # distance: a Builder sees r^2 = 20, so a standoff measured in king moves
    # parks it four tiles out, seeing none of the ring it came to shoot, and
    # exploring instead for the rest of the match.
    if p.enemy_core is not None:
        if not ct.is_in_vision(Position(*p.enemy_core)):
            if _step(p, ct, world.adjacent8(p, p.enemy_core)):
                return
    _harass(p, ct)

# --------------------------------------------------------------------------
# Harassment and exploration


HARASS_VALUE = {
    EntityType.SPLITTER: 0,
    EntityType.CONVEYOR: 1,
    EntityType.HARVESTER: 2,
}


def _harass(p, ct):
    """Chip enemy logistics; a Builder can only damage its own tile."""
    here = (ct.get_position().x, ct.get_position().y)
    targets = sorted(
        (t for t, kind in p.enemy_buildings.items() if kind in HARASS_VALUE),
        key=lambda t: (HARASS_VALUE[p.enemy_buildings[t]],
                       world.cheb(t, here), t),
    )
    if not targets:
        _explore(p, ct)
        return
    target = targets[0]
    if ask(ct.can_fire, Position(*target)):
        ct.fire(Position(*target))
        return
    if not _step(p, ct, {target}):
        _explore(p, ct)


def _explore(p, ct):
    here = (ct.get_position().x, ct.get_position().y)
    alive = world.surviving(p, ct)
    if p.enemy_core is None and alive:
        target = alive[p.ticket % len(alive)]
        if world.cheb(here, target) > 3:
            if _step(p, ct, world.adjacent8(p, target)):
                return
    # Spiral coverage from our own Core -- ordering waypoints by ring distance
    # and angle, the way Make Fire did -- was tried and rejected. It beat the
    # strongest archived opponent by three games and lost four to the next one,
    # scored identically against the live bot, and left the panel a shade worse
    # (262-32 against 264-30). One favourable opponent is not enough.
    stride = 4
    choices = [(x, y)
               for y in range(1, p.h, stride) for x in range(1, p.w, stride)
               if (x, y) not in p.explored and (x, y) not in p.walls
               and (x, y) not in p.solids]
    if not choices:
        p.explored.clear()
        return
    target = min(choices, key=lambda q: (world.cheb(q, here), q))
    if world.dist_sq(target, here) <= 20:
        p.explored.add(target)
        _explore(p, ct)
        return
    _step(p, ct, {target})
