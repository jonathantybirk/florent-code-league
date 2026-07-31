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
    REPAIR_RADIUS,
    CORE_PANIC_PERCENT,
    LONG_LINE_RESERVE,
    BLOCKED_TILE_PATIENCE,
    SLOT_HOME_UNDER_FIRE,
    SLOT_BUILDER_TICKET,
    SLOT_ECON_LINES,
    SLOT_LAUNCH_ID,
    SIEGE_ORE_RADIUS,
    SIEGE_ORE_FAR,
    RAID_MIN_GAP,
    SIEGE_LINE_MAX,
    SIEGE_SLOTS,
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
    p.fails = {}
    p.fortified = set()
    p.home_gunners = 0
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
    if p.phase == "explore" and ct.get_current_round() % 5 == 0:
        # New ground gets seen while wandering; re-offer the deposit search.
        p.phase = "idle"
    if _scorch(p, ct):
        return
    if _repair(p, ct):
        return
    if p.phase in ("idle", "explore") and _home_gunner(p, ct):
        return
    if p.phase in ("idle", "explore") and _fortify(p, ct):
        # Bricking the Core ring outranks a second income line: every strong
        # opponent here wins by placing Gunners against the Core itself.
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
    _step(p, ct, {t for t in world.adjacent4(p, tile)
                  if t not in world.blocked_tiles(p)} | {tile})


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


def _scorch(p, ct):
    """Burn our own producer rather than let it arm the Gunner beside it.

    A Harvester round-robins into every adjacent building regardless of owner,
    so a Gunner planted next to ours is fed by us, at 5 damage per titanium we
    mined. One Harvester is 20 Ti; the battery it feeds is worth hundreds. If
    we cannot shoot the Gunner off -- and a Builder has no ranged attack -- then
    taking our own building away is the only way to cut its supply.
    """
    for tile in sorted(set(p.my_harvesters) | set(p.conveyors)):
        if world.cheb(tile, p.core) > REPAIR_RADIUS + 3:
            continue
        # Only burn for a Gunner that can actually reach the Core. "Any Gunner
        # beside our Harvester" is baitable: a purpose-built opponent
        # (`probes/baiter`) plants shotless Gunners next to our producers and
        # makes us destroy a 20 Ti building and its income for their 10 Ti. It
        # beat us 16-14 doing exactly that.
        armed = False
        for neighbour in world.adjacent4(p, tile):
            if p.enemy_buildings.get(neighbour) not in (EntityType.GUNNER,
                                                        EntityType.SENTINEL):
                continue
            if any(world.dist_sq(neighbour, seat) <= GUNNER_RANGE_SQ
                   for seat in p.foot):
                armed = True
                break
        if not armed:
            continue
        target = Position(*tile)
        if ask(ct.can_destroy, target):
            ct.destroy(target)
            p.my_harvesters.discard(tile)
            p.conveyors.pop(tile, None)
            p.solids.discard(tile)
            log(ct, f"reaver t{p.ticket} scorched {tile}")
            return True
        spots = world.adjacent4(p, tile) - world.blocked_tiles(p)
        here = (ct.get_position().x, ct.get_position().y)
        if here not in spots and _step(p, ct, spots):
            return True
    return False


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
    spots = world.adjacent8(p, tile) - world.blocked_tiles(p)
    return _step(p, ct, spots)


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


def _core_ring(p):
    """The twelve tiles that touch our 2x2 Core footprint."""
    x, y = p.core
    ring = set()
    for dx in range(-1, 3):
        for dy in range(-1, 3):
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
        if here == tile:
            position = Position(*tile)
            if ask(ct.can_fire, position):
                ct.fire(position)
            p.stalls, p.clear_target = 0, None
            return
        if p.clear_target != tile:
            p.clear_target, p.stalls = tile, 0
        p.stalls += 1
        if p.stalls > BLOCKED_TILE_PATIENCE:
            p.stalls, p.clear_target = 0, None
            p.blacklist.add(tile)
            continue
        if _step(p, ct, {tile}):
            return
    _assist(p, ct)


def _siege(p, ct):
    if p.enemy_core is None:
        _explore(p, ct)
        return
    if _ferry(p, ct):
        return
    # A firing position we can already reach costs nothing to take, and a
    # producer the enemy paid for is the cheapest ammunition on the board.
    if _add_gunner(p, ct, without_travel=True):
        return
    ore = _pick_siege_ore(p, ct)
    if ore is not None and _forward_harvester(p, ct, ore) is False:
        return
    if _add_gunner(p, ct):
        return
    if _extend_feed(p, ct):
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


def _supply_tiles(p):
    """Every producer that could push a stack into a Gunner we place."""
    return set(p.feeders) | set(p.enemy_output)


def _pick_siege_ore(p, ct):
    """Claim a deposit close enough to the enemy Core to matter."""
    core = p.enemy_core
    if p.siege_ore is not None:
        return p.siege_ore
    taken = world.claimed_positions(p, ct, SIEGE_SLOTS)
    # Tiered, not a hard cutoff. A deposit within SIEGE_ORE_RADIUS can feed a
    # Gunner directly; a further one still can, through a short conveyor creep.
    # Some maps put no ore at all near a Core, and a flat cutoff made the whole
    # assault give up and explore for a thousand rounds on those.
    # The far tier is a last resort. If they already run a producer near their
    # own Core we would rather stand next to it than walk ten tiles to mine our
    # own -- their Harvester feeds our Gunner just as well as ours would.
    near_supply = any(world.cheb(t, core) <= SIEGE_ORE_RADIUS + 1
                      for t in p.enemy_output)
    limit = SIEGE_ORE_RADIUS if near_supply else SIEGE_ORE_FAR
    pool = [o for o in world.known_ores(p) - p.foot
            if world.cheb(o, core) <= limit and o not in taken]
    pool.sort(key=lambda o: (world.cheb(o, core), world.cheb(o, p.core), o))
    for ore in pool:
        if world.claim(ct, SIEGE_SLOTS, ore) is not None:
            p.siege_ore = ore
            log(ct, f"siege t{p.ticket} claims ore {ore}")
            return ore
    return None


def _forward_harvester(p, ct, ore):
    """Walk to the deposit and mine it.

    True once our Harvester stands there, False while still working on it, and
    None when the deposit turned out to be unusable -- the caller then falls
    through to parasitising whatever the enemy has already built nearby.
    """
    target = Position(*ore)
    if ct.is_in_vision(target):
        if ct.get_tile_env(target) != Environment.ORE_TITANIUM:
            # A mirrored prediction that reality disagrees with; drop it.
            log(ct, f"siege t{p.ticket} drop {ore}: not ore")
            _drop_siege_ore(p, ct)
            return None
        building = ct.get_tile_building_id(target)
        if building is not None:
            if ct.get_team(building) == ct.get_team():
                p.feeders.add(ore)
                return True
            # Their Harvester already feeds this deposit. Taking the tile costs
            # ten Builder attacks, but the stacks it produces are ours to shoot
            # with as soon as a Gunner stands beside it.
            log(ct, f"siege t{p.ticket} drop {ore}: enemy building")
            _drop_siege_ore(p, ct)
            return None

    def attempt():
        if ask(ct.can_build_harvester, target):
            ct.build_harvester(target)
            p.solids.add(ore)
            p.feeders.add(ore)
            log(ct, f"siege t{p.ticket} forward harvester {ore}")
            return True
        log(ct, f"siege t{p.ticket} cannot harvest {ore} from "
                f"{tuple(ct.get_position())}")
        return False

    _build_from(p, ct, ore, attempt)
    return False


def _drop_siege_ore(p, ct):
    if p.siege_ore is not None:
        world.unclaim(ct, SIEGE_SLOTS, p.siege_ore)
        p.rejected_ores.add(p.siege_ore)
        p.siege_ore = None


def _add_gunner(p, ct, without_travel=False):
    """Build one Gunner that both sees the Core and touches a supply.

    Returns True only when the round was actually spent on this: a Gunner
    placed, an enemy building chipped, or a step taken toward the tile. A
    truthful answer here matters, because the caller falls through to mining
    a forward deposit and an optimistic True starves the whole siege.
    """
    core_tiles = set(world.footprint(p.enemy_core))
    candidates = []
    for feeder in _supply_tiles(p):
        for delta in D4_DELTAS:
            spot = (feeder[0] + delta[0], feeder[1] + delta[1])
            if not world.inside(p, spot) or spot in core_tiles:
                continue
            if spot in p.blacklist or spot in p.gunners:
                continue
            if spot in world.known_walls(p) or spot in world.known_ores(p):
                continue
            if not _feeder_outputs_into(p, feeder, spot):
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


def _feeder_outputs_into(p, feeder, spot):
    """Will this producer actually push a stack onto `spot`?"""
    if feeder in p.enemy_output:
        facing = p.enemy_output[feeder]
    elif feeder in p.conveyors:
        facing = p.conveyors[feeder]
    else:
        facing = None                    # our own Harvester
    if facing is None:
        return True                      # Harvesters round-robin every side
    dx, dy = facing.delta()
    return (feeder[0] + dx, feeder[1] + dy) == spot


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


def _extend_feed(p, ct):
    """No Gunner slot touches the supply yet: creep a conveyor Core-ward."""
    core_tiles = set(world.footprint(p.enemy_core))
    ring = {t for tile in core_tiles for t in world.adjacent8(p, tile)
            if t not in core_tiles and t not in world.known_walls(p)
            and t not in world.known_ores(p)}
    # Their Harvesters are deliberately not tapped here. A Conveyor of ours
    # beside one does collect their titanium (probed and confirmed), but belting
    # it anywhere useful means laying tiles inside their base that nobody
    # repairs, and it measured worse both long and short: 12-18 and 13-17
    # against undertow, from 14-16. The mechanic is real; this use of it is not.
    best = None
    for feeder in p.feeders:
        if p.conveyors.get(feeder) is not None:
            continue                     # a conveyor already has its output
        line = plan.plan_line(p, feeder, ring, joinable=(),
                              max_length=SIEGE_LINE_MAX)
        if line and (best is None or len(line) < len(best)):
            best = line
    if not best:
        return False
    tile, facing = best[0]
    target = Position(*tile)
    if ct.is_in_vision(target) and ct.get_tile_building_id(target) is not None:
        return _clear_tile(p, ct, tile)

    def attempt():
        if ask(ct.can_build_conveyor, target, facing):
            ct.build_conveyor(target, facing)
            p.conveyors[tile] = facing
            p.feeders.add(tile)
            return True
        return False

    _build_from(p, ct, tile, attempt)
    return True


def _clear_tile(p, ct, tile):
    """Chip an enemy walkable building off a tile we want (2 Ti for 2 damage).

    A defender can deny the tile outright by parking a Builder on it -- a
    Builder is not a building, so it cannot be shot off and cannot be walked
    through. Give up on that tile rather than queue behind it forever: the
    conveyor one step upstream is the next candidate and feeds the same
    battery, so the blockade only costs them the tile they are standing on.
    """
    here = (ct.get_position().x, ct.get_position().y)
    if here == tile:
        position = Position(*tile)
        if ask(ct.can_fire, position):
            ct.fire(position)
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
    _step(p, ct, {tile})
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
    if here == target:
        position = Position(*here)
        if ask(ct.can_fire, position):
            ct.fire(position)
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
