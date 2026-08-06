"""Map-agnostic online economy planner and explorer."""

from collections import deque
import sys
from typing import TYPE_CHECKING

from fcode import Controller, EntityType, Environment, GameError, Position

import doctrine
from constants import (
    CLAIM_SLOTS,
    GUARD_CHASE_STEPS,
    GUARD_RADIUS_SQ,
    MAX_GUARD_GUNNERS,
    CORE_THREAT_RADIUS_SQ,
    CPU_SOFT_BUDGET_US,
    D4_DELTAS,
    D8,
    ECON_EXPAND_ROUND,
    FACING,
    LAUNCHER_BUILDER_INDEX,
    LAUNCHER_BUILDERS,
    LAUNCH_DIRECTION_BITS,
    LAUNCH_REJECTION_FLAG,
    LAUNCH_REJECTION_POSITION_BITS,
    LAUNCH_REJECTION_POSITION_MASK,
    LAUNCH_REQUEST_SLOTS,
    MIN_AMMO_FOR_SENTINEL,
    NETWORK_CAP_EARLY,
    NETWORK_CAP_LATE,
    AVOID_ENEMY_RAYS,
    MAX_RELAY_LAUNCHERS,
    HARVESTER_FINISH_STEPS,
    REPAIR_NETWORK,
    STUCK_ROUNDS_BEFORE_STANDDOWN,
    WRITE_OFF_STUCK_BUILDERS,
    FERRY_ON_INFERENCE,
    PAD_FIRST_ORDER,
    RING_MAX_SITES,
    RING_EDGE_MARGIN,
    SEAL_TITANIUM_RESERVE,
    SENTINEL_RANGE_SQ,
    SENTINEL_WRAP_RESERVE,
    SIEGE_BARRIER_ENABLED,
    SIEGE_BARRIER_RESERVE,
    RING_RADIUS,
    SLOT_BUILDER_HEARTBEAT,
    SLOT_BUILDER_TICKET,
    SLOT_CONSTRUCTION_LOCK,
    SLOT_CORE_DAMAGED,
    SLOT_ENEMY_CORE,
    SLOT_OWN_CORE,
    SLOT_SYMMETRY_REJECT_START,
    WALKABLE_BUILDINGS,
)
from utils import pack_enemy, pack_pos, unpack_core, unpack_enemy, unpack_pos

if TYPE_CHECKING:
    from main import Player


HARASS_PRIORITY = {EntityType.SPLITTER: 0, EntityType.CONVEYOR: 1}
# What to shoot first when several enemies are in reach.
COMBAT_PRIORITY = {
    EntityType.GUNNER: 0,
    EntityType.SENTINEL: 1,
    EntityType.BUILDER_BOT: 2,
    EntityType.LAUNCHER: 3,
}
GUNNER_RANGE_SQ = 13
# Clockwise from north-west; one ring site per compass direction.
RING_DELTAS = ((-1, -1), (0, -1), (1, -1), (1, 0),
               (1, 1), (0, 1), (-1, 1), (-1, 0))
PATH_FAILURES_BEFORE_LAUNCHER = 1
LAUNCH_REQUEST_ROUNDS = 4
BLOCKER_GUNNER_RETRY_ROUNDS = 4
RELAY_STOP_DISTANCE = 7
MOVABLE_BUILD_BLOCKER_GRACE = 3
STALL_REPORT_ROUNDS = 5
DEFERRED_ORE_ROUNDS = 8
MIN_AMMO_FOR_GUNNER = 20


def run(p: "Player", ct: Controller) -> None:
    try:
        _run(p, ct)
    except GameError as error:
        print(
            f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
            f"action=builder run reason=GameError: {error}",
            file=sys.stderr,
            flush=True,
        )
        # An escaping GameError permanently destroys this unit.
        return


def _run(p, ct):
    # Store round + 1 so zero remains the unambiguous "no Builder seen" value.
    # All Builders publish the same value; the Core only needs proof that at
    # least one of them was alive during the preceding round.
    ct.write_store(SLOT_BUILDER_HEARTBEAT, ct.get_current_round() + 1)
    if not hasattr(p, "builder_index"):
        p.builder_index = ct.read_store(SLOT_BUILDER_TICKET)
        ct.write_store(SLOT_BUILDER_TICKET, p.builder_index + 1)
        p.w, p.h = ct.get_map_width(), ct.get_map_height()
        p.seen, p.terrain = set(), {}
        p.walls, p.ores, p.solids, p.conveyors = set(), set(), set(), {}
        p.bot_occupied, p.enemy_conveyors = set(), {}
        p.enemy_launchers, p.enemy_launcher_danger = set(), set()
        p.enemy_economy = {}
        p.core, p.foot = None, set()
        p.task, p.route, p.route_i, p.phase = None, [], 0, "scout"
        p.explored = set()
        p.rejected_symmetries = 0
        p.current_route_tiles = set()
        p.network_tiles = set()
        p.network_load = 0
        p.network_plan = {}
        p.economy_lines_completed = 0
        p.ring_slot = p.builder_index - LAUNCHER_BUILDER_INDEX
        p.launcher_builders_wanted = 0
        p.lock_required = False
        p.home_gunners_built = 0
        p.guard_gunners_built = 0
        p.field_gunners_built = 0
        p.attack_gunners_built = 0
        p.path_failures = 0
        p.awaiting_launch = 0
        p.launch_origin = None
        p.launch_blocked = False
        p.launch_blocking_launchers = set()
        p.launcher_breakers = set()
        p.relay_launchers_built = 0
        p.next_blocker_gunner_round = 0
        p.build_wait_key, p.build_wait_rounds = None, 0
        p.pending_build = None
        p.rejected_build_sites = set()
        p.deferred_ores = {}
        p.last_progress_round = ct.get_current_round()
        p.last_progress = "spawned"
        p.stall_reported = False
        # The Core decided the doctrine on round 0 and published it with its
        # position. Reading it here rather than re-classifying keeps every
        # Builder on the same plan: a Builder's own vision is not the Core's,
        # so an independent verdict would not be a consistent one.
        own_core, p.doctrine = unpack_core(ct.read_store(SLOT_OWN_CORE))
        p.economy_builders = doctrine.economy_builders(p.doctrine)
        p.max_field_gunners = doctrine.max_field_gunners(p.doctrine)
        # Pad first, attacker second, miner last -- see PAD_FIRST_ORDER.
        p.launcher_builders_wanted = doctrine.launcher_builders(p.doctrine)
        attackers = doctrine.attack_builders(p.doctrine)
        if PAD_FIRST_ORDER:
            p.ring_slot = p.builder_index
            p.is_launcher_builder = p.builder_index < p.launcher_builders_wanted
            p.is_attacker = (
                p.launcher_builders_wanted
                <= p.builder_index
                < p.launcher_builders_wanted + attackers
            )
        else:
            p.is_launcher_builder = (
                0 <= p.ring_slot < p.launcher_builders_wanted
            )
            p.is_attacker = (p.builder_index >= p.economy_builders
                             and not p.is_launcher_builder)
        p.siege_sentinel = None
        p.sentinel_wrap = []
        # No map oracle. Terrain, ore and the enemy Core come only from what
        # this Builder has seen and from the symmetry inference below, so the
        # bot plays a generated map, the held-out set and the final exactly the
        # way it plays the published pool.
    _sense(p, ct)
    _report_stall(p, ct)
    _update_enemy_core_inference(p, ct)
    if p.core is None:
        return
    # A Builder that has proved it cannot path is a permanent +20% on every
    # price the team pays. Retire it before it gets a turn to do anything else.
    if _write_off(p, ct):
        return
    alarm = ct.read_store(SLOT_CORE_DAMAGED)
    if p.builder_index == 0 and alarm:
        _defend_core(p, ct)
        return
    # A critical Core outranks the ring, but only when the second mender can
    # arrive in time to matter: healing restores 4 HP for a flat 1 Ti at any
    # cost scale, so two menders out-heal a Gunner and fully cancel a
    # Sentinel. Under RUSH the race is decided by tempo and pulling the ring
    # Builder home costs more games than the healing saves -- measured, so
    # the recall is FORTIFY-only and short-leash.
    if (p.is_launcher_builder and alarm >= 2
            and p.doctrine == doctrine.FORTIFY
            and _chebyshev(tuple(ct.get_position()), p.core) <= 10):
        _heal_core(p, ct)
        return
    # Before any role work: an enemy in front of us outranks whatever errand
    # this Builder was on, wherever on the map that happens to be. Never the
    # economy Builder -- its opening titanium is the harvester budget, and a
    # field Gunner at round 7 is an economy that never starts.
    if p.builder_index != 0 and _engage_with_turret(p, ct):
        return
    if p.is_launcher_builder:
        # Before the ring, before the seal, before anything: an enemy that has
        # walked up to our own Core. This is the one Builder already standing
        # there, and answering on sighting rather than on damage is the single
        # largest measured change in this bot -- see `_guard_home`.
        if _guard_home(p, ct):
            return
        if not _run_launcher_ring(p, ct):
            return
        # The outer threat-zone seal is worth its titanium only where games
        # run long enough to finish it. When it is unaffordable it yields,
        # and the ring Builder mines instead of freezing in place: the
        # round-1000 tiebreak is delivered titanium, and a second miner is
        # worth more than a Builder holding a pose.
        if p.doctrine == doctrine.FORTIFY and not _run_core_seal(p, ct):
            return
    if p.is_attacker:
        p.phase = "rush"
    if p.phase == "rush":
        _rush(p, ct)
        return
    # A hole in the line outranks laying more of it: every Harvester upstream
    # of a gap is mining into a dead end, so one 3 Ti tile restores the whole
    # line's income where the next Harvester only adds to a broken one.
    if _repair_network(p, ct):
        return
    if p.network_load >= _network_cap(ct):
        p.phase = "harass"
    if p.phase == "harass":
        if (p.network_load < _network_cap(ct)
                and _has_unclaimed_ore(p, ct)):
            # The late-game tiebreak is delivered titanium: when the cap
            # lifts, mining beats harassing.
            p.phase = "scout"
        else:
            _harass(p, ct)
            return
    if p.phase == "scout":
        _pick(p, ct)
    if p.phase == "goto":
        _goto(p, ct)
    elif p.phase == "wait_lock":
        _wait_for_construction_lock(p, ct)
    elif p.phase == "prelay":
        if p.lock_required:
            _refresh_construction_lock(p, ct)
        _prelay(p, ct)
    elif p.phase == "lay":
        _lay(p, ct)
    else:
        _explore(p, ct)


def _sense(p, ct):
    for tile in ct.get_nearby_tiles():
        key = tuple(tile)
        p.seen.add(key)
        env = ct.get_tile_env(tile)
        p.terrain[key] = env
        if env == Environment.WALL:
            p.walls.add(key)
            p.enemy_launchers.discard(key)
            continue
        if env == Environment.ORE_TITANIUM:
            p.ores.add(key)
        bot_id = ct.get_tile_builder_bot_id(tile)
        if bot_id is not None and bot_id != ct.get_id():
            p.bot_occupied.add(key)
        else:
            p.bot_occupied.discard(key)
        bid = ct.get_tile_building_id(tile)
        if bid is None:
            p.solids.discard(key)
            p.conveyors.pop(key, None)
            p.enemy_conveyors.pop(key, None)
            p.enemy_economy.pop(key, None)
            p.enemy_launchers.discard(key)
            continue
        kind = ct.get_entity_type(bid)
        enemy = ct.get_team(bid) != ct.get_team()
        if enemy and kind == EntityType.LAUNCHER:
            p.enemy_launchers.add(key)
        else:
            p.enemy_launchers.discard(key)
        if kind == EntityType.CORE and enemy:
            ct.write_store(SLOT_ENEMY_CORE, pack_enemy(ct.get_position(bid), True))
        if enemy and kind in HARASS_PRIORITY:
            p.enemy_economy[key] = kind
        else:
            p.enemy_economy.pop(key, None)
        if kind == EntityType.CORE:
            if ct.get_team(bid) == ct.get_team():
                p.core = tuple(ct.get_position(bid))
            p.solids.add(key)
        elif kind in WALKABLE_BUILDINGS:
            p.solids.discard(key)
            if ct.get_team(bid) == ct.get_team():
                p.conveyors[key] = ct.get_direction(bid)
                p.enemy_conveyors.pop(key, None)
            else:
                p.enemy_conveyors[key] = ct.get_direction(bid)
        else:
            p.solids.add(key)
    if p.core and not p.foot:
        x, y = p.core
        p.foot = {(x + dx, y + dy) for dx in (0, 1) for dy in (0, 1)}
    p.enemy_launcher_danger = {
        (launcher[0] + dx, launcher[1] + dy)
        for launcher in p.enemy_launchers
        for dx, dy in (direction.delta() for direction in D8)
        if _inside(p, (launcher[0] + dx, launcher[1] + dy))
    }
    p.launcher_breakers.intersection_update(p.enemy_launchers)
    if (p.launch_blocked and p.launch_blocking_launchers
            and not p.launch_blocking_launchers & p.enemy_launchers):
        p.launch_blocked = False
        p.launch_blocking_launchers.clear()


def _network_cap(ct) -> int:
    """One trunk saturates at four Harvesters; a long game earns a second."""
    return (NETWORK_CAP_EARLY if ct.get_current_round() < ECON_EXPAND_ROUND
            else NETWORK_CAP_LATE)


def _has_unclaimed_ore(p, ct) -> bool:
    claimed = {x for x in (unpack_pos(ct.read_store(s)) for s in CLAIM_SLOTS) if x}
    return bool(p.ores - claimed - p.solids - set(p.conveyors))


def _pick(p, ct):
    # A conveyor network carries one stack/round: exactly four Harvesters at
    # their 10-Ti-per-four-round cadence. Do not create silently idle deposits.
    if p.network_load >= _network_cap(ct):
        return
    claimed = {x for x in (unpack_pos(ct.read_store(s)) for s in CLAIM_SLOTS) if x}
    claimed |= p.ores & p.solids
    claimed |= {ore for ore, expires in p.deferred_ores.items()
                if expires >= ct.get_current_round()}
    p.deferred_ores = {ore: expires for ore, expires in p.deferred_ores.items()
                       if expires >= ct.get_current_round()}
    me, best = tuple(ct.get_position()), None
    candidates = sorted(
        p.ores - claimed,
        key=lambda ore: max(abs(ore[0] - me[0]), abs(ore[1] - me[1])),
    )
    for ore in candidates:
        route = _route(p, ore)
        travel = _distance(p, me, _adjacent(p, ore))
        if route is None or travel is None:
            continue
        # Nearest-first is robust under fog; route length breaks ties. The
        # offline planner supplies the upper bound for later score tuning.
        best = (travel, len(route), ore, route)
        break
    if best is None:
        return
    _, _, ore, route = best
    for slot in CLAIM_SLOTS:
        if ct.read_store(slot) == 0:
            ct.write_store(slot, pack_pos(ore))
            p.task, p.route = ore, route
            p.current_route_tiles.clear()
            if route:
                p.route_i = len(route) - 1
                # Only long routes justify serializing construction. Short
                # routes gain more from parallelism and rarely collide deeply.
                p.lock_required = len(route) >= 24
                p.phase = "wait_lock" if p.lock_required else "prelay"
            else:
                p.lock_required = False
                p.route_i, p.phase = 0, "goto"
            return


def _route(p, ore):
    """Shortest cardinal line to Core or this Builder's unsaturated network."""
    joinable = p.network_tiles if p.network_load < 4 else set()
    blocked = (p.walls | p.foot | (p.ores - {ore}) | p.solids
               | p.rejected_build_sites
               | _launcher_hazards(p)
               | (set(p.conveyors) - joinable))
    prev, queue, goal = {ore: None}, deque([ore]), None
    while queue and goal is None:
        cur = queue.popleft()
        for dx, dy in D4_DELTAS:
            nxt = cur[0] + dx, cur[1] + dy
            if nxt in prev or not _inside(p, nxt):
                continue
            # An orthogonally adjacent Harvester feeds the Core directly.
            if nxt in p.foot:
                prev[nxt], goal = cur, nxt
                break
            if nxt in joinable:
                # A Conveyor accepts from every cardinal side except its own
                # output side; reject a head-on attempted join.
                direction = p.conveyors.get(nxt)
                if direction is not None:
                    receiver_output = (nxt[0] + direction.delta()[0],
                                       nxt[1] + direction.delta()[1])
                    if receiver_output != cur:
                        prev[nxt], goal = cur, nxt
                        break
            # Unknown terrain is not permission to spend. Builders scout until
            # an entire cardinal route is observed, then construct it.
            if nxt not in p.seen:
                continue
            if nxt in blocked:
                continue
            prev[nxt] = cur
            queue.append(nxt)
    if goal is None:
        return None
    path, cur = [], goal
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    tiles, result = path[1:-1], []
    for i, tile in enumerate(tiles):
        nxt = tiles[i + 1] if i + 1 < len(tiles) else path[-1]
        result.append((tile, FACING[(nxt[0] - tile[0], nxt[1] - tile[1])]))
    return result


def _goto(p, ct):
    me, target = tuple(ct.get_position()), Position(*p.task)
    if _cardinal_distance(me, p.task) == 1:
        if ct.can_build_harvester(target):
            ct.build_harvester(target)
            _mark_progress(p, ct, "built harvester", p.task)
            p.solids.add(p.task)
            p.economy_lines_completed += 1
            _done(p, ct)
        else:
            building_id = ct.get_tile_building_id(target)
            compatible = (
                building_id is not None
                and ct.get_team(building_id) == ct.get_team()
                and ct.get_entity_type(building_id) == EntityType.HARVESTER
            )
            if compatible:
                _mark_progress(p, ct, "found existing harvester", p.task)
                _done(p, ct)
            elif building_id is not None or _build_failure(
                    p, ct, p.task, "harvester", ct.get_harvester_cost(),
                    allow_ore=True):
                p.deferred_ores[p.task] = (
                    ct.get_current_round() + DEFERRED_ORE_ROUNDS
                )
                _abandon_task(p, ct, "blocked harvester site")
        return
    # Builder construction is cardinal-only. A diagonal tile is visible but
    # not actionable, so explicitly move to a cardinal neighbour of the ore.
    _move_cardinal_adjacent(p, ct, p.task)


def _wait_for_construction_lock(p, ct):
    """Acquire a delayed-store lease before committing conveyor tiles."""
    owner, expires = _read_construction_lock(ct)
    me = p.builder_index + 1
    if owner == me:
        p.phase = "prelay"
        _refresh_construction_lock(p, ct)
        return
    if owner == 0 or expires < ct.get_current_round():
        ct.write_store(SLOT_CONSTRUCTION_LOCK,
                       me | ((ct.get_current_round() + 20) << 2))
    # Position at the Core/network end while the previous line finishes.
    if p.route:
        _step(p, ct, Position(*p.route[-1][0]), True)


def _broken_network_tiles(p, ct):
    """Conveyor tiles we laid that are now visibly empty."""
    broken = []
    for tile in p.network_plan:
        position = Position(*tile)
        if not ct.is_in_vision(position):
            continue
        if ct.get_tile_building_id(position) is None:
            broken.append(tile)
    return broken


def _repair_network(p, ct):
    """Rebuild the nearest hole in our own conveyor line.

    Ported back from vigil, which still has it where ragnarok does not. A
    broken line pays nothing at all -- every Harvester upstream of the gap is
    mining into a dead end -- so patching one tile is worth more than the next
    Harvester almost always. Almost: a Harvester already within a couple of
    steps is finished first, so a cluster of ores does not send the Builder
    back down the line between each one.

    This is the mechanic the ragnarok line dropped when it was assembled, and
    dropping it is a plausible reason the vigil line still beats it: belts are
    what a long game is decided on, and ragnarok cannot mend one.
    """
    if not REPAIR_NETWORK:
        return False
    broken = _broken_network_tiles(p, ct)
    if not broken:
        return False
    me = tuple(ct.get_position())
    if (p.task is not None
            and _cardinal_distance(me, p.task) <= HARVESTER_FINISH_STEPS):
        return False
    broken.sort(key=lambda tile: (_cardinal_distance(me, tile), tile))
    tile = broken[0]
    facing = p.network_plan[tile]
    target = Position(*tile)
    if _cardinal_distance(me, tile) != 1:
        _move_cardinal_adjacent(p, ct, tile)
        return True
    if ct.can_build_conveyor(target, facing):
        ct.build_conveyor(target, facing)
        _mark_progress(p, ct, "repaired conveyor", tile)
        p.conveyors[tile] = facing
        return True
    if _build_failure(p, ct, tile, "conveyor repair", ct.get_conveyor_cost()):
        # Something else stands there now; the line has to be re-planned
        # rather than patched.
        del p.network_plan[tile]
    return True


def _write_off(p, ct):
    """Destroy a Builder that has proved it cannot act, if one can be replaced.

    Also ported back from vigil. A Builder walled in behind buildings is not
    merely idle: it holds +20% on every price the team pays for the rest of the
    game, and while it keeps answering the heartbeat the Core will never
    replace it. Removing it refunds the scale and frees the Core to try again
    from a spawn tile that may not be trapped.

    The guard is affordability, not a headcount: standing down is safe even for
    the last Builder, because the Core respawns one the moment the heartbeat
    lapses, and unsafe only when the Core cannot afford the replacement.
    """
    if not WRITE_OFF_STUCK_BUILDERS:
        return False
    if p.path_failures < STUCK_ROUNDS_BEFORE_STANDDOWN:
        return False
    if ct.get_global_resources() < ct.get_builder_bot_cost():
        return False
    # Nothing after this call runs; the engine tears the unit down inside it.
    ct.self_destruct()
    return True


def _read_construction_lock(ct):
    value = ct.read_store(SLOT_CONSTRUCTION_LOCK)
    return value & 0x3, value >> 2


def _refresh_construction_lock(p, ct):
    ct.write_store(SLOT_CONSTRUCTION_LOCK,
                   (p.builder_index + 1) | ((ct.get_current_round() + 20) << 2))


def _prelay(p, ct):
    """Build Core-to-ore so a Harvester is never committed without a line."""
    if p.route_i < 0:
        p.phase = "goto"
        return
    tile, facing = p.route[p.route_i]
    me, target = ct.get_position(), Position(*tile)
    if _cardinal_distance(tuple(me), tuple(target)) != 1:
        if tile in p.walls or tile in p.solids or (
            tile in p.conveyors and tile not in p.current_route_tiles
        ):
            _reject_route_tile(p, ct, tile, outward=True)
            return
        _move_cardinal_adjacent(p, ct, tuple(target))
        return
    if ct.can_build_conveyor(target, facing):
        ct.build_conveyor(target, facing)
        _mark_progress(p, ct, "built conveyor", tile)
        p.conveyors[tile] = facing
        # p.conveyors is rebuilt from vision every round, so it forgets a tile
        # the moment it leaves sight and cannot tell "destroyed" from "not
        # looking". p.network_plan is the permanent record of what we laid,
        # which is the only thing that makes a hole detectable at all.
        p.network_plan[tile] = facing
        p.current_route_tiles.add(tile)
    else:
        building_id = ct.get_tile_building_id(target)
        compatible = (
            building_id is not None
            and tile in p.current_route_tiles
            and ct.get_team(building_id) == ct.get_team()
            and ct.get_entity_type(building_id) == EntityType.CONVEYOR
            and ct.get_direction(building_id) == facing
        )
        if not compatible:
            if building_id is not None or _build_failure(
                    p, ct, tile, "conveyor", ct.get_conveyor_cost()):
                _reject_route_tile(p, ct, tile, outward=True)
            return
        _mark_progress(p, ct, "found existing conveyor", tile)
    p.route_i -= 1
    if p.route_i >= 0:
        _step(p, ct, Position(*p.route[p.route_i][0]), True)
    else:
        p.phase = "goto"


def _lay(p, ct):
    if p.route_i >= len(p.route):
        _done(p, ct)
        return
    tile, facing = p.route[p.route_i]
    me, target = ct.get_position(), Position(*tile)
    if _cardinal_distance(tuple(me), tuple(target)) != 1:
        if tile in p.walls or tile in p.solids or (
            tile in p.conveyors and tile not in p.current_route_tiles
        ):
            _reject_route_tile(p, ct, tile)
            return
        _move_cardinal_adjacent(p, ct, tuple(target))
        return
    if ct.can_build_conveyor(target, facing):
        ct.build_conveyor(target, facing)
        _mark_progress(p, ct, "built conveyor", tile)
        p.conveyors[tile] = facing
        # p.conveyors is rebuilt from vision every round, so it forgets a tile
        # the moment it leaves sight and cannot tell "destroyed" from "not
        # looking". p.network_plan is the permanent record of what we laid,
        # which is the only thing that makes a hole detectable at all.
        p.network_plan[tile] = facing
        p.current_route_tiles.add(tile)
    else:
        building_id = ct.get_tile_building_id(target)
        compatible = (
            building_id is not None
            and
            tile in p.current_route_tiles
            and
            ct.get_team(building_id) == ct.get_team()
            and ct.get_entity_type(building_id) == EntityType.CONVEYOR
            and ct.get_direction(building_id) == facing
        )
        if not compatible:
            if building_id is not None or _build_failure(
                    p, ct, tile, "conveyor", ct.get_conveyor_cost()):
                # Never silently splice into a conflicting facing: recompute a
                # disjoint route with observed infrastructure blocked.
                _reject_route_tile(p, ct, tile)
            return
        _mark_progress(p, ct, "found existing conveyor", tile)
    p.route_i += 1
    if p.route_i < len(p.route):
        _step(p, ct, Position(*p.route[p.route_i][0]), True)
    else:
        _done(p, ct)


def _replace_route(p, outward=False):
    """Replan after fog or another Builder invalidates the current line."""
    replacement = _route(p, p.task)
    if replacement is not None and replacement != p.route[p.route_i:]:
        p.route = replacement
        p.route_i = len(replacement) - 1 if outward else 0
        return True
    return False


def _reject_route_tile(p, ct, tile, outward=False):
    p.rejected_build_sites.add(tile)
    if _replace_route(p, outward):
        _mark_progress(p, ct, "replanned blocked route", tile)
    else:
        _abandon_task(p, ct, "no alternate conveyor route")


def _done(p, ct):
    if p.task and p.current_route_tiles:
        p.network_tiles.update(p.current_route_tiles)
        p.network_load += 1
        p.current_route_tiles.clear()
    owner, _ = _read_construction_lock(ct)
    if owner == p.builder_index + 1:
        ct.write_store(SLOT_CONSTRUCTION_LOCK, 0)
    if p.task:
        value = pack_pos(p.task)
        for slot in CLAIM_SLOTS:
            if ct.read_store(slot) == value:
                ct.write_store(slot, 0)
                break
    p.task, p.route, p.route_i, p.phase = None, [], 0, "scout"
    p.lock_required = False
    p.path_failures = 0


def _abandon_task(p, ct, reason):
    """Release an impossible construction task without counting it as income."""
    owner, _ = _read_construction_lock(ct)
    if owner == p.builder_index + 1:
        ct.write_store(SLOT_CONSTRUCTION_LOCK, 0)
    if p.task:
        value = pack_pos(p.task)
        for slot in CLAIM_SLOTS:
            if ct.read_store(slot) == value:
                ct.write_store(slot, 0)
                break
    old_task = p.task
    p.current_route_tiles.clear()
    p.task, p.route, p.route_i, p.phase = None, [], 0, "scout"
    p.lock_required = False
    p.path_failures = 0
    _mark_progress(p, ct, reason, old_task)


def _build_failure(p, ct, target, kind, cost, allow_ore=False):
    """Return true when a selected build site should be abandoned.

    Mobile blockers get a short grace period. Resource/cooldown failures keep
    waiting, while walls, buildings, ore misuse, and unexplained legal failures
    immediately force the caller to choose another site.
    """
    target = tuple(target)
    if target in p.bot_occupied:
        reason_code = "bot"
        reason = "builder bot occupying target"
    elif target in p.walls:
        reason_code = "wall"
        reason = "wall on target"
    elif target in p.ores and not allow_ore:
        reason_code = "ore"
        reason = "reserved ore tile"
    elif target in p.solids or target in p.conveyors:
        reason_code = "building"
        reason = "building on target"
    elif ct.get_global_resources() < cost:
        reason_code = "resources"
        reason = f"needs {cost} titanium"
    elif ct.get_action_cooldown() > 0 or ct.get_move_cooldown() > 0:
        reason_code = "cooldown"
        reason = "builder cooldown"
    else:
        reason_code = "invalid"
        reason = "site rejected by can_build"

    key = kind, target, reason_code
    if p.build_wait_key == key:
        p.build_wait_rounds += 1
    else:
        p.build_wait_key, p.build_wait_rounds = key, 1
    p.pending_build = kind, target, reason, p.build_wait_rounds
    details = f"{reason}; available={ct.get_global_resources()} cost={cost}"
    _plan_failed(p, ct, f"build {kind}", target, details,
                 p.build_wait_rounds)

    if _vacate_ore(p, ct, target):
        return False
    if reason_code == "bot":
        return p.build_wait_rounds > MOVABLE_BUILD_BLOCKER_GRACE
    if reason_code in ("resources", "cooldown"):
        return False
    return True


def _plan_failed(p, ct, action, target, reason, attempt=None):
    """Write a replay-visible explanation whenever an intended action fails."""
    suffix = f" attempt={attempt}" if attempt is not None else ""
    print(
        f"PLAN_FAILED id={ct.get_id()} round={ct.get_current_round()} "
        f"phase={p.phase} action={action} target={tuple(target)} "
        f"reason={reason}{suffix}"
    )


def _vacate_ore(p, ct, build_target):
    """Do not let a waiting Builder reserve an ore tile with its body."""
    here = tuple(ct.get_position())
    if here not in p.ores:
        return False
    choices = []
    for dx, dy in D4_DELTAS:
        spot = here[0] + dx, here[1] + dy
        if (not _inside(p, spot) or spot == build_target or spot in p.ores
                or spot in p.walls or spot in p.solids
                or spot in p.bot_occupied):
            continue
        direction = FACING[(dx, dy)]
        if ct.can_move(direction):
            choices.append((
                _cardinal_distance(spot, build_target),
                spot,
                direction,
            ))
    if not choices:
        return False
    _, spot, direction = min(choices)
    ct.move(direction)
    _mark_progress(p, ct, "vacated ore while waiting", spot)
    return True


def _mark_progress(p, ct, action, target=None):
    p.last_progress_round = ct.get_current_round()
    p.last_progress = f"{action} {target}" if target is not None else action
    p.stall_reported = False
    p.pending_build = None
    p.build_wait_key, p.build_wait_rounds = None, 0


def _report_stall(p, ct):
    """Emit one replay-visible diagnostic after five rounds without progress."""
    idle_rounds = ct.get_current_round() - p.last_progress_round
    if idle_rounds <= STALL_REPORT_ROUNDS or p.stall_reported:
        return None
    if (p.pending_build is not None
            and p.pending_build[2].startswith("needs ")):
        return None
    pending = p.pending_build or "none"
    message = (
        f"BUILDER_STALL id={ct.get_id()} rounds={idle_rounds} "
        f"pos={tuple(ct.get_position())} phase={p.phase} task={p.task} "
        f"last={p.last_progress} pending={pending}"
    )
    print(message)
    p.stall_reported = True
    return message


def _step(p, ct, target, exact, allow_launcher=True):
    source = ct.get_position()
    launch_rejected = _consume_launch_rejection(p, ct)
    if p.awaiting_launch:
        if tuple(source) != p.launch_origin:
            # The Launcher moved us. Resume the original task immediately.
            p.awaiting_launch = 0
            p.launch_origin = None
            p.path_failures = 0
        else:
            adjacent = _adjacent_visible_launcher(ct, target)
            if adjacent is not None:
                if _announce_launch(p, ct, target, adjacent[1]):
                    p.awaiting_launch -= 1
                    return True
                p.awaiting_launch = 0
                p.launch_origin = None
            # The requested Launcher disappeared before servicing us.
            p.awaiting_launch = 0
            p.launch_origin = None

    nxt = _bfs_step(p, tuple(source), tuple(target), exact)
    if nxt:
        # Cardinal only: a diagonal is not a legal Builder move in 2.3.3, and
        # this loop silently did nothing whenever the path asked for one.
        for direction in D8:
            if source.add(direction) == Position(*nxt) and ct.can_move(direction):
                ct.move(direction)
                _mark_progress(p, ct, "moved", nxt)
                p.path_failures = 0
                return True

    goals = {tuple(target)} if exact else _adjacent(p, tuple(target))
    if tuple(source) in goals:
        p.path_failures = 0
        return False

    p.path_failures += 1
    # An enemy Launcher across the path is a target, not an obstacle -- but
    # only the ones the route actually runs into.
    blocking = _blocking_launchers(p, tuple(source), tuple(target), exact)
    if blocking and _build_launcher_breaker_gunner(
            p, ct, blocking=blocking, route=target):
        return True
    if (allow_launcher and not launch_rejected and not p.launch_blocked
            and p.path_failures >= PATH_FAILURES_BEFORE_LAUNCHER
            and _build_escape_launcher(p, ct, target)):
        return True
    if _build_blocker_gunner(p, ct, target):
        return True
    if _move_while_stuck(p, ct, target):
        return True
    _plan_failed(
        p, ct, "move", target,
        "no route, safe launcher, aligned gunner, or legal local move",
    )
    return False


def _build_escape_launcher(p, ct, target):
    """Build a temporary ferry after repeated failures to find a walkable path."""
    launchers = _visible_friendly_launchers(ct)
    if launchers:
        adjacent = _adjacent_visible_launcher(ct, target, launchers)
        if adjacent is None:
            return False
        p.awaiting_launch = LAUNCH_REQUEST_ROUNDS
        p.launch_origin = tuple(ct.get_position())
        if _announce_launch(p, ct, target, adjacent[1]):
            return True
        p.awaiting_launch = 0
        p.launch_origin = None
        return False

    # Cap how many Launchers one Builder will buy purely to throw itself
    # forward. Each is 20 Ti and a permanent +10% on every price the team pays,
    # and the bill lands on the two things that actually kill a Core: measured
    # on aurora, this bot builds 6 Launchers, 1 Harvester and 4 Gunners in the
    # game where the atlas-free ragnarok_fair -- which cannot ferry at all and
    # therefore walks -- builds 3, 2 and 7. The chain buys tempo and pays for it
    # in firepower and economy at once, and ragnarok_fair takes 25/42 off
    # valkyrie on the cluster while ragnarok itself only manages 21/42.
    if p.relay_launchers_built >= MAX_RELAY_LAUNCHERS:
        _plan_failed(
            p, ct, "build escape launcher", target,
            f"relay cap reached ({MAX_RELAY_LAUNCHERS})",
        )
        return False
    if ct.get_global_resources() < ct.get_launcher_cost():
        _plan_failed(
            p, ct, "build escape launcher", target,
            f"needs {ct.get_launcher_cost()} titanium; "
            f"available={ct.get_global_resources()}",
        )
        return False

    here = tuple(ct.get_position())
    candidates = []
    for dx, dy in D4_DELTAS:
        spot = here[0] + dx, here[1] + dy
        position = Position(*spot)
        if (_inside(p, spot) and spot not in p.walls and spot not in p.solids
                and spot not in _launcher_hazards(p)
                and spot not in p.ores and ct.can_build_launcher(position)):
            candidates.append((position.distance_squared(target), spot, position))
    if not candidates:
        _plan_failed(
            p, ct, "build escape launcher", target,
            "no adjacent non-ore site with a safe legal landing",
        )
        return False

    _, spot, position = min(candidates)
    ct.build_launcher(position)
    p.relay_launchers_built += 1
    _mark_progress(p, ct, "built escape launcher", spot)
    p.solids.add(spot)
    p.path_failures = 0
    p.awaiting_launch = LAUNCH_REQUEST_ROUNDS
    p.launch_origin = here
    _announce_launch(p, ct, target, position)
    return True


def _build_blocker_gunner(p, ct, target):
    """Build an immediately aligned Gunner against a visible path blocker."""
    if (ct.get_global_ammo() < MIN_AMMO_FOR_GUNNER
            or ct.get_current_round() < p.next_blocker_gunner_round):
        return False

    here = ct.get_position()
    enemies = [entity_id for entity_id in ct.get_nearby_entities()
               if ct.get_team(entity_id) != ct.get_team()]
    if not enemies:
        return False

    source, destination = tuple(here), tuple(target)
    protected_lanes = _friendly_turret_lanes(ct)
    target_dx = destination[0] - source[0]
    target_dy = destination[1] - source[1]
    unit_priority = {
        EntityType.BUILDER_BOT: 0,
        EntityType.LAUNCHER: 1,
        EntityType.GUNNER: 2,
        EntityType.SENTINEL: 3,
    }
    candidates = []
    for dx, dy in D4_DELTAS:
        spot = source[0] + dx, source[1] + dy
        position = Position(*spot)
        if (not _inside(p, spot) or spot in p.foot or spot in p.walls
                or spot in p.ores or spot in p.solids):
            continue
        for enemy_id in enemies:
            enemy = ct.get_position(enemy_id)
            facing = _ray_direction(spot, tuple(enemy))
            if (facing is None
                    or position.distance_squared(enemy) > GUNNER_RANGE_SQ
                    or not ct.can_fire_from(
                        position, facing, EntityType.GUNNER, enemy,
                    )
                    or not _preserves_friendly_turret_lanes(
                        ct, position, protected_lanes,
                    )
                    or not ct.can_build_gunner(position, facing)):
                continue
            enemy_dx = enemy.x - source[0]
            enemy_dy = enemy.y - source[1]
            ahead = enemy_dx * target_dx + enemy_dy * target_dy > 0
            deviation = abs(enemy_dx * target_dy - enemy_dy * target_dx)
            candidates.append((
                not ahead,
                deviation,
                unit_priority.get(ct.get_entity_type(enemy_id), 4),
                here.distance_squared(enemy),
                position.distance_squared(target),
                position.x,
                position.y,
                position,
                facing,
            ))
    if not candidates:
        return False

    *_, position, facing = min(candidates)
    ct.build_gunner(position, facing)
    _mark_progress(p, ct, "built blocker gunner", tuple(position))
    p.solids.add(tuple(position))
    p.next_blocker_gunner_round = (
        ct.get_current_round() + BLOCKER_GUNNER_RETRY_ROUNDS
    )
    return True


def _visible_friendly_launchers(ct):
    """Return visible friendly Launcher ids and positions."""
    result = []
    for entity_id in ct.get_nearby_buildings():
        if (ct.get_team(entity_id) == ct.get_team()
                and ct.get_entity_type(entity_id) == EntityType.LAUNCHER):
            result.append((entity_id, ct.get_position(entity_id)))
    return result


def _adjacent_visible_launcher(ct, target, launchers=None):
    """Pick the adjacent Launcher furthest forward toward target."""
    here = ct.get_position()
    if launchers is None:
        launchers = _visible_friendly_launchers(ct)
    adjacent = [launcher for launcher in launchers
                if here.distance_squared(launcher[1]) <= 2]
    if not adjacent:
        return None
    return min(adjacent, key=lambda launcher: (
        launcher[1].distance_squared(target), launcher[1].x, launcher[1].y,
    ))


def _announce_launch(p, ct, target, launcher_position):
    """Publish this passenger and the launcher's requested compass direction."""
    dx = _sign(target.x - launcher_position.x)
    dy = _sign(target.y - launcher_position.y)
    direction_index = next((
        index for index, direction in enumerate(D8, start=1)
        if direction.delta() == (dx, dy)
    ), None)
    if direction_index is None:
        _plan_failed(
            p, ct, "announce launch", target,
            f"launcher at {tuple(launcher_position)} is already the target",
        )
        return False
    slot = LAUNCH_REQUEST_SLOTS[p.builder_index % len(LAUNCH_REQUEST_SLOTS)]
    request = (ct.get_id() << LAUNCH_DIRECTION_BITS) | direction_index
    ct.write_store(slot, request)
    return True


def _consume_launch_rejection(p, ct):
    """Consume a rejection and remember the Launcher blocking safe landings."""
    slot = LAUNCH_REQUEST_SLOTS[p.builder_index % len(LAUNCH_REQUEST_SLOTS)]
    value = ct.read_store(slot)
    if not value & LAUNCH_REJECTION_FLAG:
        return False
    payload = value & (LAUNCH_REJECTION_FLAG - 1)
    passenger = payload >> LAUNCH_REJECTION_POSITION_BITS
    if passenger != ct.get_id():
        return False
    blocker = unpack_pos(payload & LAUNCH_REJECTION_POSITION_MASK)
    if blocker is not None:
        p.enemy_launchers.add(blocker)
        p.solids.add(blocker)
        p.enemy_launcher_danger.update(
            (blocker[0] + dx, blocker[1] + dy)
            for dx, dy in (direction.delta() for direction in D8)
            if _inside(p, (blocker[0] + dx, blocker[1] + dy))
        )
    ct.write_store(slot, 0)
    p.awaiting_launch = 0
    p.launch_origin = None
    p.launch_blocked = True
    p.launch_blocking_launchers = set(p.enemy_launchers)
    return True


def _sign(value):
    return (value > 0) - (value < 0)


def _move_while_stuck(p, ct, target):
    """Explore locally while waiting until a useful Launcher is affordable."""
    source = ct.get_position()
    candidates = []
    for direction in FACING.values():
        position = source.add(direction)
        if (tuple(position) not in _launcher_hazards(p)
                and ct.can_move(direction)):
            candidates.append((
                tuple(position) in p.seen,
                position.distance_squared(target),
                position.x,
                position.y,
                direction,
            ))
    if not candidates:
        return False
    *_, direction = min(candidates)
    ct.move(direction)
    _mark_progress(p, ct, "moved while blocked", tuple(ct.get_position()))
    return True


def _bfs_step(p, source, target, exact, avoid_launchers=True):
    """First move of the cardinal route, or None when there is no route."""
    path = _bfs_path(p, source, target, exact, avoid_launchers=avoid_launchers)
    if path is None or len(path) < 2:
        return None
    return path[1]


def _bfs_path(p, source, target, exact, avoid_launchers=True, extra_blocked=()):
    """Full cardinal route from source to a goal tile, or None."""
    goals = {target} if exact else _adjacent(p, target)
    if source in goals:
        return [source]
    blocked = p.walls | p.foot | p.solids | (p.bot_occupied - {source})
    if avoid_launchers:
        blocked = blocked | (_launcher_hazards(p) - {source})
    if extra_blocked:
        blocked = blocked | (set(extra_blocked) - {source})
    prev, queue = {source: None}, deque([source])
    found = None
    while queue:
        cur = queue.popleft()
        if cur in goals:
            found = cur
            break
        for dx, dy in D4_DELTAS:
            nxt = cur[0] + dx, cur[1] + dy
            if nxt in prev or not _inside(p, nxt) or nxt in blocked:
                continue
            prev[nxt] = cur
            queue.append(nxt)
    if found is None:
        return None
    path = []
    while found is not None:
        path.append(found)
        found = prev[found]
    path.reverse()
    return path


def _blocking_launchers(p, source, target, exact):
    """Only the Launchers whose pickup zone the open route actually crosses.

    The old breaker took whichever Launcher was cheapest to line up on, which
    is frequently one standing harmlessly off to the side. Shooting that one
    costs a Gunner and a turn and opens nothing, and the route stays shut.

    Take the route that would exist if their Launchers were gone, see which
    hazard tiles it runs through, and blame only the Launchers casting them.
    A Launcher covers the eight tiles around itself, so it owns a crossed tile
    exactly when that tile is one Chebyshev step away.
    """
    hazards = _launcher_hazards(p)
    if not hazards:
        return set()
    path = _bfs_path(p, source, target, exact, avoid_launchers=False)
    if path is None:
        return set()
    crossed = set(path) & hazards
    return {launcher for launcher in p.enemy_launchers
            if any(_chebyshev(launcher, tile) == 1 for tile in crossed)}


def _out_of_time(ct, budget=CPU_SOFT_BUDGET_US):
    """True once this turn has spent enough of its 10 ms to stop searching.

    A unit that overruns is interrupted mid-run(): it does not act at all that
    round, and nothing it was part-way through is kept. So an optional search
    that might not fit is worth strictly less than the ordinary action it would
    displace. Never let this raise -- a bad clock read must not cost the turn.
    """
    try:
        return ct.get_cpu_time_elapsed() > budget
    except Exception:  # noqa: BLE001
        return False


_NO_BASELINE = object()


def _route_baseline(p, source, target, exact):
    """The unobstructed route once, for a whole turn's worth of candidates.

    Every candidate site asks the same first question -- "is there a route at
    all?" -- so asking it per candidate searched the map hundreds of times a
    turn. Returns the route as a set, or None when there is none.
    """
    path = _bfs_path(p, source, tuple(target), exact)
    return None if path is None else set(path)


def _keeps_route_open(p, spot, source, target, exact, baseline=_NO_BASELINE):
    """True when spot can be built on without cutting our own way forward.

    Turrets are solid. Dropping one on the single corridor to the enemy Core
    walls the attacker out of the game it was built to fight -- and nothing
    checked for it: _preserves_friendly_turret_lanes guards firing lines, not
    footpaths. Building onto the goal itself is exempt, since arriving is not
    the objective there.

    Pass `baseline` (from _route_baseline) when testing many sites against the
    same route. A site the existing route does not use cannot close it -- that
    route still stands with the site blocked -- so only sites *on* the route
    need the second search. This is exact, not a heuristic: it decides the same
    way the two-search version did, and turned a 13.5 ms Builder turn on
    longship into one that fits the ladder's 10 ms limit with room to spare.
    """
    if spot == tuple(target) or spot == source:
        return True
    if baseline is _NO_BASELINE:
        baseline = _route_baseline(p, source, target, exact)
    if baseline is None:
        # Already no route; a turret cannot make that worse, and refusing here
        # would disable the breaker in exactly the case it exists for.
        return True
    if spot not in baseline:
        return True
    return _bfs_path(p, source, tuple(target), exact,
                     extra_blocked=(spot,)) is not None


def _distance(p, source, goals):
    if source in goals:
        return 0
    blocked = (p.walls | p.foot | p.solids | (p.bot_occupied - {source})
               | (_launcher_hazards(p) - {source}))
    dist, queue = {source: 0}, deque([source])
    while queue:
        cur = queue.popleft()
        for dx, dy in D4_DELTAS:
            nxt = cur[0] + dx, cur[1] + dy
            if nxt in dist or not _inside(p, nxt) or nxt in blocked:
                continue
            dist[nxt] = dist[cur] + 1
            if nxt in goals:
                return dist[nxt]
            queue.append(nxt)
    return None


def _distance_map(p, source):
    """Compute every reachable distance once for candidate-heavy planners."""
    blocked = (p.walls | p.foot | p.solids | (p.bot_occupied - {source})
               | (_launcher_hazards(p) - {source}))
    dist, queue = {source: 0}, deque([source])
    while queue:
        cur = queue.popleft()
        for dx, dy in D4_DELTAS:
            nxt = cur[0] + dx, cur[1] + dy
            if nxt in dist or not _inside(p, nxt) or nxt in blocked:
                continue
            dist[nxt] = dist[cur] + 1
            queue.append(nxt)
    return dist


def _explore(p, ct):
    me, stride = tuple(ct.get_position()), 4

    # First resolve the enemy-Core hypotheses. This is map-agnostic: targets
    # come only from dimensions, our observed Core, and rejected symmetries.
    info_target = _enemy_scout_target(p, ct)
    if info_target is not None:
        _step(p, ct, Position(*info_target), False)
        return

    choices = [(x, y) for y in range(1, p.h, stride) for x in range(1, p.w, stride)
               if (x, y) not in p.explored and (x, y) not in p.walls
               and (x, y) not in p.solids
               and (x, y) not in _launcher_hazards(p)
               and (x // stride + y // stride) % 3 == p.builder_index % 3]
    if not choices:
        p.explored.clear()
        corners = ((0, 0), (p.w - 1, 0), (0, p.h - 1), (p.w - 1, p.h - 1))
        target = max(corners, key=lambda q: (
            max(abs(q[0] - me[0]), abs(q[1] - me[1])), q
        ))
        _step(p, ct, Position(*target), False)
        return
    target = min(choices, key=lambda q: max(abs(q[0] - me[0]), abs(q[1] - me[1])))
    # A Builder already observes radius^2 20; don't idle walking to the exact
    # centre of an area that is fully visible.
    if (target[0] - me[0]) ** 2 + (target[1] - me[1]) ** 2 <= 20:
        p.explored.add(target)
        _explore(p, ct)
        return
    _step(p, ct, Position(*target), False)


def _harass(p, ct):
    """Scout for the enemy economy and sabotage high-value logistics.

    The opening harasser deliberately ignores the Core and combat buildings.
    Builder attacks are too slow and expensive for a Core kill, while damaging
    logistics immediately denies income and forces an opposing Builder home.
    """
    me = tuple(ct.get_position())
    targets = sorted(
        p.enemy_economy,
        key=lambda tile: (
            HARASS_PRIORITY[p.enemy_economy[tile]],
            max(abs(tile[0] - me[0]), abs(tile[1] - me[1])),
            tile,
        ),
    )
    # 2.3.3 inverted the attack rule: a Builder damages an orthogonally
    # adjacent tile and never the one it stands on, so stand *beside* the
    # target rather than on it.
    for target in targets:
        if ct.can_fire(Position(*target)):
            ct.fire(Position(*target))
            _mark_progress(p, ct, "fired", target)
            return

    # A 3 Ti barrier on an enemy-half ore tile denies its Harvester for the
    # whole match (measured: the victim collected zero). Cheaper and more
    # permanent than shooting a belt they rebuild for 3 Ti.
    if _deny_enemy_ore(p, ct):
        return

    if targets:
        _step(p, ct, Position(*targets[0]), False)
        return

    denial_target = _nearest_enemy_ore(p, ct)
    if denial_target is not None:
        _step(p, ct, Position(*denial_target), False)
        return

    # No remembered economy is reachable yet. Resolve the enemy-Core location
    # and continue normal partitioned exploration; infrastructure discovered on
    # the way is recorded by _sense and attacked on the following round.
    _explore(p, ct)


def _nearest_enemy_ore(p, ct):
    """The closest free enemy-half ore tile worth walking to and denying."""
    packed = ct.read_store(SLOT_ENEMY_CORE)
    if packed == 0 or p.core is None:
        return None
    enemy_core, _ = unpack_enemy(packed)
    me = tuple(ct.get_position())
    candidates = [
        ore for ore in p.ores
        if ore not in p.solids
        and _distance_sq(ore, enemy_core) < _distance_sq(ore, p.core)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda ore: (
        max(abs(ore[0] - me[0]), abs(ore[1] - me[1])), ore))


def _deny_enemy_ore(p, ct):
    """Barrier an adjacent free ore tile on the enemy's side of the map."""
    packed = ct.read_store(SLOT_ENEMY_CORE)
    if packed == 0 or p.core is None:
        return False
    enemy_core, _ = unpack_enemy(packed)
    cost = ct.get_barrier_cost()
    if ct.get_global_resources() < cost + SEAL_TITANIUM_RESERVE:
        return False
    me = tuple(ct.get_position())
    for dx, dy in D4_DELTAS:
        spot = me[0] + dx, me[1] + dy
        if (spot in p.ores and spot not in p.solids
                and _distance_sq(spot, enemy_core) < _distance_sq(spot, p.core)
                and ct.can_build_barrier(Position(*spot))):
            ct.build_barrier(Position(*spot))
            _mark_progress(p, ct, "denied enemy ore", spot)
            p.solids.add(spot)
            return True
    return False


def _heal_core(p, ct):
    """Return the economy Builder to repair a Core under active fire."""
    for tile in sorted(p.foot):
        position = Position(*tile)
        if ct.can_heal(position):
            ct.heal(position)
            _mark_progress(p, ct, "healed", tuple(position))
            return
    _step(p, ct, Position(*p.core), False)


def _run_launcher_ring(p, ct):
    """Build the Launcher ring, returning true when economy work can resume."""
    packed = ct.read_store(SLOT_ENEMY_CORE)
    if packed == 0:
        _explore(p, ct)
        return False
    enemy_core, _ = unpack_enemy(packed)
    if not hasattr(p, "launcher_ring_targets"):
        p.launcher_ring_targets = _launcher_ring_targets(p, enemy_core)
        p.launcher_ring_done = set()
        p.launcher_ring_built = 0
    # Spawning this Builder first buys the pad early; it also gives it time to
    # build the whole eight-site compass ring, which is not what the tempo was
    # bought for. On aurora it put up three ring Launchers by round 8 on top of
    # the two the relay chain wanted -- +50% scale before the first Harvester.
    # The pad is one Launcher on the enemy-facing site; the rest of the ring is
    # a screen this bot has never measured a win from.
    if p.launcher_ring_built >= RING_MAX_SITES:
        return True

    # With more than one ring Builder there is no store slot left to claim
    # sites in, so they stride the list from different offsets and then fall
    # through to the whole of it; a site is skipped anyway once a building is
    # visible on it.
    ordered = (p.launcher_ring_targets[p.ring_slot::LAUNCHER_BUILDERS]
               + p.launcher_ring_targets)
    for target in ordered:
        key = tuple(target)
        if key in p.launcher_ring_done:
            continue
        if ct.is_in_vision(target):
            building_id = ct.get_tile_building_id(target)
            if building_id is not None:
                p.launcher_ring_done.add(key)
                continue
        here = ct.get_position()
        if _cardinal_distance(tuple(here), key) != 1:
            _move_cardinal_adjacent(p, ct, key)
            return False
        if (ct.get_global_resources() >= ct.get_launcher_cost()
                and ct.can_build_launcher(target)):
            ct.build_launcher(target)
            _mark_progress(p, ct, "built ring launcher", key)
            p.solids.add(key)
            p.launcher_ring_done.add(key)
            p.launcher_ring_built += 1
        elif _build_failure(
                p, ct, key, "ring launcher", ct.get_launcher_cost()):
            p.launcher_ring_done.add(key)
        return False
    return True


def _core_seal_targets(p, enemy_core):
    """Tiles that, once solid, put every Core-threatening tile out of reach.

    An enemy turret hurts the Core from any tile within CORE_THREAT_RADIUS_SQ
    of the footprint, and an enemy Builder builds onto a tile orthogonally
    adjacent to itself. So the set an enemy Builder must never stand in is the
    threat disc expanded by one, and the seal is the shell immediately outside
    that. Fill the shell and no cardinal path leads in -- which is the point,
    because ringing the Core more tightly only made them place turrets a little
    further out and shoot over the gap.

    Barriers, not Launchers. Three titanium and +1% each against twenty and
    +10%, and they block line of sight too, so even a turret built outside the
    seal loses its firing line to the Core.

    Terrain walls and the map edge already seal; they are simply absent from
    the shell. Ore is skipped because it cannot be built on, which does leave a
    hole -- an honest one, not one this function can close.
    """
    threat = set()
    for tile in p.foot:
        for x in range(tile[0] - 4, tile[0] + 5):
            for y in range(tile[1] - 4, tile[1] + 5):
                if _distance_sq((x, y), tile) <= CORE_THREAT_RADIUS_SQ:
                    threat.add((x, y))
    forbidden = set(threat)
    for tile in threat:
        for dx, dy in D4_DELTAS:
            forbidden.add((tile[0] + dx, tile[1] + dy))

    shell = set()
    for tile in forbidden:
        for dx, dy in D4_DELTAS:
            spot = (tile[0] + dx, tile[1] + dy)
            if spot in forbidden or not _inside(p, spot):
                continue
            if spot in p.walls or spot in p.ores or spot in p.foot:
                continue
            shell.add(spot)
    # Enemy-facing arc first: a half-built seal should be closed on the side
    # they are actually coming from.
    return [Position(*spot) for spot in
            sorted(shell, key=lambda s: (_distance_sq(s, enemy_core), s))]


def _run_core_seal(p, ct):
    """Wall off the Core's threat zone, returning true when there is nothing left.

    Deliberately after the Launcher ring: the ring is the attacker's throw pad
    and is up in a few rounds, while the seal is dozens of tiles and will often
    not finish before the game does. Getting the enemy-facing arc closed is
    most of the value.
    """
    packed = ct.read_store(SLOT_ENEMY_CORE)
    if packed == 0:
        return True
    enemy_core, _ = unpack_enemy(packed)
    if not hasattr(p, "seal_targets"):
        p.seal_targets = _core_seal_targets(p, enemy_core)
        p.seal_done = set()

    for target in p.seal_targets:
        key = tuple(target)
        if key in p.seal_done:
            continue
        if ct.is_in_vision(target) and ct.get_tile_building_id(target) is not None:
            p.seal_done.add(key)
            continue
        cost = ct.get_barrier_cost()
        if ct.get_global_resources() < cost + SEAL_TITANIUM_RESERVE:
            # Hold a reserve: a perimeter is worth less than the Harvester or
            # the ammunition it would otherwise have starved. Yield the round
            # -- the caller sends this Builder mining instead of freezing.
            return True
        here = ct.get_position()
        if _cardinal_distance(tuple(here), key) != 1:
            _move_cardinal_adjacent(p, ct, key)
            return False
        if ct.can_build_barrier(target):
            ct.build_barrier(target)
            _mark_progress(p, ct, "built seal barrier", key)
            p.solids.add(key)
            p.seal_done.add(key)
        elif _build_failure(p, ct, key, "seal barrier", cost):
            p.seal_done.add(key)
        return False
    return True


def _launcher_ring_targets(p, enemy_core):
    """Ring the Core at RING_RADIUS, enemy-facing site first.

    A screen thrown out towards the enemy covers one approach and is worthless
    the moment they come around it, and it is four tiles from home, so the
    Builder walks before it can build. Ringing our own Core covers every
    direction at once and the first Launcher is up almost immediately.

    The ring is also the attacker's throw pad. A Launcher picks up a Builder
    within radius squared 2, so a Builder leaving the Core is adjacent to a ring
    site and gets thrown out rather than building a second Launcher purely to
    escape with. Sorting enemy-first is what makes that work -- the pad has to
    be the one site that exists when the attacker asks for it.
    """
    core_x, core_y = p.core
    targets = []
    for dx, dy in RING_DELTAS:
        if _edge_distance(p, dx, dy) <= RING_EDGE_MARGIN:
            continue
        # The Core is 2x2, so a diagonal has one ring tile but a cardinal has
        # two. Take whichever of the pair leans towards the enemy.
        if dx > 0:
            x = core_x + 1 + RING_RADIUS
        elif dx < 0:
            x = core_x - RING_RADIUS
        else:
            x = min((core_x, core_x + 1), key=lambda v: abs(enemy_core[0] - v))
        if dy > 0:
            y = core_y + 1 + RING_RADIUS
        elif dy < 0:
            y = core_y - RING_RADIUS
        else:
            y = min((core_y, core_y + 1), key=lambda v: abs(enemy_core[1] - v))
        site = (x, y)
        if not _inside(p, site) or site in targets:
            continue
        if site in p.walls or site in p.ores or site in p.foot:
            continue
        targets.append(site)

    targets.sort(key=lambda site: (_distance_sq(site, enemy_core), site))
    return [Position(*site) for site in targets]


def _edge_distance(p, dx, dy):
    """Tiles between the Core footprint and the map edge along one direction."""
    spans = []
    if dx > 0:
        spans.append(p.w - 1 - (p.core[0] + 1))
    elif dx < 0:
        spans.append(p.core[0])
    if dy > 0:
        spans.append(p.h - 1 - (p.core[1] + 1))
    elif dy < 0:
        spans.append(p.core[1])
    # A diagonal needs room in both of its components, so the tighter one
    # decides: an enemy cannot come from the south-east of a Core sitting
    # two tiles off the east edge.
    return min(spans) if spans else p.w + p.h


def _aligned_gunner_site(p, ct, enemies):
    """Best adjacent tile and facing from which a new Gunner could fire now.

    Shared by home defence and by field engagement so both answer an enemy the
    same way: a real firing solution from a tile we may legally build on, never
    a hopeful compass bearing. _preserves_friendly_turret_lanes keeps the new
    turret out of the line of the ones already standing.
    """
    me = ct.get_position()
    protected_lanes = _friendly_turret_lanes(ct)
    candidates = []
    for direction in D8:
        position = me.add(direction)
        if not _inside(p, tuple(position)) or tuple(position) in p.foot:
            continue
        for enemy_id in enemies:
            target = ct.get_position(enemy_id)
            facing = _ray_direction(tuple(position), tuple(target))
            if (facing is not None
                    and position.distance_squared(target) <= GUNNER_RANGE_SQ
                    and ct.can_fire_from(
                        position, facing, EntityType.GUNNER, target,
                    )
                    and _preserves_friendly_turret_lanes(
                        ct, position, protected_lanes,
                    )
                    and ct.can_build_gunner(position, facing)):
                candidates.append((
                    COMBAT_PRIORITY.get(ct.get_entity_type(enemy_id), 4),
                    position.distance_squared(target),
                    position.x, position.y, D8.index(facing), position, facing,
                ))
    if not candidates:
        return None
    *_, position, facing = min(candidates)
    return position, facing


def _engage_with_turret(p, ct):
    """Answer any enemy this Builder can see with an aligned Gunner.

    The meta this chases does not wait for enemies to reach the Core: it puts a
    turret on whatever it meets, wherever it meets it, unclaimed ground
    included. A Builder that walks past an enemy scout and does nothing has
    given up that ground for free.

    The cap is what keeps this from becoming the whole economy. Each field
    Gunner is its cost plus +10% on every build the team makes afterwards, so
    "a turret for every enemy" pays for itself only while the count is small.
    """
    if (p.field_gunners_built >= p.max_field_gunners
            or ct.get_global_ammo() < MIN_AMMO_FOR_GUNNER
            # Keep a harvester's worth of budget out of reach: a field Gunner
            # bought with the economy's opening titanium costs far more than
            # its price.
            or ct.get_global_resources()
            < ct.get_gunner_cost() + ct.get_harvester_cost()):
        return False
    enemies = [entity_id for entity_id in ct.get_nearby_entities()
               if ct.get_team(entity_id) != ct.get_team()]
    if not enemies:
        return False
    enemies.sort(key=lambda entity_id: (
        COMBAT_PRIORITY.get(ct.get_entity_type(entity_id), 4),
        ct.get_position(entity_id).distance_squared(ct.get_position()),
        entity_id,
    ))
    site = _aligned_gunner_site(p, ct, enemies)
    if site is None:
        return False
    position, facing = site
    ct.build_gunner(position, facing)
    _mark_progress(p, ct, "built field gunner", tuple(position))
    p.field_gunners_built += 1
    return True


def _guard_home(p, ct):
    """Turret an enemy that has come to our Core, before the alarm would fire.

    The defence this lineage shipped with is `_defend_core`, and it triggers on
    `SLOT_CORE_DAMAGED` -- which the Core only raises once it has already lost
    50 HP. That is five Gunner rounds *after* their turret went up, and by then
    answering it costs a turret duel instead of four shots at a Builder.

    Sighting is the cheaper trigger, and it is decisive because of how thin the
    attack it interrupts actually is. The whole enemy attack is carried by one
    Builder: their Core will not spawn a replacement while any of their
    Builders still answers the heartbeat, so a Builder killed on our doorstep
    is an attack that does not come back. A Gunner is 10 Ti and kills a 40 HP
    Builder in four rounds.

    Measured on the 21 official maps in both seats against valkyrie, vigil,
    ragnarok and vanguard, 168 games: the warden_walk chassis takes 118 with
    this off and 145 with it on, and against valkyrie alone it goes from 26/42
    to 40/42. Both the trigger radius and the cap were measured, not chosen.

    Deliberately *only* this Builder. Letting every Builder guard scores 137 --
    the economy Builder abandons the belt it is laying and the miner stops
    mining, and the games that buys back are fewer than the ones it costs.
    """
    if (p.guard_gunners_built >= MAX_GUARD_GUNNERS
            or ct.get_global_ammo() < MIN_AMMO_FOR_GUNNER
            or ct.get_global_resources() < ct.get_gunner_cost()):
        return False
    team = ct.get_team()
    enemies = []
    for entity_id in ct.get_nearby_entities():
        if ct.get_team(entity_id) == team:
            continue
        spot = tuple(ct.get_position(entity_id))
        near = min(_distance_sq(spot, tile) for tile in p.foot)
        if near <= GUARD_RADIUS_SQ:
            enemies.append((COMBAT_PRIORITY.get(ct.get_entity_type(entity_id), 4),
                            near, entity_id))
    if not enemies:
        return False
    enemies.sort()
    ordered = [entity_id for _, _, entity_id in enemies]
    site = _aligned_gunner_site(p, ct, ordered)
    if site is not None:
        position, facing = site
        ct.build_gunner(position, facing)
        _mark_progress(p, ct, "built guard gunner", tuple(position))
        p.solids.add(tuple(position))
        p.guard_gunners_built += 1
        return True
    # No firing seat from here. Close the distance a little rather than let the
    # intruder emplace -- but never leave the Core to do it, because the ring,
    # the seal and the next intruder are all back here.
    target = ct.get_position(ordered[0])
    if (_cardinal_distance(tuple(ct.get_position()), tuple(target))
            <= GUARD_CHASE_STEPS):
        # Never with a Launcher: a four-step walk is not worth 20 Ti and a
        # permanent +10%, and the ferry exists to cross the map, not a yard.
        return _step(p, ct, target, False, allow_launcher=False)
    return False


def _defend_core(p, ct):
    """Answer a visible Core attack with an ordinary counter-firing Gunner.

    This deliberately has no opening layout or inferred firing position: the
    economy Builder must first see both the damage and a target it can align
    with from a locally buildable tile.  Otherwise it falls back to repairs.
    """
    enemies = [entity_id for entity_id in ct.get_nearby_entities()
               if ct.get_team(entity_id) != ct.get_team()]
    enemies.sort(key=lambda entity_id: (
        COMBAT_PRIORITY.get(ct.get_entity_type(entity_id), 4),
        ct.get_position(entity_id).distance_squared(Position(*p.core)),
        entity_id,
    ))
    # Escalate slowly with sustained damage rather than committing a fixed
    # defensive formation before the bot knows whether one is needed.
    core_position = Position(*p.core)
    core_id = (ct.get_tile_building_id(core_position)
               if ct.is_in_vision(core_position) else None)
    damage = (ct.get_max_hp(core_id) - ct.get_hp(core_id)) if core_id else 0
    desired = min(4, 1 + damage // 180)
    if (ct.get_global_ammo() >= MIN_AMMO_FOR_GUNNER
            and p.home_gunners_built < desired):
        site = _aligned_gunner_site(p, ct, enemies)
        if site is not None:
            position, facing = site
            ct.build_gunner(position, facing)
            _mark_progress(p, ct, "built defensive gunner", tuple(position))
            p.home_gunners_built += 1
            return
    if _block_firing_lane(p, ct, enemies):
        return
    _heal_core(p, ct)


def _block_firing_lane(p, ct, enemies):
    """Rebuild-tank: a 3 Ti barrier in a Gunner's lane absorbs its whole clock.

    Measured in the lab: one Builder rebuilding the lane barrier held a Core
    at zero damage through 201 rounds of sustained Gunner fire for about
    1 Ti a round, while the shooter burned 2 Ti a shot. The barrier is
    rebuilt for as long as the lane is live, because this runs every round
    the alarm is up. Sentinel lanes are not blockable and fall through to
    healing, which two menders out-pace.
    """
    core_tiles = sorted(p.foot)
    me = tuple(ct.get_position())
    best = None
    for enemy_id in enemies:
        if ct.get_entity_type(enemy_id) != EntityType.GUNNER:
            continue
        origin = tuple(ct.get_position(enemy_id))
        facing = ct.get_direction(enemy_id)
        dx, dy = facing.delta()
        # Walk the ray; it is live if the first targetable tile is our Core.
        tile = origin[0] + dx, origin[1] + dy
        lane = []
        while (_inside(p, tile) and tile not in p.walls
               and _distance_sq(origin, tile) <= GUNNER_RANGE_SQ):
            if tile in core_tiles:
                for spot in lane:
                    rank = (_cardinal_distance(me, spot), spot)
                    if best is None or rank < best[0]:
                        best = (rank, spot)
                break
            if ct.is_in_vision(Position(*tile)) and (
                    ct.get_tile_building_id(Position(*tile)) is not None
                    or ct.get_tile_builder_bot_id(Position(*tile)) is not None):
                break  # something else already soaks this lane
            lane.append(tile)
            tile = tile[0] + dx, tile[1] + dy
    if best is None:
        return False
    _, spot = best
    if ct.get_global_resources() < ct.get_barrier_cost():
        return False
    if _cardinal_distance(me, spot) != 1:
        _move_cardinal_adjacent(p, ct, spot)
        return True
    position = Position(*spot)
    if ct.can_build_barrier(position):
        ct.build_barrier(position)
        _mark_progress(p, ct, "blocked firing lane", spot)
        p.solids.add(spot)
        return True
    return False


def _block_siege_lane(p, ct):
    """Rebuild-tank the siege: the same barrier trick, aimed the other way.

    `_block_firing_lane` soaks a Gunner aimed at our own Core and only ever
    runs from the defence alarm. This is the mirror: out at the enemy Core, the
    lanes that matter run from their home Gunners onto the battery we are
    building, and soaking those is what keeps the battery alive long enough to
    finish the Core.

    Pantheon does exactly this and does almost nothing else with barriers --
    31 of the 33 barriers across twenty decoded ladder games sit in an enemy
    Gunner's ray, every one of them 2-5 tiles from the *enemy* Core and 11-36
    from their own, and each is rebuilt on the same tile as fast as it dies
    (one tile took eighteen shots across six rebuilds).

    The trade is lopsided. A barrier is 3 Ti and +1% scale for 30 HP, so it
    eats three Gunner rounds and six of their ammunition -- and ammunition is
    titanium 1:1 -- while costing a fifth of that and buying three rounds in
    which their defence is shooting a wall instead of our turrets.

    The one condition is that the lane has to be theirs alone. Units act in
    spawn-id order (verified: 421 turns, no exception), so a barrier that
    blocks both ways is decided by who lands the killing blow on it: with
    mutual fire the earlier-id turret breaks its own cover and hands the later
    one a clear shot. Rather than track parity, `_preserves_friendly_turret_
    lanes` simply refuses any tile one of our own turrets is firing through --
    which is free in practice, because our battery faces their Core while their
    defence faces our battery, so the two lanes rarely coincide.
    """
    if not SIEGE_BARRIER_ENABLED or p.attack_gunners_built < 1:
        # Nothing emplaced yet means nothing worth soaking for. Soaking on
        # behalf of the Builder itself measured worse (17/42 against 20/42):
        # the Builder can step out of a lane for free, and every round it
        # spends laying cover instead of turrets is a round the battery that
        # actually kills the Core does not exist.
        return False
    cost = ct.get_barrier_cost()
    if ct.get_global_resources() < cost + SIEGE_BARRIER_RESERVE:
        return False
    me = tuple(ct.get_position())
    team = ct.get_team()
    protected = _friendly_turret_lanes(ct)
    best = None
    for enemy_id in ct.get_nearby_buildings():
        if (ct.get_team(enemy_id) == team
                or ct.get_entity_type(enemy_id) != EntityType.GUNNER):
            continue
        origin = tuple(ct.get_position(enemy_id))
        dx, dy = ct.get_direction(enemy_id).delta()
        tile = origin[0] + dx, origin[1] + dy
        lane = []
        while (_inside(p, tile) and tile not in p.walls
               and _distance_sq(origin, tile) <= GUNNER_RANGE_SQ):
            if not ct.is_in_vision(Position(*tile)):
                break
            position = Position(*tile)
            occupant = ct.get_tile_building_id(position)
            if occupant is None and ct.get_tile_builder_bot_id(position) is not None:
                break  # a body already soaks this lane, and it can walk away
            if occupant is not None:
                # Only a *building* of ours is worth cover: it cannot dodge.
                if ct.get_team(occupant) == team:
                    for spot in lane:
                        rank = (_cardinal_distance(me, spot), spot)
                        if best is None or rank < best[0]:
                            best = (rank, spot)
                break
            lane.append(tile)
            tile = tile[0] + dx, tile[1] + dy
    if best is None:
        return False
    _, spot = best
    if (spot in p.ores or spot in p.walls
            or not _preserves_friendly_turret_lanes(ct, Position(*spot), protected)):
        return False
    if _cardinal_distance(me, spot) != 1:
        _move_cardinal_adjacent(p, ct, spot)
        return True
    position = Position(*spot)
    if ct.can_build_barrier(position):
        ct.build_barrier(position)
        _mark_progress(p, ct, "blocked siege lane", spot)
        p.solids.add(spot)
        return True
    return False


def _rush(p, ct):
    """Walk in and build a small, conventional direct-fire attack."""
    packed = ct.read_store(SLOT_ENEMY_CORE)
    if packed == 0:
        _explore(p, ct)
        return
    enemy_core, sighted = unpack_enemy(packed)
    if p.sentinel_wrap and _wrap_siege_sentinel(p, ct):
        return
    if _opening_ferry(p, ct, enemy_core, sighted):
        return
    # Soak before building. A battery with a live enemy lane onto it loses a
    # turret faster than a Builder can replace one, and the barrier is a third
    # of the price of what it is protecting.
    if _block_siege_lane(p, ct):
        return
    if p.attack_gunners_built < 5 and _build_basic_gunner(p, ct, enemy_core):
        return
    _harass(p, ct)


def _build_siege_sentinel(p, ct, enemy_core):
    """Answer a Core no Gunner lane reaches with the shot nothing blocks.

    A Sentinel's line pierces walls, buildings, and bodies, so a legal seat
    only needs eight-way alignment with a Core tile inside range -- the very
    terrain that defeated the Gunner search is irrelevant to it. It pays
    2.78x more per point of damage, which is why this runs only after the
    Gunner and Launcher-breaker searches have both come up empty.
    """
    if p.siege_sentinel is not None:
        return False
    # This search is the widest in the bot (13x13 around four Core tiles) and
    # it runs last, after two others have already spent the turn. Skipping it
    # costs a fallback that fires in a handful of games; overrunning costs the
    # whole round, for every unit, on the map where it happens.
    if _out_of_time(ct):
        return False
    if ct.get_global_ammo() < MIN_AMMO_FOR_SENTINEL:
        return False
    core_tiles = {(enemy_core[0] + dx, enemy_core[1] + dy)
                  for dx in (0, 1) for dy in (0, 1)}
    # Plan against known terrain: we must be close enough to have seen the
    # Core's surrounds, or the "seat" may be a wall we have not met yet.
    if not any(tile in p.seen for tile in core_tiles):
        return False
    me = tuple(ct.get_position())
    distances = _distance_map(p, me)
    protected_lanes = _friendly_turret_lanes(ct)
    choices = []
    for core_tile in sorted(core_tiles):
        for dx in range(-6, 7):
            for dy in range(-6, 7):
                spot = core_tile[0] + dx, core_tile[1] + dy
                if (not _inside(p, spot) or spot in core_tiles
                        or spot in p.walls or spot in p.ores or spot in p.solids
                        or spot in p.foot
                        or spot in p.rejected_build_sites):
                    continue
                facing = _ray_direction(spot, core_tile)
                if (facing is None
                        or _distance_sq(spot, core_tile) > SENTINEL_RANGE_SQ
                        or not ct.can_fire_from(
                            Position(*spot), facing, EntityType.SENTINEL,
                            Position(*core_tile),
                        )
                        or not _preserves_friendly_turret_lanes(
                            ct, Position(*spot), protected_lanes,
                        )):
                    continue
                goals = (_cardinal_adjacent(p, spot) - p.walls - p.solids
                         - _launcher_hazards(p))
                distance = min(
                    (distances[goal] for goal in goals if goal in distances),
                    default=None,
                )
                if distance is not None:
                    # Prefer arriving soon, then the farthest seat: distance
                    # from the Core is safety the wrap does not have to buy.
                    choices.append((
                        distance, -_distance_sq(spot, core_tile),
                        spot, D8.index(facing), facing,
                    ))
    if not choices:
        return False
    _, _, spot, _, facing = min(choices)
    position = Position(*spot)
    if _cardinal_distance(me, spot) != 1:
        _move_cardinal_adjacent(p, ct, spot)
        return True
    if ct.can_build_sentinel(position, facing):
        ct.build_sentinel(position, facing)
        _mark_progress(p, ct, "built siege sentinel", spot)
        p.solids.add(spot)
        p.siege_sentinel = spot
        # Wrap the exposed sides so conventional return fire cannot reach it;
        # its own shot pierces the wrap. Enemy-facing side first.
        p.sentinel_wrap = sorted(
            (tile for tile in _cardinal_adjacent(p, spot)
             if tile not in p.walls and tile not in p.solids
             and tile not in p.ores),
            key=lambda tile: (_distance_sq(tile, enemy_core), tile),
        )
    elif _build_failure(p, ct, spot, "siege sentinel", ct.get_sentinel_cost()):
        p.rejected_build_sites.add(spot)
    return True


def _wrap_siege_sentinel(p, ct):
    """Lay the barrier wrap around a fresh siege Sentinel, one tile a round."""
    while p.sentinel_wrap:
        target = p.sentinel_wrap[0]
        if target in p.solids or target in p.walls:
            p.sentinel_wrap.pop(0)
            continue
        cost = ct.get_barrier_cost()
        if ct.get_global_resources() < cost + SENTINEL_WRAP_RESERVE:
            # The wrap is insurance, not the weapon; never starve the shot.
            return False
        me = tuple(ct.get_position())
        if me == target:
            # Standing on the tile to be walled: step to any free neighbour.
            return _move_while_stuck(p, ct, Position(*p.siege_sentinel))
        if _cardinal_distance(me, target) != 1:
            _move_cardinal_adjacent(p, ct, target)
            return True
        position = Position(*target)
        if ct.can_build_barrier(position):
            ct.build_barrier(position)
            _mark_progress(p, ct, "built sentinel wrap", target)
            p.solids.add(target)
            p.sentinel_wrap.pop(0)
        elif _build_failure(p, ct, target, "sentinel wrap", cost):
            p.sentinel_wrap.pop(0)
        return True
    return False


def _opening_ferry(p, ct, enemy_core, sighted=False):
    """Relay every attacker toward a sufficiently distant enemy Core.

    The gate is knowing where the enemy Core actually is. `sighted` is that
    flag: the store carries it set when a unit has physically seen the Core and
    clear when the position is only the symmetry inference's best guess.
    Ferrying at a guess is what the ancestor of this function was right to
    refuse -- a wrong throw spends a Launcher and puts the attacker further
    from the real Core than it started -- so the guess still walks. In this
    bot, which has no map oracle at all, that gate is the whole of the
    difference between relaying and walking.
    """
    if not (sighted or FERRY_ON_INFERENCE):
        return False

    if _consume_launch_rejection(p, ct) or p.launch_blocked:
        return False

    here = tuple(ct.get_position())
    if (_chebyshev(p.core, enemy_core) <= RELAY_STOP_DISTANCE
            or _chebyshev(here, enemy_core) <= RELAY_STOP_DISTANCE):
        p.awaiting_launch = 0
        p.launch_origin = None
        return False

    target = Position(*enemy_core)
    launchers = _visible_friendly_launchers(ct)
    adjacent = _adjacent_visible_launcher(ct, target, launchers)
    if adjacent is not None:
        p.awaiting_launch = LAUNCH_REQUEST_ROUNDS
        p.launch_origin = here
        if _announce_launch(p, ct, target, adjacent[1]):
            return True
        p.awaiting_launch = 0
        p.launch_origin = None
        return False

    if launchers:
        # Reuse a forward Launcher. If only the previous relay remains behind
        # us, keep walking toward the Core until it leaves vision; never build
        # a duplicate while any friendly Launcher is visible.
        current_distance = Position(*here).distance_squared(target)
        forward = [launcher for launcher in launchers
                   if launcher[1].distance_squared(target) < current_distance]
        destination = (min(forward, key=lambda launcher: (
            launcher[1].distance_squared(target), launcher[1].x, launcher[1].y,
        ))[1] if forward else target)
        _step(p, ct, destination, False, allow_launcher=False)
        return True

    return _build_escape_launcher(p, ct, target)


def _chebyshev(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _build_basic_gunner(p, ct, enemy_core):
    """Build on the nearest visible legal ray, without a special formation."""
    if ct.get_global_ammo() < MIN_AMMO_FOR_GUNNER:
        return False
    core_tiles = {(enemy_core[0] + dx, enemy_core[1] + dy)
                  for dx in (0, 1) for dy in (0, 1)}
    me = tuple(ct.get_position())
    distances = _distance_map(p, me)
    protected_lanes = _friendly_turret_lanes(ct)
    # A Gunner seated on a tile an enemy turret already covers is shot before
    # it has fired much. Prefer any legal seat outside their rays and take a
    # covered one only when nothing else reaches -- it is a sort key, not a
    # filter, so a covered seat still beats no seat.
    enemy_cover = _enemy_turret_cover(p, ct) if AVOID_ENEMY_RAYS else frozenset()
    choices = []
    for core_tile in sorted(core_tiles):
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                spot = core_tile[0] + dx, core_tile[1] + dy
                if (not _inside(p, spot) or spot in core_tiles
                        or spot in p.walls or spot in p.ores or spot in p.solids
                        or spot in p.rejected_build_sites):
                    continue
                facing = _ray_direction(spot, core_tile)
                if (facing is None
                        or _distance_sq(spot, core_tile) > GUNNER_RANGE_SQ
                        or not ct.can_fire_from(
                            Position(*spot), facing, EntityType.GUNNER,
                            Position(*core_tile),
                        )
                        or not _preserves_friendly_turret_lanes(
                            ct, Position(*spot), protected_lanes,
                        )):
                    continue
                goals = (_cardinal_adjacent(p, spot) - p.walls - p.solids
                         - _launcher_hazards(p))
                distance = min(
                    (distances[goal] for goal in goals if goal in distances),
                    default=None,
                )
                if distance is not None:
                    choices.append((spot in enemy_cover, distance, spot,
                                    D8.index(facing), facing))
    # Self-blocking is checked in preference order and stops at the first site
    # that survives, rather than for every candidate: the cheap tests above
    # have already ruled most sites out, and the best site almost always keeps
    # the route open, so this costs one search instead of one per candidate.
    if choices:
        choices.sort()
        baseline = _route_baseline(p, me, Position(*enemy_core), False)
        choices = [
            next((choice for choice in choices
                  if _keeps_route_open(p, choice[1], me,
                                       Position(*enemy_core), False, baseline)),
                 None)
        ]
        choices = [choice for choice in choices if choice is not None]
    if not choices:
        blocking = _blocking_launchers(p, me, tuple(enemy_core), False)
        if _build_launcher_breaker_gunner(
                p, ct, blocking=blocking, route=Position(*enemy_core)):
            return True
        if _build_siege_sentinel(p, ct, enemy_core):
            return True
        _explore(p, ct)
        return True
    _, _, spot, _, facing = min(choices)
    position = Position(*spot)
    if not ct.is_in_vision(position):
        _step(p, ct, position, False)
        return True
    if _cardinal_distance(me, spot) != 1:
        _move_cardinal_adjacent(p, ct, spot)
        return True
    if ct.can_build_gunner(position, facing):
        ct.build_gunner(position, facing)
        _mark_progress(p, ct, "built core gunner", spot)
        p.solids.add(spot)
        p.attack_gunners_built += 1
    elif _build_failure(p, ct, spot, "core gunner", ct.get_gunner_cost()):
        p.rejected_build_sites.add(spot)
    return True


def _build_launcher_breaker_gunner(p, ct, blocking=None, route=None):
    """Reach a safe build tile and place a Gunner aimed at a blocking Launcher.

    `blocking` restricts the target set to Launchers actually standing in the
    route; without it every visible Launcher is fair game, which is how the bot
    used to spend Gunners on ones that were never in the way.
    """
    if ct.get_global_ammo() < MIN_AMMO_FOR_GUNNER:
        return False
    me = tuple(ct.get_position())
    targets = sorted(p.enemy_launchers if blocking is None else blocking)
    if not targets:
        return False
    distances = _distance_map(p, me)
    protected_lanes = _friendly_turret_lanes(ct)
    choices = []
    for launcher_position in targets:
        if launcher_position in p.launcher_breakers:
            continue
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                spot = launcher_position[0] + dx, launcher_position[1] + dy
                if (not _inside(p, spot) or spot in p.foot or spot in p.walls
                        or spot in p.ores or spot in p.solids
                        or spot in p.rejected_build_sites):
                    continue
                facing = _ray_direction(spot, launcher_position)
                if (facing is None
                        or _distance_sq(spot, launcher_position) > GUNNER_RANGE_SQ
                        or not ct.can_fire_from(
                            Position(*spot), facing, EntityType.GUNNER,
                            Position(*launcher_position),
                        )
                        or not _preserves_friendly_turret_lanes(
                            ct, Position(*spot), protected_lanes,
                        )):
                    continue
                goals = (_cardinal_adjacent(p, spot) - p.walls - p.solids
                         - p.bot_occupied - _launcher_hazards(p))
                distance = min(
                    (distances[goal] for goal in goals if goal in distances),
                    default=None,
                )
                if distance is not None:
                    choices.append((
                        distance,
                        _distance_sq(spot, launcher_position),
                        launcher_position,
                        spot,
                        D8.index(facing),
                        facing,
                    ))
    if not choices:
        return False
    # As in _build_basic_gunner: rank first, then pay for the self-blocking
    # search only until a site survives it.
    choices.sort()
    if route is not None:
        baseline = _route_baseline(p, me, route, False)
        chosen = next(
            (choice for choice in choices
             if _keeps_route_open(p, choice[3], me, route, False, baseline)),
            None,
        )
        if chosen is None:
            return False
    else:
        chosen = choices[0]

    _, _, launcher_position, spot, _, facing = chosen
    position = Position(*spot)
    if _cardinal_distance(me, spot) != 1:
        _move_cardinal_adjacent(p, ct, spot)
        return True
    if ct.can_build_gunner(position, facing):
        ct.build_gunner(position, facing)
        _mark_progress(p, ct, "built launcher breaker", spot)
        p.solids.add(spot)
        p.attack_gunners_built += 1
        p.launcher_breakers.add(launcher_position)
    elif _build_failure(
            p, ct, spot, "launcher breaker", ct.get_gunner_cost()):
        p.rejected_build_sites.add(spot)
    return True


def _ray_direction(source, target):
    dx, dy = target[0] - source[0], target[1] - source[1]
    if not (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
        return None
    step = (0 if dx == 0 else (1 if dx > 0 else -1),
            0 if dy == 0 else (1 if dy > 0 else -1))
    return next((direction for direction in D8 if direction.delta() == step), None)


def _enemy_turret_cover(p, ct):
    """Tiles a visible enemy Gunner or Sentinel can currently shoot.

    A Gunner's ray stops at the first targetable tile and is blocked by walls;
    a Sentinel's pierces both, so its whole line counts. Computed once per
    turn, not once per candidate site -- the per-site version is what put an
    earlier build over the turn limit.
    """
    covered = set()
    team = ct.get_team()
    for turret_id in ct.get_nearby_buildings():
        if ct.get_team(turret_id) == team:
            continue
        kind = ct.get_entity_type(turret_id)
        if kind not in (EntityType.GUNNER, EntityType.SENTINEL):
            continue
        origin = tuple(ct.get_position(turret_id))
        try:
            dx, dy = ct.get_direction(turret_id).delta()
        except Exception:  # noqa: BLE001 - a turret with no facing
            continue
        pierces = kind == EntityType.SENTINEL
        reach = SENTINEL_RANGE_SQ if pierces else GUNNER_RANGE_SQ
        tile = origin[0] + dx, origin[1] + dy
        while _inside(p, tile) and _distance_sq(origin, tile) <= reach:
            if tile in p.walls and not pierces:
                break
            covered.add(tile)
            if not pierces and tile in p.solids:
                break
            tile = tile[0] + dx, tile[1] + dy
    return covered


def _friendly_turret_lanes(ct):
    """Map protected firing-ray tiles to the friendly turret and its target."""
    lanes = {}
    enemies = [
        entity_id for entity_id in ct.get_nearby_entities()
        if ct.get_team(entity_id) != ct.get_team()
    ]
    if not enemies:
        return lanes
    for turret_id in ct.get_nearby_buildings():
        if ct.get_team(turret_id) != ct.get_team():
            continue
        turret_type = ct.get_entity_type(turret_id)
        if turret_type not in (EntityType.GUNNER, EntityType.SENTINEL):
            continue
        origin = ct.get_position(turret_id)
        facing = ct.get_direction(turret_id)
        for enemy_id in enemies:
            target = ct.get_position(enemy_id)
            if (_ray_direction(tuple(origin), tuple(target)) != facing
                    or not ct.can_fire_from(
                        origin, facing, turret_type, target,
                    )):
                continue
            dx, dy = facing.delta()
            tile = origin.x + dx, origin.y + dy
            target_tile = tuple(target)
            while tile != target_tile:
                lanes.setdefault(tile, (turret_id, target_tile))
                tile = tile[0] + dx, tile[1] + dy
    return lanes


def _preserves_friendly_turret_lanes(
        ct, proposed_position, protected_lanes=None):
    """Reject a building tile that would interrupt a friendly turret's shot."""
    proposed = tuple(proposed_position)
    lanes = (protected_lanes if protected_lanes is not None
             else _friendly_turret_lanes(ct))
    blocker = lanes.get(proposed)
    if blocker is not None:
        turret_id, target = blocker
        print(
            f"PLAN_FAILED id={ct.get_id()} "
            f"round={ct.get_current_round()} action=place turret "
            f"target={proposed} reason=would block friendly "
            f"turret={turret_id} firing_at={target}"
        )
        return False
    return True


def _distance_sq(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _enemy_core_candidates(p):
    """Candidate top-left Core coordinates: rotation, x mirror, y mirror."""
    x, y = p.core
    return (
        (p.w - 2 - x, p.h - 2 - y),
        (p.w - 2 - x, y),
        (x, p.h - 2 - y),
    )


def _transform(p, tile, index):
    x, y = tile
    if index == 0:
        return p.w - 1 - x, p.h - 1 - y
    if index == 1:
        return p.w - 1 - x, y
    return x, p.h - 1 - y


def _update_enemy_core_inference(p, ct):
    """Reject symmetry hypotheses using only this Builder's observations."""
    rejected = p.rejected_symmetries | _team_rejected_symmetries(ct)
    candidates = _enemy_core_candidates(p)
    for index, candidate in enumerate(candidates):
        if rejected & (1 << index):
            continue
        # Seeing the predicted footprint without an enemy Core disproves it.
        footprint = {(candidate[0] + dx, candidate[1] + dy)
                     for dx in (0, 1) for dy in (0, 1)}
        if all(_inside(p, tile) and ct.is_in_vision(Position(*tile))
               for tile in footprint):
            found = False
            for tile in footprint:
                bid = ct.get_tile_building_id(Position(*tile))
                if (bid is not None and ct.get_team(bid) != ct.get_team()
                        and ct.get_entity_type(bid) == EntityType.CORE):
                    ct.write_store(SLOT_ENEMY_CORE, pack_enemy(ct.get_position(bid), True))
                    found = True
                    break
            if not found:
                rejected |= 1 << index
                continue
        # A terrain mismatch between two observed paired cells disproves it.
        for tile, env in p.terrain.items():
            paired = _transform(p, tile, index)
            if paired in p.terrain and p.terrain[paired] != env:
                rejected |= 1 << index
                break
    p.rejected_symmetries = rejected
    ct.write_store(SLOT_SYMMETRY_REJECT_START + min(p.builder_index, 1), rejected)

    surviving = [candidate for i, candidate in enumerate(candidates)
                 if not rejected & (1 << i)]
    if not surviving:
        return
    # Commit to the farthest surviving candidate immediately rather than
    # waiting for the other two to be disproved. Waiting optimises being
    # certain; the game rewards being right early, and the attacker that
    # holds off has spent the rounds that decide it exploring. The farthest
    # candidate is the 180-degree rotation wherever the three differ, which
    # is the truth on 28 of 42 published map-sides against 4 for the nearest
    # -- a fair map places the Cores as far apart as its symmetry allows.
    #
    # Being wrong is cheap and self-correcting: the moment observed terrain
    # contradicts a hypothesis it is struck from `rejected`, and the guess
    # published here moves to the next surviving candidate on the same round.
    best = max(surviving, key=lambda c: (_distance_sq(c, p.core), c))
    current, sighted = unpack_enemy(ct.read_store(SLOT_ENEMY_CORE))
    # A sighting is authoritative: never overwrite one with an inference.
    if not sighted and current != best:
        ct.write_store(SLOT_ENEMY_CORE, pack_enemy(best))


def _enemy_scout_target(p, ct):
    """Assign unresolved candidate footprints across the two Builders."""
    if ct.read_store(SLOT_ENEMY_CORE):
        return None
    rejected = p.rejected_symmetries | _team_rejected_symmetries(ct)
    candidates = []
    for index, candidate in enumerate(_enemy_core_candidates(p)):
        if not rejected & (1 << index) and candidate not in candidates:
            candidates.append(candidate)
    if not candidates:
        return None
    # Farthest candidate first: fair maps put the Cores as far apart as the
    # symmetry allows (28/42 map-sides on the published pool, against 4/42
    # for nearest-first), so the attacker's first guess should be the far one.
    candidates.sort(
        key=lambda c: -_distance_sq(c, p.core) if p.core else 0)
    # Different builder ids investigate different candidates; after a rejection
    # the modulo assignment automatically closes ranks next round.
    assignment = (p.builder_index - p.economy_builders
                  if p.is_attacker else p.builder_index)
    return candidates[assignment % len(candidates)]


def _team_rejected_symmetries(ct):
    return ((ct.read_store(SLOT_SYMMETRY_REJECT_START)
             | ct.read_store(SLOT_SYMMETRY_REJECT_START + 1)) & 0x7)


def _adjacent(p, target):
    return {(target[0] + d.delta()[0], target[1] + d.delta()[1]) for d in D8
            if _inside(p, (target[0] + d.delta()[0], target[1] + d.delta()[1]))}


def _cardinal_adjacent(p, target):
    return {(target[0] + dx, target[1] + dy) for dx, dy in D4_DELTAS
            if _inside(p, (target[0] + dx, target[1] + dy))}


def _cardinal_distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _move_cardinal_adjacent(p, ct, target):
    me = tuple(ct.get_position())
    goals = (_cardinal_adjacent(p, target) - p.walls - p.solids
             - p.bot_occupied - _launcher_hazards(p))
    non_ore_goals = goals - p.ores
    if non_ore_goals:
        goals = non_ore_goals
    distances = _distance_map(p, me)
    reachable = [(distances[goal], goal) for goal in goals
                 if goal in distances]
    if reachable:
        _, goal = min(reachable)
        _step(p, ct, Position(*goal), True)
        return True
    _plan_failed(
        p, ct, "move to build range", target,
        "no reachable cardinal-adjacent tile",
    )
    return False


def _inside(p, tile):
    return 0 <= tile[0] < p.w and 0 <= tile[1] < p.h


def _launcher_hazards(p):
    """Tiles where an enemy Launcher could pick this Builder up."""
    return getattr(p, "enemy_launcher_danger", set())
