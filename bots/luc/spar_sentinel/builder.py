"""Map-agnostic online economy planner and explorer."""

from collections import deque
import sys
from typing import TYPE_CHECKING

from fcode import Controller, EntityType, Environment, GameError, Position, Team

import doctrine
from atlas import identify_visible
from constants import (BELT_SCORE_CANDIDATES, BELT_TILE_WEIGHT,
    RING_AFTER_ECONOMY,
    CORE_ALARM_MASK, ECONOMY_BEFORE_TURRETS, TURRET_HOLD_MIN_HARVESTERS,
    TURRET_HOLD_ROUNDS,
    HARASS_RERANK_CANDIDATES, HARASS_TRUE_DISTANCE,
    
    CLAIM_SLOTS,
    CORE_THREAT_RADIUS_SQ,
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
    AVOID_THREAT_FOR_LOGISTICS,
    BARRIER_INTO_THREAT,
    BELT_PATROL_ROUNDS,
    CONTEST_MAX_DISTANCE_SQ,
    ESCAPE_ENCIRCLEMENT,
    LAUNCHER_BUILD_ROUNDS,
    LEAVE_FIRING_LINE,
    ESCAPE_MIN_EXITS,
    PATROL_RADIUS,
    TRAP_ENEMY_BUILDERS,
    TRAP_MAX_DISTANCE_SQ,
    CUT_ENEMY_BELT,
    GUNNER_DAMAGE,
    HOLD_FIRE_ON_TENDED_BARRIER,
    PATH_LOOKAHEAD,
    FIRE_BLOCK_LAUNCH_ROUNDS,
    PATH_DETOUR_FACTOR,
    PATH_SAFETY_MARGIN,
    REPAIR_ATTEMPT_LIMIT,
    SENTINEL_DAMAGE,
    STEAL_ENEMY_HARVESTER,
    NETWORK_CAP_EARLY,
    NETWORK_CAP_LATE,
    HARVESTER_FINISH_STEPS,
    REPAIR_NETWORK,
    STUCK_ROUNDS_BEFORE_STANDDOWN,
    WRITE_OFF_STUCK_BUILDERS,
    FERRY_ON_INFERENCE,
    PAD_FIRST_ORDER,
    RING_MAX_SITES,
    RING_EXTRA_SITES,
    SELF_SEAL_MIN_OPEN,
    RING_MIN_SEPARATION,
    RING_REPLAN_TILES,
    RING_THREAT_SQ,
    RING_TITANIUM_RESERVE,
    DEBUG_BUILD,
    DEBUG_LAUNCH,
    LAUNCH_HOPS_IN_PATHS,
    LAUNCH_PASSENGER_SHIFT,
    LAUNCH_PICKUP_SQ,
    LAUNCH_RANGE_SQ,
    REACHABILITY_ENABLED,
    RING_EDGE_MARGIN,
    SEAL_TITANIUM_RESERVE,
    SENTINEL_RANGE_SQ,
    SENTINEL_WRAP_RESERVE,
    SIEGE_BARRIER_ENABLED,
    SIEGE_BARRIER_RESERVE,
    RING_RADIUS,
    ATTACK_TURRET_CAP,
    DEFEND_TURRET_SENTINEL,
    FLANK_REPLAN_ROUNDS,
    STEAL_BEFORE_EXPAND,
    STEAL_MAX_DISTANCE,
    FLANK_WHEN_IDLE,
    HARVESTER_RECHECK_ROUNDS,
    IDLE_BEFORE_FLANK,
    BOT_STANDOFF,
    LANE_BARRIER_FIRST,
    LOCK_OWNER_BITS,
    LOCK_OWNER_MASK,
    STANDOFF_BACKOFF,
    STANDOFF_WAIT,
    LAUNCH_RETRY_COOLDOWN,
    SEAT_AWARE_DEFENCE,
    SEAT_B_MENDER_LEASH,
    SEAT_B_MENDS_HARDER,
    SEAT_B_YIELDS_ORE,
    SEAT_B_PREFERS_RANGE,
    SEAT_B_SKIPS_DUEL,
    SEAT_B_TURRET_STEP,
    PLUG_CUT_IMMEDIATELY,
    PLUG_CUT_LEASH,
    LATE_BUILDERS_MINE,
    HOME_TURRET_MAX,
    HOME_TURRET_STEP,
    MENDER_LEASH,
    SEAL_EVERY_DOCTRINE,
    SECOND_MENDER_ALARM,
    SECOND_MENDER_ON_ANY_DAMAGE,
    SIEGE_SEARCH_EVERY,
    SIEGE_SENTINEL_TARGET,
    ECON_EXPAND_BUILDERS,
    SECOND_MENDER_ON_CRITICAL,
    GUARD_HEALS_ON_ANY_DAMAGE,
    MAX_OPENING_BUILDERS,
    CORE_ALARM_MASK,
    SHOOTER_POS_SHIFT,
    SLOT_BUILDER_HEARTBEAT,
    SLOT_BUILDER_TICKET,
    SLOT_CONSTRUCTION_LOCK,
    SLOT_CORE_DAMAGED,
    SLOT_ENEMY_CORE,
    SLOT_OWN_CORE,
    SLOT_SYMMETRY_REJECT_START,
    WALKABLE_BUILDINGS,
)
from utils import (THROW_OFFSETS, is_response, landing_index, pack_enemy,
                   pack_pos, pack_request, pad_owner, passenger_hash,
                   unpack_core, unpack_enemy, unpack_pos, unpack_response,
                   writable_by_builder)

if TYPE_CHECKING:
    from main import Player


# What the harasser breaks first. Harvesters are deliberately absent.
#
# They looked like the best target on this ladder: `vidar`, `vidar_r*` and
# `skadi` all carry the deposit-staleness bug this build fixed in itself, so a
# Harvester of theirs destroyed out of their sight retires that deposit
# permanently rather than for the rounds it takes to rebuild. Measured, adding
# it at top priority costs 3.4pp of mean and 7.2pp of the floor.
#
# The original note was right about why: a tap takes the same Harvester's 2.5 Ti
# a round *onto our belt* and denies it to them at the same time, so destroying
# it trades a resource we were already collecting for a denial we partly had.
# The permanent-denial bug is real and is still exploited -- by the Sentinel,
# which shoots Harvesters first and is not giving up anything to do it.
HARASS_PRIORITY = {EntityType.SPLITTER: 0, EntityType.CONVEYOR: 1}
# Mirror of launcher.KIND_INDEX, for decoding rejection intel.
REJECT_KINDS = {0: EntityType.GUNNER, 1: EntityType.SENTINEL,
                2: EntityType.LAUNCHER}
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
    except Exception as error:
        # An escaping exception of ANY type destroys this unit outright -- the
        # engine tears it down, and it is animated as the bot exploding. That
        # is a whole Builder, its +20% scale and every round of its future work
        # thrown away for a typo, and until this handler existed it happened
        # silently: a NameError in the launch request killed every Builder that
        # asked for a throw, and the only visible symptom was the bank climbing
        # while the unit count fell.
        print(f"BUILDER_CRASH id={ct.get_id()} round={ct.get_current_round()} "
              f"error={error!r}", file=sys.stderr, flush=True)
        return


def _run(p, ct):
    # Store round + 1 so zero remains the unambiguous "no Builder seen" value.
    # All Builders publish the same value; the Core only needs proof that at
    # least one of them was alive during the preceding round. A per-Builder
    # bitmask was tried and is impossible: the engine buffers store writes to
    # the start of the next round, so every Builder in a round reads the same
    # snapshot and ORs its bit onto it, and only the last writer's word lands.
    ct.write_store(SLOT_BUILDER_HEARTBEAT, ct.get_current_round() + 1)
    p.round = ct.get_current_round()
    # Re-entrancy guards are per-turn state: clear them before anything can
    # consult them. See `_build_launcher_breaker_gunner`.
    p.breaking_launcher = False
    if not hasattr(p, "builder_index"):
        p.builder_index = ct.read_store(SLOT_BUILDER_TICKET)
        ct.write_store(SLOT_BUILDER_TICKET, p.builder_index + 1)
        p.w, p.h = ct.get_map_width(), ct.get_map_height()
        p.seen, p.terrain = set(), {}
        p.walls, p.ores, p.solids, p.conveyors = set(), set(), set(), {}
        p.bot_occupied, p.enemy_conveyors = set(), {}
        p.enemy_launchers, p.enemy_launcher_danger = set(), set()
        p.enemy_turrets, p.threat = {}, {}
        p.friendly_launchers = set()
        p.enemy_harvesters = set()
        p.hurt_tiles = {}
        p.building_hp = {}
        p.blocked_by_fire = False
        p.fire_blocked_rounds = 0
        p.launch_retry_round = 0
        p.last_landing_asked = None
        p.last_pad_asked = None
        p.displaced_landings = set()
        p.last_hp = None
        p.threat_signature = None
        p.belt_patrolled = 0
        p.repair_attempts = {}
        p.contested = set()
        p.cut_tiles = set()
        p.countered_sentinels = set()
        p.patrol_target = None
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
        p.field_gunners_built = 0
        p.attack_gunners_built = 0
        p.path_failures = 0
        p.awaiting_launch = 0
        p.launch_origin = None
        p.launch_blocked = False
        p.launch_blocking_launchers = set()
        p.launcher_breakers = set()
        p.next_blocker_gunner_round = 0
        p.build_wait_key, p.build_wait_rounds = None, 0
        p.pending_build = None
        p.rejected_build_sites = set()
        p.deferred_ores = {}
        p.harvester_seen = {}
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
        # Everything past the opening headcount is income, whatever the role
        # arithmetic above would have made it. Both branches key on
        # `builder_index >= economy_builders`, which is the *opening's* way of
        # saying "this one is not a miner" -- read by a Builder spawned on round
        # 250 it says the opposite of what it means, and every expansion Builder
        # would walk to the enemy Core as an attacker instead of laying belt.
        # The expansion exists to answer a tiebreak on titanium collected; a
        # sixth attacker does not collect titanium.
        if LATE_BUILDERS_MINE and p.builder_index >= MAX_OPENING_BUILDERS:
            p.is_launcher_builder = False
            p.is_attacker = False
        # Which seat we are seeing the game from. Units act in ascending global
        # entity id across BOTH teams and ids are handed out in spawn order, so
        # team A's Core is id 1 and team B's is id 2 -- team A therefore wins
        # every tie for the whole match: the race to a tile, the first shot in a
        # turret duel, the heal that lands before the shot. Measured against
        # vidar_r3 over 42 games this is worth 13-8 from seat A and 8-13 from
        # seat B, a 23.8pp swing that has nothing to do with the opponent.
        p.seat_b = ct.get_team() is Team.B
        p.siege_sentinel = None
        p.siege_sentinels_built = 0
        p.last_siege_search_round = -999
        p.sentinel_wrap = []
        p.atlas = (identify_visible(ct, own_core) if own_core is not None
                   else None)
        if p.atlas is not None:
            atlas_tiles = {(x, y) for y in range(p.h) for x in range(p.w)}
            p.walls.update(p.atlas.walls)
            p.ores.update(p.atlas.ores)
            p.seen.update(atlas_tiles)
            p.terrain.update({tile: Environment.EMPTY for tile in atlas_tiles})
            p.terrain.update({tile: Environment.WALL for tile in p.atlas.walls})
            p.terrain.update({tile: Environment.ORE_TITANIUM
                              for tile in p.atlas.ores})
            ct.write_store(SLOT_ENEMY_CORE, pack_enemy(p.atlas.enemy_core, True))
    _sense(p, ct)
    _report_stall(p, ct)
    if p.atlas is None:
        _update_enemy_core_inference(p, ct)
    if p.core is None:
        return
    # A Builder that has proved it cannot path is a permanent +20% on every
    # price the team pays. Retire it before it gets a turn to do anything else.
    if _write_off(p, ct):
        return
    # Before any errand: if the box is one barrier from closing, leave. Nothing
    # this Builder was going to do is worth being worth nothing afterwards.
    if _escape_encirclement(p, ct):
        return
    # And before any errand: do not stand in a firing line. This is deliberately
    # a single check at the top rather than a rule each mechanic remembers to
    # apply -- the harass code had to learn it separately, and every other
    # mechanic would have had to learn it too, one bug at a time. A Builder's
    # tile is a free choice in almost every job it does: which side of a belt it
    # breaks, which neighbour of an ore it mines from, which tile it lays the
    # next conveyor from. Spending 18 HP a round for a choice that was free is
    # the single most common way this bot loses Builders.
    if _leave_the_firing_line(p, ct):
        return
    alarm = ct.read_store(SLOT_CORE_DAMAGED) & CORE_ALARM_MASK
    # A light alarm must not pin the only miner before it has connected a
    # single Harvester. Watched on sweden seat A: chip damage held alarm at 1
    # from round ~75 to the end, the miner healed 4 HP a round for 240 rounds
    # with its Harvester finished but unbelted three tiles away, and the team
    # mined 0 all game — while the winning seat's 750 mined would have paid
    # for every heal many times over. Income first, then mending; a critical
    # Core (alarm 2) still outranks everything.
    if (p.builder_index == 0 and alarm == 1
            and p.network_load == 0 and not p.is_attacker):
        pass
    elif p.builder_index == 0 and alarm:
        # A Core this far gone gets a second mender rather than another turret.
        #
        # One mender restores 4 HP a round for a flat 1 Ti and a Gunner deals 7
        # for 4 Ti, so a lone mender cancels only about two thirds of a single
        # shooter and the Core still dies, slowly. Two restore 8 and out-heal it
        # outright -- and healing is the one answer whose price does not move
        # with cost scale, which matters most exactly when the Core is losing
        # and every turret we have bought has already raised the tax.
        #
        # The evidence for the trigger is the loss ledger: 11 of 12 losses to
        # vidar are Core kills in which our Core ends on 0 and theirs ends on
        # 215-500, while we hold 4-6 Gunners. We are not short of turrets.
        #
        # Alarm level 2 is the Core below CRITICAL_HP, and the leash is the ring
        # Builder's: a miner recalled from across the map arrives after the
        # decision. Below that level the guard still answers with turrets, which
        # is what stops a scratch turning into a permanent mending detail.
        # Trigger on *damage*, not on the Core's alarm level.
        #
        # `alarm` is the Core's own `repair_alert`, and level 2 is the Core below
        # CRITICAL_HP -- 300 of 500. Waiting for it means the second mender only
        # ever arrives for a Core that has already lost two fifths of its life,
        # which on the maps this bot loses is after the game is decided.
        #
        # This is the mechanic that holds this bot's floor, and it was read off
        # the opponent that holds it: vidar_r3 is vidar plus exactly this change
        # -- every non-attacker Builder mends on any Core damage rather than on
        # the death projection -- and it is the hardest matchup on the ladder at
        # 0.512. Its own note makes the case: the losses that decide these games
        # are early rushes, the projection cannot fire before round 40 by
        # construction, and plain damage can. The cost of being wrong is one
        # Builder-turn and 1 Ti, against the permanent +20% that every turret
        # answer costs.
        mend = (_core_is_hurt(p, ct) if SECOND_MENDER_ON_ANY_DAMAGE
                else alarm >= SECOND_MENDER_ALARM)
        leash = (SEAT_B_MENDER_LEASH
                 if (SEAT_B_MENDS_HARDER and getattr(p, "seat_b", False))
                 else MENDER_LEASH)
        if (SECOND_MENDER_ON_CRITICAL and mend
                and _chebyshev(tuple(ct.get_position()), p.core) <= leash):
            _heal_core(p, ct)
            return
        _defend_core(p, ct)
        return
    if p.builder_index == 0 and not alarm:
        # Quiet rounds are when trapping is affordable and patrolling is free.
        # Both are behind the economy: a guard that stops mining to walk a
        # circuit on round 5 costs the opening Harvester, which is worth more
        # than any amount of early vision.
        if _trap_enemy_builder(p, ct):
            return
        if p.network_load >= _network_cap(ct) and _patrol_core(p, ct):
            return
    # The Builder posted at the Core mends it on *any* damage, and does so
    # before it goes back to laying its Launcher ring.
    #
    # The gate this replaces was `alarm >= 2` -- the Core below CRITICAL_HP,
    # 300 of 500 -- on FORTIFY maps only. So the one Builder standing on the
    # Core watched it lose two fifths of its life before lifting a finger, and
    # on a RUSH map never lifted one at all: it walked off to build a ring while
    # the Core died behind it. 90% of this bot's games end in a Core kill and
    # the median loss is round 113, which is the window this sits in.
    #
    # Healing needs no sight of the shooter -- which matters, because a Builder
    # sees r^2=20 and a Sentinel shoots from r^2=32, so the turret killing our
    # Core is routinely invisible to the Builder standing on it -- and it is the
    # most titanium-efficient act in the game: 4 HP for a flat 1 Ti, unaffected
    # by cost scale, against the 4 Ti a Gunner pays for 7 damage and the 3.33 Ti
    # a Sentinel pays for 6. Two menders out-heal a Gunner outright.
    #
    # The leash stays. The measured RUSH finding was about *recalling* a Builder
    # from across the map, where the tempo lost costs more games than the
    # healing saves; this Builder is already at the Core, so the alternative use
    # of its turn is a Launcher, not a march. What is dropped is the FORTIFY
    # restriction and the 200-HP wait, neither of which survives the reason.
    if (p.is_launcher_builder
            and _chebyshev(tuple(ct.get_position()), p.core) <= MENDER_LEASH):
        if GUARD_HEALS_ON_ANY_DAMAGE:
            worth_mending = bool(alarm) or _core_is_hurt(p, ct)
        else:
            worth_mending = alarm >= 2 and p.doctrine == doctrine.FORTIFY
        if worth_mending:
            _heal_core(p, ct)
            return
    # A Builder that has stopped achieving anything goes and does something
    # else, rather than pacing where it stands.
    #
    # Measured over 84 Builders that lived 60 rounds or more: 19% spend their
    # last sixty rounds bouncing between three tiles or fewer while moving in a
    # third of them, and the median Builder spends *all* of its last sixty
    # rounds on its three most-visited tiles. A body that has run out of errands
    # is still charging the team +20% on every price, so the floor for it is not
    # "stand still", it is "go and find something".
    #
    # Deliberately last among the productive branches and first among the
    # fallbacks: everything that can name a real job -- mending, plugging a cut,
    # role work, repairs -- runs ahead of it, so this only fires for a Builder
    # that genuinely has nothing. Menders are exempt by construction, because
    # healing calls `_mark_progress` every round it happens.
    if (FLANK_WHEN_IDLE and not p.is_launcher_builder
            and ct.get_current_round() - p.last_progress_round > IDLE_BEFORE_FLANK
            and ct.get_current_round() - getattr(p, "last_flank_round", -999)
            > FLANK_REPLAN_ROUNDS):
        p.last_flank_round = ct.get_current_round()
        _explore(p, ct)
        return
    # A belt we cut gets its barrier before this Builder does anything else.
    #
    # A cut on its own is rented damage: the tile costs them 3 Ti to relay and a
    # Builder walking the line puts it straight back, so we spent a round of
    # fire for a gap that lasts one. The barrier is what makes the cut stick --
    # 3 Ti and +1% to us, it cannot be built over, and clearing it costs them a
    # round of fire or a turret they would rather aim at us.
    #
    # It cannot be laid the same round: the tile is not empty until the conveyor
    # is gone. So the cut is remembered and this fills it on the very next turn,
    # ahead of every errand. That priority is the point -- the plug used to sit
    # inside `_contest_enemy_logistics`, behind a `network_load >= cap` gate, so
    # a Builder that cut a belt and then found something else to do never came
    # back and left the gap open for them to relay for 3 Ti.
    if PLUG_CUT_IMMEDIATELY and _plug_cut_belt(p, ct):
        return
    # Before any role work: an enemy in front of us outranks whatever errand
    # this Builder was on, wherever on the map that happens to be. Never the
    # economy Builder -- its opening titanium is the harvester budget, and a
    # field Gunner at round 7 is an economy that never starts.
    if p.builder_index != 0 and _engage_with_turret(p, ct):
        return
    if p.is_launcher_builder:
        if not _run_launcher_ring(p, ct):
            return
        # The outer threat-zone seal is worth its titanium only where games
        # run long enough to finish it. When it is unaffordable it yields,
        # and the ring Builder mines instead of freezing in place: the
        # round-1000 tiebreak is delivered titanium, and a second miner is
        # worth more than a Builder holding a pose.
        if ((p.doctrine == doctrine.FORTIFY or SEAL_EVERY_DOCTRINE)
                and not _run_core_seal(p, ct)):
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
    # Then look for the holes vision has not shown us. Ordered after the repair
    # and before any new work: a patrol that pre-empts a known break would walk
    # away from a line it could mend this round.
    if _patrol_belt(p, ct):
        return
    # Contesting their logistics is worth more than extending ours once ours is
    # saturated, and nothing before this point wants the round.
    # Take theirs when theirs is nearer than ours.
    #
    # This used to run only once our own network was saturated, which on a close
    # map is far too late: a Harvester of theirs four tiles away is cheaper to
    # tap than a fresh deposit of ours fifteen tiles away is to belt, and on the
    # tight maps -- vault, duel, showdown -- their line is often the nearest
    # economy on the board. Tapping costs them nothing they can see and moves
    # 2.5 Ti a round onto our belt; laying our own costs a Builder the walk, the
    # conveyor chain and the Harvester.
    #
    # The comparison is the gate: contest early only when their logistics really
    # is the closer job, otherwise keep the old saturation rule so this never
    # pre-empts an expansion that was nearer all along.
    saturated = p.network_load >= _network_cap(ct)
    if (saturated or _enemy_logistics_is_nearer(p, ct)) \
            and _contest_enemy_logistics(p, ct):
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
        # Ours are remembered too, and as opportunities rather than hazards:
        # the path planner treats a friendly pad as a one-round hop of up to
        # r^2=26, which is the fastest movement any Builder has.
        if not enemy and kind == EntityType.LAUNCHER:
            p.friendly_launchers.add(key)
        else:
            p.friendly_launchers.discard(key)
        if enemy and kind in (EntityType.GUNNER, EntityType.SENTINEL):
            # Remember the facing too: a Gunner threatens one ray, and which
            # ray it is decides whether a detour of one tile is enough.
            p.enemy_turrets[key] = (kind, ct.get_direction(bid))
        else:
            p.enemy_turrets.pop(key, None)
        if kind == EntityType.CORE and enemy:
            ct.write_store(SLOT_ENEMY_CORE, pack_enemy(ct.get_position(bid), True))
        if enemy and kind in HARASS_PRIORITY:
            p.enemy_economy[key] = kind
        else:
            p.enemy_economy.pop(key, None)
        # Tracked separately from enemy_economy: a Harvester is not a harass
        # target -- breaking it gains nothing a tap does not gain better -- but
        # it is exactly what the tap needs to find.
        if enemy and kind == EntityType.HARVESTER:
            p.enemy_harvesters.add(key)
        else:
            p.enemy_harvesters.discard(key)
        # When we last had eyes on a Harvester of ours. `_pick` refuses an ore
        # tile that is in `p.solids`, and `_sense` can only clear that flag for
        # tiles the Builder can currently see -- so a Harvester shot out while
        # nobody was looking left its deposit marked "taken" for the rest of the
        # game and was never rebuilt. See HARVESTER_RECHECK_ROUNDS.
        if not enemy and kind == EntityType.HARVESTER:
            p.harvester_seen[key] = ct.get_current_round()
        if kind == EntityType.CORE:
            if ct.get_team(bid) == ct.get_team():
                p.core = tuple(ct.get_position(bid))
            p.solids.add(key)
        elif not enemy and kind != EntityType.BUILDER_BOT:
            # Every building of ours is a fire detector; see _note_incoming_fire.
            p.building_hp.setdefault(key, ct.get_hp(bid))
        elif kind in WALKABLE_BUILDINGS:
            p.solids.discard(key)
            if ct.get_team(bid) == ct.get_team():
                p.building_hp.setdefault(key, ct.get_hp(bid))
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
    _note_incoming_fire(p, ct)
    _refresh_threat(p, ct)
    p.launcher_breakers.intersection_update(p.enemy_launchers)
    if (p.launch_blocked and p.launch_blocking_launchers
            and not p.launch_blocking_launchers & p.enemy_launchers):
        p.launch_blocked = False
        p.launch_blocking_launchers.clear()


def _note_incoming_fire(p, ct):
    """Remember tiles where we were shot, including by things we cannot see.

    This is the gap that kills Builders. A Builder sees to r^2=20; a Sentinel
    shoots to r^2=32 and its line is never blocked. So the turret that kills us
    is routinely outside our own vision, is never entered in `enemy_turrets`,
    and the threat map that pathfinding consults is empty exactly where the
    danger is. No amount of care about *known* firing lines helps against a
    shooter we are structurally unable to see.

    Damage is the sensor we do have. Losing HP on a tile proves that tile is
    covered, whatever we can see from it, so the tile is remembered and every
    later route and build site treats it as lethal ground. It is a coarse
    signal -- one tile per hit, no idea of the ray -- but it is evidence rather
    than inference, and it accumulates across the game.

    Charged at Sentinel damage deliberately. Being wrong high costs a detour;
    being wrong low costs the Builder.
    """
    hurt = False
    hp = ct.get_hp()
    last = getattr(p, "last_hp", None)
    p.last_hp = hp
    if last is not None and hp < last:
        p.hurt_tiles[tuple(ct.get_position())] = SENTINEL_DAMAGE
        hurt = True

    # Our buildings are sensors too, and better ones than the Builders: there
    # are more of them, they are spread across the map, and a conveyor sitting
    # in a lane reports that lane every single round without having to walk
    # into it. A belt tile losing HP with no visible shooter is proof the tile
    # is covered, and it costs 3 Ti to learn instead of a Builder.
    #
    # Only when we cannot see what did it. If a known turret already covers the
    # tile the threat map has it, and recording it twice would double its
    # weight in the survival arithmetic.
    seen_now = {}
    for tile, was in list(p.building_hp.items()):
        position = Position(*tile)
        if not ct.is_in_vision(position):
            seen_now[tile] = was
            continue
        building = ct.get_tile_building_id(position)
        if building is None or ct.get_team(building) != ct.get_team():
            continue
        now = ct.get_hp(building)
        seen_now[tile] = now
        if now < was and not _threat_at(p, tile):
            p.hurt_tiles[tile] = SENTINEL_DAMAGE
            hurt = True
    p.building_hp = seen_now

    if hurt:
        # Force the threat map to be rebuilt with the new tiles folded in.
        p.threat_signature = None


def _refresh_threat(p, ct):
    """Every tile a remembered enemy turret can shoot, and what it costs to be there.

    Turrets do not move, so remembering them is sound: a Gunner seen once keeps
    threatening its ray whether or not anything of ours can currently see it.
    Only a turret we can see to be gone is forgotten, which `_sense` does by
    dropping the key when the tile is empty.

    A Gunner threatens the tiles down its facing; a Sentinel threatens its whole
    pattern and cannot be blocked. `get_attackable_tiles_from` gives the raw
    pattern for a hypothetical turret, which is exactly the question -- it
    ignores ammunition and cooldown, and a threat map should: an empty magazine
    is one convert_ammo away.

    The map is rebuilt only when the turret set changes. It is a few hundred
    tiles and the CPU budget is 10 ms a round for every unit.
    """
    signature = frozenset(p.enemy_turrets.items())
    if getattr(p, "threat_signature", None) == signature:
        return
    p.threat_signature = signature
    threat = dict(p.hurt_tiles)
    for spot, (kind, facing) in p.enemy_turrets.items():
        try:
            tiles = ct.get_attackable_tiles_from(Position(*spot), facing, kind)
        except GameError:
            continue
        damage = (SENTINEL_DAMAGE if kind == EntityType.SENTINEL
                  else GUNNER_DAMAGE)
        for tile in tiles:
            key = tuple(tile)
            # A tile two turrets both cover is twice as lethal, and the
            # attacker's survival check has to see that.
            threat[key] = threat.get(key, 0) + damage
    p.threat = threat


def _threat_at(p, tile):
    return getattr(p, "threat", {}).get(tuple(tile), 0)


def _survives_path(p, ct, path):
    """Would we live to the end of this path, walking it a tile a round?

    The attacker dies too often because it plans a route to the enemy Core and
    then walks it regardless of what is aimed down it. A path is a schedule --
    one tile per round -- so the damage it will take is simply the sum over its
    first PATH_LOOKAHEAD steps of whatever covers each tile. Compare that with
    the HP actually on the unit, keep a margin of one Gunner shot for the turret
    we have not seen, and if it does not survive, the caller re-plans with those
    tiles blocked.

    Looking a fixed distance ahead rather than the whole way is deliberate: the
    far end of a long path is mostly unexplored, its threat estimate is empty
    by construction, and re-planning against an empty estimate every round
    burns CPU to no purpose.
    """
    if not path:
        return True
    budget = ct.get_hp() - PATH_SAFETY_MARGIN
    taken = 0
    for tile in path[:PATH_LOOKAHEAD]:
        taken += _threat_at(p, tile)
        if taken >= budget:
            return False
    return True


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
    # An ore tile we believe carries one of our Harvesters is claimed only while
    # that belief is fresh. Measured over 414 games, live Harvesters ran 1.80 at
    # round 50 down to 1.42 at round 500 in games this bot won, and 1.69 down to
    # 0.24 in games it lost -- an economy that never grows and, when losing,
    # collapses to nothing, while the vidar line holds about 2.0 throughout.
    # The cause is the staleness above, not the caps: NETWORK_CAP_EARLY 6 was
    # measured inert because permission was never the binding constraint.
    #
    # Re-targeting a stale site is cheap even when the Harvester turns out to be
    # alive: `_goto` recognises it ("found existing harvester") and closes the
    # task without spending anything.
    stale = {ore for ore, seen in p.harvester_seen.items()
             if ct.get_current_round() - seen > HARVESTER_RECHECK_ROUNDS}
    claimed |= (p.ores & p.solids) - stale
    claimed |= {ore for ore, expires in p.deferred_ores.items()
                if expires >= ct.get_current_round()}
    p.deferred_ores = {ore: expires for ore, expires in p.deferred_ores.items()
                       if expires >= ct.get_current_round()}
    me, best = tuple(ct.get_position()), None
    candidates = sorted(
        p.ores - claimed,
        key=lambda ore: max(abs(ore[0] - me[0]), abs(ore[1] - me[1])),
    )
    # Seat B does not race for the contested deposit.
    #
    # Units act in ascending entity id across both teams, so team A moves first
    # every round for the whole match and wins every tie -- including the race
    # to the deposit both miners can see. Measured against skadi: eleven of the
    # 21 maps split exactly 1-2, won from seat A and lost from seat B, which is
    # the single largest term left in this bot's floor.
    #
    # Arriving second at a deposit is worse than arriving first at the next one,
    # because the loser has walked the distance and still has to walk again. So
    # from seat B the nearest deposit is skipped when there is another to take,
    # which turns a race we lose into a walk we own.
    if (SEAT_B_YIELDS_ORE and getattr(p, "seat_b", False)
            and len(candidates) > 1):
        candidates = candidates[1:]
    # Choose the deposit by what it costs to *deliver*, not by how far it is to
    # walk to.
    #
    # The old loop sorted by travel distance and then broke on the first
    # routable candidate, so `len(route)` -- the belt -- was computed and never
    # compared, exactly as the comment it replaced admitted ("route length
    # breaks ties ... for later score tuning"). A deposit three tiles away
    # behind a wall, needing fifteen conveyors, beat one five tiles away needing
    # four.
    #
    # A conveyor is 3 Ti and, measured with get_scale_percent, +1 on the team's
    # cost scale. Forty of them is about 120 Ti and a +40% tax on every price
    # afterwards. That is affordable in a 600-round game and ruinous in a
    # 150-round one, and the ladder is full of the latter: The Flotte
    # Experience v38 swept us 0-5 on 2026-08-08 in games of 133-172 rounds
    # while laying 8-17 conveyors against our 28-47. On hive we laid 36, built
    # one Gunner at round 114, dealt zero damage and died on 133.
    #
    # Bounded by work, so the extra searching cannot cost a turn: at most
    # BELT_SCORE_CANDIDATES deposits are priced, and the list is still ordered
    # nearest-first, so those are the ones worth pricing.
    priced = []
    for ore in candidates[:BELT_SCORE_CANDIDATES]:
        route = _route(p, ore)
        travel = _distance(p, me, _adjacent(p, ore))
        if route is None or travel is None:
            continue
        priced.append((len(route) * BELT_TILE_WEIGHT + travel,
                       travel, len(route), ore, route))
    if priced:
        priced.sort()
        _, travel, _, ore, route = priced[0]
        best = (travel, len(route), ore, route)
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
    """Shortest cardinal line to Core or this Builder's unsaturated network.

    Routed around every known enemy firing line, not merely repaired after it.
    A conveyor is 3 Ti and +1% and dies to a single Gunner shot, and the tile
    does not get safer for being rebuilt: heimdall's bridge trace had one belt
    tile inside a Gunner's ray rebuilt 22 times, 66 Ti and 22% of compounding
    scale, for an income of 10 titanium in 1000 rounds. A hole that keeps
    reappearing is not damage -- it is a tile the enemy owns, and the line has
    to go somewhere else.

    A longer safe route beats a short dead one, so the threat tiles are blocked
    rather than merely penalised. If that leaves no route at all the caller
    falls back and this Builder mines elsewhere, which is the correct answer:
    ore that can only be delivered through a firing line is not ore we can bank.
    """
    joinable = p.network_tiles if p.network_load < 4 else set()
    blocked = (p.walls | p.foot | (p.ores - {ore}) | p.solids
               | p.rejected_build_sites
               | _launcher_hazards(p)
               | (set(p.conveyors) - joinable))
    if AVOID_THREAT_FOR_LOGISTICS:
        blocked = blocked | (set(getattr(p, "threat", ())) - {ore})
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
    # A tile inside a known firing line, or one that has already eaten
    # REPAIR_ATTEMPT_LIMIT rebuilds, is not damage -- it is ground the enemy
    # holds. Abandon the tile, drop the whole line's plan, and let the next
    # _route pass find a way round the turret instead of feeding it.
    attempts = p.repair_attempts.get(tile, 0)
    if attempts >= REPAIR_ATTEMPT_LIMIT or _threat_at(p, tile):
        _abandon_belt_tile(p, ct, tile)
        return True
    facing = p.network_plan[tile]
    target = Position(*tile)
    if _cardinal_distance(me, tile) != 1:
        _move_cardinal_adjacent(p, ct, tile)
        return True
    if ct.can_build_conveyor(target, facing):
        ct.build_conveyor(target, facing)
        _mark_progress(p, ct, "repaired conveyor", tile)
        p.conveyors[tile] = facing
        p.repair_attempts[tile] = attempts + 1
        return True
    if _build_failure(p, ct, tile, "conveyor repair", ct.get_conveyor_cost()):
        # Something else stands there now; the line has to be re-planned
        # rather than patched.
        del p.network_plan[tile]
    return True


def _abandon_belt_tile(p, ct, tile):
    """Write off a belt tile the enemy controls, and re-plan the line around it.

    Rebuilding into a seat a turret covers is the single most expensive mistake
    in this lineage's history. The tile is added to the rejected set so no later
    route proposes it again, and the surviving plan is torn down back to the
    Core -- a line with a permanent hole delivers nothing, so keeping the rest
    of it standing only pays scale on conveyors that carry no titanium.
    """
    p.rejected_build_sites.add(tile)
    p.network_plan.pop(tile, None)
    p.repair_attempts.pop(tile, None)
    p.conveyors.pop(tile, None)
    p.network_tiles.discard(tile)
    _mark_progress(p, ct, "abandoned belt tile under fire", tile)
    # Re-plan from scratch on the next scouting pass rather than patching.
    p.task, p.route, p.route_i = None, [], 0
    p.phase = "scout"


def _patrol_belt(p, ct):
    """Walk the line every so often to find cuts vision has not shown us.

    A Builder only sees holes in tiles it happens to be looking at, and the
    miner spends its life at the far end of the belt next to the ore. Enemies
    cut lines in the middle, where nothing of ours is standing, and a cut belt
    is silent: income simply stops, and the bot goes on building Harvesters
    that feed a dead end.

    So once every BELT_PATROL_ROUNDS the miner walks back down its own line.
    The walk is the sensor -- vision does the rest, and `_repair_network` picks
    up whatever the patrol exposes on the following round.
    """
    if not p.network_plan:
        return False
    if ct.get_current_round() - p.belt_patrolled < BELT_PATROL_ROUNDS:
        return False
    unseen = [tile for tile in p.network_plan
              if not ct.is_in_vision(Position(*tile))]
    if not unseen:
        p.belt_patrolled = ct.get_current_round()
        return False
    me = tuple(ct.get_position())
    target = min(unseen, key=lambda tile: _cardinal_distance(me, tile))
    if _cardinal_distance(me, target) <= 1:
        p.belt_patrolled = ct.get_current_round()
        return False
    _step(p, ct, Position(*target), False)
    return True


def _enemy_logistics_is_nearer(p, ct):
    """Is an enemy Harvester or belt tile closer than our own next deposit?

    Cheap and deliberately crude: Chebyshev on remembered positions, no routing.
    A wrong answer costs one Builder-turn, and the branch it guards re-checks
    everything properly.
    """
    if not STEAL_BEFORE_EXPAND:
        return False
    me = tuple(ct.get_position())
    theirs = [t for t in p.enemy_harvesters] + [t for t in p.enemy_conveyors]
    if not theirs:
        return False
    near_theirs = min(_cardinal_distance(me, t) for t in theirs)
    if near_theirs > STEAL_MAX_DISTANCE:
        return False
    free_ore = p.ores - p.solids - set(p.conveyors)
    near_ours = (min(_cardinal_distance(me, o) for o in free_ore)
                 if free_ore else 999)
    return near_theirs < near_ours


def _contest_enemy_logistics(p, ct):
    """Tap a Harvester of theirs into a belt of ours, and cut what feeds their Core.

    Both halves are new to this lineage, which has always treated the enemy's
    economy as something to raid rather than something to take.

    A Harvester outputs one whole stack round-robin to whichever of its four
    cardinal neighbours was used least recently, and it does not care whose
    conveyor that is. So a conveyor of ours laid against an enemy Harvester
    takes a share of its output on a fixed rotation, permanently, for 3 Ti. They
    cannot see it happening in their own titanium count -- the stack simply
    never arrives -- and removing it means removing their own Harvester's
    neighbour.

    Cutting is the cheaper half. A conveyor is 30 HP and a Builder does 2 damage
    a hit for 2 Ti, so breaking one costs 30 Ti of shots -- but it is *their*
    trunk, and every round it stays down is a stack that never reaches their
    Core. Cut the tile nearest their Core: the further down the line the cut,
    the more of their belt is stranded behind it.
    """
    if not (STEAL_ENEMY_HARVESTER or CUT_ENEMY_BELT):
        return False
    me = tuple(ct.get_position())
    if STEAL_ENEMY_HARVESTER and _tap_enemy_harvester(p, ct, me):
        return True
    if CUT_ENEMY_BELT and _cut_enemy_belt(p, ct, me):
        return True
    return False


def _tap_enemy_harvester(p, ct, me):
    """Lay one of our conveyors against an enemy Harvester to steal its rotation."""
    harvesters = [tile for tile in p.enemy_harvesters
                  if _distance_sq(tile, me) <= CONTEST_MAX_DISTANCE_SQ]
    if not harvesters:
        return False
    for harvester in sorted(harvesters,
                            key=lambda t: (_cardinal_distance(me, t), t)):
        for dx, dy in D4_DELTAS:
            spot = (harvester[0] + dx, harvester[1] + dy)
            if not _inside(p, spot) or spot in p.walls or spot in p.ores:
                continue
            if spot in p.solids or spot in p.conveyors:
                continue
            if spot in p.enemy_conveyors or _threat_at(p, spot):
                continue
            if spot in p.contested:
                continue
            # Point the tap back towards our own side; the rest of the line is
            # ordinary belt the miner will extend on a later pass.
            facing = FACING[(_sign(p.core[0] - spot[0]), 0)] if (
                abs(p.core[0] - spot[0]) >= abs(p.core[1] - spot[1])
                and p.core[0] != spot[0]
            ) else FACING[(0, _sign(p.core[1] - spot[1]))]
            if _cardinal_distance(me, spot) != 1:
                _move_cardinal_adjacent(p, ct, spot)
                return True
            target = Position(*spot)
            if ct.can_build_conveyor(target, facing):
                ct.build_conveyor(target, facing)
                _mark_progress(p, ct, "tapped enemy harvester", spot)
                p.conveyors[spot] = facing
                p.contested.add(spot)
                return True
    return False


def _cut_enemy_belt(p, ct, me):
    """Break the enemy conveyor nearest their Core, then wall the gap.

    Cutting alone is rented damage: the tile is 3 Ti for them to relay, and a
    Builder of theirs walking the line puts it straight back, so we pay 30 Ti of
    Builder fire for a gap that lasts a round. Dropping our own barrier into the
    hole is what makes the cut stick -- it is 3 Ti and +1% to us, it cannot be
    built over, and clearing it costs them another 30 Ti of fire or a turret
    they would rather point at us. Their belt stays severed until they spend
    more than we did, which is the whole trade.

    The barrier also has to be built the round *after* the cut: the tile is not
    empty until the conveyor is gone, so this remembers the hole it made and
    fills it on a later pass.
    """
    packed = ct.read_store(SLOT_ENEMY_CORE)
    if packed == 0:
        return False
    enemy_core, _ = unpack_enemy(packed)

    # Plug a hole we cut earlier before opening a new one: an unplugged cut is
    # the version of this that does not pay.
    for tile in sorted(p.cut_tiles, key=lambda t: _cardinal_distance(me, t)):
        if _cardinal_distance(me, tile) != 1:
            continue
        position = Position(*tile)
        if ct.is_in_vision(position) and ct.get_tile_building_id(position):
            p.cut_tiles.discard(tile)
            continue
        if ct.get_global_resources() < ct.get_barrier_cost():
            break
        if ct.can_build_barrier(position):
            ct.build_barrier(position)
            _mark_progress(p, ct, "walled a cut belt", tile)
            p.solids.add(tile)
            p.cut_tiles.discard(tile)
            return True

    reachable = [tile for tile in p.enemy_conveyors
                 if _cardinal_distance(me, tile) == 1]
    if not reachable:
        return False
    tile = min(reachable, key=lambda t: (_distance_sq(t, enemy_core), t))
    target = Position(*tile)
    if ct.can_fire(target):
        ct.fire(target)
        _mark_progress(p, ct, "cut enemy belt", tile)
        p.cut_tiles.add(tile)
        return True
    return False


def _plug_cut_belt(p, ct):
    """Barrier a conveyor tile this team has just cut, before any other errand.

    Returns True when the turn has been spent. Walks back to the hole if it is
    close, because a Builder that cuts and wanders has paid for nothing; the
    leash keeps that from turning into a march across the map.
    """
    if not p.cut_tiles:
        return False
    me = tuple(ct.get_position())
    for tile in sorted(p.cut_tiles, key=lambda t: _cardinal_distance(me, t)):
        position = Position(*tile)
        # Already refilled by them, or never emptied: stop tracking it.
        if ct.is_in_vision(position) and ct.get_tile_building_id(position):
            p.cut_tiles.discard(tile)
            continue
        if ct.get_global_resources() < ct.get_barrier_cost():
            return False
        if _cardinal_distance(me, tile) == 1:
            if ct.can_build_barrier(position):
                ct.build_barrier(position)
                _mark_progress(p, ct, "walled a cut belt", tile)
                p.solids.add(tile)
                p.cut_tiles.discard(tile)
                return True
            # Something else took the tile; it is not ours to plug.
            p.cut_tiles.discard(tile)
            continue
        if _cardinal_distance(me, tile) <= PLUG_CUT_LEASH:
            return _step(p, ct, position, False)
        p.cut_tiles.discard(tile)
    return False


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
    return value & LOCK_OWNER_MASK, value >> LOCK_OWNER_BITS


def _refresh_construction_lock(p, ct):
    """Claim the shared build lock.

    The owner field was two bits wide, which holds three Builders. `owner` is
    `builder_index + 1`, so the fourth Builder wrote 4, `4 & 0b11` is 0, and 0
    is the value that means "nobody owns this lock". That Builder therefore
    never matched its own claim, rewrote the slot with a fresh expiry every
    round, and -- because units act in ascending entity id -- did so *after* the
    early miner had claimed it, erasing the claim of the one Builder actually
    laying belt, which then waited for a lock it could never be granted.

    Three Builders is what the opening has, so this was unreachable until
    ECON_EXPAND_BUILDERS was turned on and index 3 started existing. Four bits
    hold fifteen owners, which is past ECON_MAX_TOTAL_BUILDERS.
    """
    ct.write_store(
        SLOT_CONSTRUCTION_LOCK,
        ((p.builder_index + 1) & LOCK_OWNER_MASK)
        | ((ct.get_current_round() + 20) << LOCK_OWNER_BITS))


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
    if DEBUG_BUILD and target is not None and action.startswith(("built", "wall",
                                                                "repaired",
                                                                "tapped",
                                                                "countered",
                                                                "turret")):
        _log_build_exposure(p, ct, action, target)
    p.last_progress_round = ct.get_current_round()
    p.last_progress = f"{action} {target}" if target is not None else action
    p.stall_reported = False
    p.pending_build = None
    p.build_wait_key, p.build_wait_rounds = None, 0


def _log_build_exposure(p, ct, action, target):
    """Record whether a building went up in a firing line, and if we could tell.

    Three separate questions, and the benchmark exists because conflating them
    is how "it still builds in the line of fire" stayed unfixed:

      knew=1        the threat map already had this tile. An outright bug: the
                    information was in hand and the placement ignored it.
      visible=1     an enemy turret covering this tile is in vision *right now*
                    and is not in the threat map. A sensing bug -- `_sense`
                    should have recorded it before the build was chosen.
      remembered=1  we have seen that turret at some earlier point in the game.
                    A memory bug: it was recorded and then lost or overwritten.

    Anything with all three at 0 is not a bug at all -- it is a turret nobody
    on our team has ever laid eyes on, and no amount of care could have avoided
    the tile.
    """
    tile = tuple(target)
    knew = 1 if _threat_at(p, tile) else 0
    visible = 0
    for entity_id in ct.get_nearby_entities():
        if ct.get_team(entity_id) == ct.get_team():
            continue
        kind = ct.get_entity_type(entity_id)
        if kind not in (EntityType.GUNNER, EntityType.SENTINEL):
            continue
        try:
            covered = ct.get_attackable_tiles_from(
                ct.get_position(entity_id), ct.get_direction(entity_id), kind)
        except GameError:
            continue
        if any(tuple(t) == tile for t in covered):
            visible = 1
            break
    remembered = 1 if any(
        tile in _turret_cover(ct, spot, kind, facing)
        for spot, (kind, facing) in p.enemy_turrets.items()) else 0
    print(f"BUILDX r={ct.get_current_round()} id={ct.get_id()} "
          f"action={action.replace(' ', '_')} tile={tile[0]},{tile[1]} "
          f"knew={knew} visible={visible} remembered={remembered}",
          file=sys.stderr, flush=True)


def _turret_cover(ct, spot, kind, facing):
    try:
        return {tuple(t) for t in ct.get_attackable_tiles_from(
            Position(*spot), facing, kind)}
    except GameError:
        return set()


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
            # Wait, do not re-ask. Under the old protocol re-announcing every
            # round was free insurance against a pad that had not noticed; now
            # the request persists in the slot until it is served or refused,
            # so re-asking only overwrites it -- and `_announce_launch` re-runs
            # `_choose_landing`, which can name a *different* tile each round as
            # the threat map shifts. Traced: builder 36 asked for (7,16) on both
            # r23 and r24, and had asked for (10,15) on r22 -- a change of mind
            # mid-negotiation rather than a retry.
            #
            # The counter still runs down, so a pad that has genuinely vanished
            # releases the Builder rather than holding it forever.
            adjacent = _adjacent_visible_launcher(ct, target)
            if adjacent is not None:
                # Waiting, not re-asking: the request is already in the slot.
                p.awaiting_launch -= 1
                return True
            # The requested Launcher disappeared before servicing us.
            p.awaiting_launch = 0
            p.launch_origin = None

    # A hop is a real edge in the route, but it costs a round of comms: the
    # request is written now and only becomes readable next turn. So the
    # announcement is made while still walking *towards* the pickup tile, one
    # step early, and the throw is ready the round we arrive. Announcing on
    # arrival instead wastes a round standing next to the pad -- usually
    # harmless, occasionally the round that gets the Builder killed.
    # Only while not already waiting on a throw. Re-announcing every round
    # re-opens the negotiation from scratch: each refusal teaches the Builder a
    # new lane, it picks a different landing, and the pad refuses that one too.
    # Measured, that loop took launch requests from 286 to 5,770 a game and the
    # serve rate from 35% to 6%. One request, then wait for the answer.
    # One request, then wait for the answer. A store write is not readable
    # until the next turn, so re-asking every round re-opens the negotiation
    # before any reply can exist -- traced: builder 36 asked for (8,16) on r20
    # and again on r21, before the r21 refusal was written. That loop took
    # launch requests from 286 to 5,770 a game and the serve rate from 35% to
    # 6.5%. `launch_retry_round` also covers the slot-collision case: two
    # Builders sharing a slot overwrite each other, and the loser simply waits
    # a round and asks again rather than hammering.
    path = (None if (p.awaiting_launch
                     or ct.get_current_round() < p.launch_retry_round) else
            _safe_path(p, ct, tuple(source), tuple(target), exact))
    if path is not None and len(path) > 2:
        for index in range(min(2, len(path) - 1)):
            if _chebyshev(path[index], path[index + 1]) <= 1:
                continue
            pad = _pad_serving(p, path[index])
            if pad is not None and index == 1:
                # We step onto the pickup tile this round and want the throw
                # available next round: announce before moving.
                _request_launch(p, ct, Position(*path[index + 1]),
                                Position(*pad))
            break

    nxt = _bfs_step(p, tuple(source), tuple(target), exact, ct=ct)
    if nxt is not None and _chebyshev(tuple(source), nxt) > 1:
        # The route's next step is a throw, not a walk. A hop edge is one BFS
        # step because it is one round, but it is not a move the Builder can
        # make itself -- it has to ask the pad. Announcing here is what turns
        # the planned hop into the real one; without it the mover finds no
        # legal direction, books a path failure, and forty of those retire the
        # Builder. That is exactly how this bot went from nine units to one.
        adjacent = _adjacent_visible_launcher(ct, target)
        if adjacent is not None and _request_launch(p, ct, target,
                                                    adjacent[1]):
            p.path_failures = 0
            return True
        # The pad is not actually usable this round; fall back to walking.
        nxt = _bfs_step(p, tuple(source), tuple(target), exact,
                        ct=ct, allow_hops=False)
    if nxt:
        # Cardinal only: a diagonal is not a legal Builder move in 2.3.3, and
        # this loop silently did nothing whenever the path asked for one.
        for direction in D8:
            if source.add(direction) == Position(*nxt) and ct.can_move(direction):
                ct.move(direction)
                _mark_progress(p, ct, "moved", nxt)
                p.path_failures = 0
                return True

    if getattr(p, "blocked_by_fire", False):
        # There is a route; it just runs through fire we would not survive.
        # Not a pathing failure -- counting it as one spends titanium on an
        # escape Launcher aimed at the same lethal tile, and forty of them
        # retire the Builder outright.
        #
        # Nor is it a reason to stand still. Waiting out a Sentinel is waiting
        # for something that does not move, does not run out of ammunition
        # while their Core lives, and cannot rotate to stop covering the tile.
        # So: back off far enough that the line cannot reach, and if the errand
        # is still worth doing after a few rounds of that, go *over* the line
        # instead of through it. A Launcher throws to r^2=26 and the landing
        # tile is chosen clear of fire, which is precisely the way past a lane
        # that cannot be walked.
        p.fire_blocked_rounds += 1
        if (allow_launcher and not p.launch_blocked
                and p.fire_blocked_rounds >= FIRE_BLOCK_LAUNCH_ROUNDS
                and _launch_beats_walking(p, ct, target)
                and _build_escape_launcher(p, ct, target)):
            return True
        _retreat_from_fire(p, ct)
        return True
    p.fire_blocked_rounds = 0

    goals = {tuple(target)} if exact else _adjacent(p, tuple(target))
    if tuple(source) in goals:
        p.path_failures = 0
        return False

    # Before treating this as a failed route: is the only thing in the way
    # another *bot*? Bots move; walls do not, and the escalation for each is
    # different. Traced from the pacing benchmark -- our Builders park against
    # enemy Builders in corridors, and because the enemy often paces back and
    # forth the route flickers between clear and blocked, so nothing ever
    # settles and both bodies are removed from the game.
    #
    # The ladder here is deliberately the human one: hold still and let them
    # pass, then give ground and see whether they take it, and only then decide
    # the tile is theirs and go around. Holding first is what makes it cheap --
    # most blockages clear on their own within a round or two, and a Builder
    # that immediately reroutes around a passer-by pays for a detour it did not
    # need.
    if _bot_standoff(p, ct, target, exact):
        return True
    p.path_failures += 1
    # Going over the obstacle is tried before shooting through it. Both cost
    # 20 Ti, but the throw resolves in one round and puts the Builder past
    # everything in between, where a turret has to break a 30 HP Launcher or
    # kill a Builder first -- several rounds during which ours stands still in
    # a contested spot, which is where it gets shot. Shooting is what is left
    # when the throw is unavailable: no pad site, a rejection outstanding, or
    # the relay already refused.
    if (allow_launcher and not launch_rejected and not p.launch_blocked
            and p.path_failures >= PATH_FAILURES_BEFORE_LAUNCHER
            and _build_escape_launcher(p, ct, target)):
        return True
    # An enemy Launcher across the path is a target, not an obstacle -- but
    # only the ones the route actually runs into.
    blocking = _blocking_launchers(p, tuple(source), tuple(target), exact)
    if blocking and _build_launcher_breaker_gunner(
            p, ct, blocking=blocking, route=target):
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


def _bot_standoff(p, ct, target, exact):
    """Wait out, then give way to, then route around another bot in the way.

    Returns True when the turn has been spent on the standoff.

    Only runs when the route is blocked *by bots alone* -- if the same search
    with bots treated as passable also fails, the obstruction is terrain and
    this has nothing to say about it.
    """
    if not BOT_STANDOFF:
        return False
    source = tuple(ct.get_position())
    goals = {tuple(target)} if exact else _adjacent(p, tuple(target))
    dist, _ = _travel(p, source, goals=goals, ignore_bots=True)
    if not (goals & set(dist)):
        # Terrain blocks it too; not a standoff.
        p.standoff_rounds = 0
        return False
    p.standoff_rounds = getattr(p, "standoff_rounds", 0) + 1
    # 1. Hold. Most blockages are a body walking past.
    if p.standoff_rounds <= STANDOFF_WAIT:
        return True
    # 2. Give ground, and see whether they take it. A step away is also a step
    #    out of whatever ray they were standing in.
    if p.standoff_rounds <= STANDOFF_WAIT + STANDOFF_BACKOFF:
        blockers = [t for t in p.bot_occupied
                    if _cardinal_distance(source, t) <= 2]
        if blockers:
            away = min(blockers, key=lambda t: _cardinal_distance(source, t))
            best, best_score = None, None
            for direction in D8:
                spot = tuple(ct.get_position().add(direction))
                if spot in _no_go(p, source) or not ct.can_move(direction):
                    continue
                score = (-_distance_sq(spot, away), _distance_sq(spot, tuple(target)))
                if best_score is None or score < best_score:
                    best, best_score = direction, score
            if best is not None:
                ct.move(best)
                return True
    # 3. They are not moving and neither of us is giving way. Their tile is
    #    theirs: write it off for a while and let the router find another way.
    for tile in list(p.bot_occupied):
        if _cardinal_distance(source, tile) <= 2:
            p.solids.add(tile)
            p.deferred_ores.pop(tile, None)
    p.standoff_rounds = 0
    return False


def _build_escape_launcher(p, ct, target):
    """Build a temporary ferry after repeated failures to find a walkable path."""
    launchers = _visible_friendly_launchers(ct)
    if launchers:
        adjacent = _adjacent_visible_launcher(ct, target, launchers)
        if adjacent is None:
            return False
        return _request_launch(p, ct, target, adjacent[1])

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
            # Refused, not ranked. Measured: this function alone was 29 of the
            # 50 buildings placed into a firing line, because it ranked purely
            # on closeness to the target. A Launcher in a Sentinel's lane is
            # gone in two shots along with the relay it was built to provide,
            # which strands the passenger it was built for.
            if _threat_at(p, spot):
                continue
            candidates.append((position.distance_squared(target),
                               spot, position))
    if not candidates:
        _plan_failed(
            p, ct, "build escape launcher", target,
            "no adjacent non-ore site with a safe legal landing",
        )
        return False

    _, spot, position = min(candidates)
    ct.build_launcher(position)
    _mark_progress(p, ct, "built escape launcher", spot)
    p.solids.add(spot)
    p.path_failures = 0
    _request_launch(p, ct, target, position)
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
    protected_lanes = _friendly_turret_lanes(ct, p)
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
    _spar_turret(ct, position, facing)
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


def _request_launch(p, ct, target, launcher_position):
    """Claim the slot and name a landing. The only writer of a request.

    Two rules decide whether a request may be written at all:

    * **The slot must be empty or hold a response.** A slot holding a live
      request belongs to whoever wrote it, and the pad owes them an answer.
      Writing over it destroys a negotiation already in progress, and because
      store writes land a turn late, both parties would otherwise write the
      same round and one word would simply vanish. With this rule the Builder
      and the pad alternate and nothing is lost.
    * **We must be addressing the pad that actually owns our tile** -- the
      lowest-id friendly Launcher whose pickup radius covers us. The landing is
      encoded as an offset from that pad, and the same rule tells the pad to
      decode it, so both ends always agree on which tile was meant.
    """
    if p.awaiting_launch:
        return False
    slot = LAUNCH_REQUEST_SLOTS[p.builder_index % len(LAUNCH_REQUEST_SLOTS)]
    if not writable_by_builder(ct.read_store(slot)):
        # Somebody's live request is in there; wait rather than clobber it.
        return False
    pad = tuple(launcher_position)
    owner = pad_owner(_known_pads(p, ct), tuple(ct.get_position()))
    if owner is not None:
        pad = owner
    landing = _choose_landing(p, ct, pad, tuple(target))
    if landing is None:
        return False
    index = landing_index(pad, landing)
    if index is None:
        return False
    ct.write_store(slot, pack_request(ct.get_id(), index))
    p.awaiting_launch = LAUNCH_REQUEST_ROUNDS
    p.launch_origin = tuple(ct.get_position())
    p.last_pad_asked = pad
    p.last_landing_asked = landing
    if DEBUG_LAUNCH:
        print(f"LREQ r={ct.get_current_round()} id={ct.get_id()} slot={slot} "
              f"at={tuple(ct.get_position())} pad={pad} landing={landing} "
              f"goal={tuple(target)}", file=sys.stderr, flush=True)
    return True


def _known_pads(p, ct):
    """Friendly pads we know of, position -> entity id (None if unseen).

    Remembered pads count for planning: a Builder may route through a Launcher
    it cannot currently see. Its id only matters when the request is actually
    written, and by then the Builder is inside the pickup radius and looking
    straight at it.
    """
    pads = {}
    for spot in getattr(p, "friendly_launchers", ()):
        position = Position(*spot)
        ident = None
        if ct.is_in_vision(position):
            building = ct.get_tile_building_id(position)
            if building is not None and ct.get_team(building) == ct.get_team():
                ident = building
        pads[spot] = ident
    return pads


def _choose_landing(p, ct, pad, target):
    """The tile in this pad's throw field the passenger actually wants.

    Everything the pad used to guess at is decided here, with the information
    that makes the decision answerable:

    * **Never a tile under fire.** A thrown Builder arrives with its move
      already spent and eats a full round before it can step off, so a covered
      landing is worse than a covered tile it walked onto. This uses the
      remembered threat map, which includes lanes inferred from damage taken by
      units and buildings rounds ago and turrets currently out of sight.
    * **Then nearest the goal by walking distance**, counting walls, because a
      landing four tiles nearer in a straight line can be twenty further to
      walk.
    * **Then furthest from the pad**, which breaks ties toward actually making
      progress rather than hopping one tile.

    Returns None when the field holds nothing safe and reachable; the caller
    then treats the relay as unavailable rather than taking a bad throw.
    """
    reachable = _distance_map(p, target)
    best, best_key = None, None
    for dx, dy in THROW_OFFSETS:
        tile = (pad[0] + dx, pad[1] + dy)
        if not _inside(p, tile) or tile in p.walls or tile in p.solids:
            continue
        if tile in p.ores or tile in p.bot_occupied:
            continue
        if _threat_at(p, tile):
            continue
        # A tile with anything standing on it is not a landing, and the traced
        # failure was exactly this: builder 36 asked to be thrown onto (8,16),
        # which was the tile an enemy Sentinel was standing on. `solids` only
        # holds what this Builder has personally sensed, and it had never seen
        # that tile -- so nothing above rejected it and every one of those
        # requests came back `illegal-throw`. Check the live map as well as
        # memory; the Builder can see far more than it has walked past.
        position = Position(*tile)
        if ct.is_in_vision(position):
            if (ct.get_tile_building_id(position) is not None
                    or ct.get_tile_builder_bot_id(position) is not None
                    or not ct.is_tile_passable(position)):
                continue
        if tile in p.enemy_turrets or tile in p.enemy_launchers:
            continue
        # Never inside an enemy Launcher's pickup radius. Pickup is team-blind,
        # so a Builder landing there can be picked up and thrown by their pad --
        # and it arrives with its move already spent, so it cannot step clear
        # first. Landing in reach of one is handing them a free displacement of
        # a 30 Ti unit, at the exact moment it is least able to react.
        if tile in _launcher_hazards(p):
            continue
        # A tile we were thrown off before. Something within pickup range of it
        # displaces us, whether or not we have ever seen what.
        if tile in p.displaced_landings:
            continue
        walk = reachable.get(tile)
        if walk is None:
            continue
        key = (walk, -(dx * dx + dy * dy))
        if best_key is None or key < best_key:
            best, best_key = tile, key
    return best


def _is_enemy_launcher(ct, spot):
    """True only for a Launcher we can see and can see belongs to them.

    Unseen is not hostile. Refusing to guess is the safe direction here: a
    friendly Launcher wrongly called hostile costs a permanent nine-tile hole in
    our own movement map, while an enemy one wrongly called friendly costs one
    throw we were going to lose anyway.
    """
    position = Position(*spot)
    if not ct.is_in_vision(position):
        return False
    building = ct.get_tile_building_id(position)
    if building is None:
        return False
    return (ct.get_entity_type(building) == EntityType.LAUNCHER
            and ct.get_team(building) != ct.get_team())


def _consume_launch_rejection(p, ct):
    """Read the pad's answer and fold anything it reported into the map.

    Intel is recorded *before* anything else is decided. A reported turret is a
    fact about the world; it is either already known, in which case recording it
    is idempotent, or it is new, in which case it is the most valuable thing the
    Builder will learn all game. The previous version validated first and
    returned early on a mismatch, which threw away correct turret positions --
    the reply that would have stopped a Builder asking for the same tile every
    four rounds for the rest of the game.

    There is no separate memory of refused landings. The map is the single
    source of truth: the turret goes in, `_choose_landing` avoids everything it
    covers, and the bad tile stops being proposed as a consequence rather than
    as a special case.
    """
    slot = LAUNCH_REQUEST_SLOTS[p.builder_index % len(LAUNCH_REQUEST_SLOTS)]
    value = ct.read_store(slot)
    if not is_response(value):
        return False
    pad = p.last_pad_asked
    if pad is None:
        return False
    launched, reply_hash, entries = unpack_response(pad, value)
    for position, facing, kind_index in entries:
        kind = REJECT_KINDS.get(kind_index)
        if kind is None or not _inside(p, position):
            continue
        if kind == EntityType.LAUNCHER:
            p.enemy_launchers.add(position)
        else:
            p.enemy_turrets[position] = (kind, D8[facing])
        p.solids.add(position)
    if entries:
        p.threat_signature = None

    if reply_hash != passenger_hash(ct.get_id()):
        # Somebody else's answer, on a slot we share. Their intel was still
        # worth having; the outcome was not ours to act on.
        return False
    p.awaiting_launch = 0
    p.launch_origin = None
    if launched:
        _note_displacement(p, ct)
    if not launched:
        # Answered and refused: hold off before asking again.
        #
        # This used to set the stamp to the *current* round, and the gate that
        # reads it is `current_round < launch_retry_round` -- never true, so
        # there was no cooldown and a Builder could re-ask the round after every
        # refusal. Refusals are not rare: with the economy expanded they run 281
        # of 650 requests (43%), because the pad correctly declines to throw a
        # passenger into a firing line. Each retry cycle costs the passenger a
        # round of standing still, and the reason for the refusal -- a turret
        # covering the landing -- does not usually clear in one round.
        #
        # Walking for a few rounds is strictly better than asking again into the
        # same answer, and the intel the refusal carried is already folded into
        # the threat map, so the route it walks is the informed one.
        p.launch_retry_round = ct.get_current_round() + LAUNCH_RETRY_COOLDOWN
    # Clear the answer once it has been read.
    #
    # Nothing cleared this slot, so the pad's reply stayed in it for the rest of
    # the game, this function returned True on every later round, and
    # `_opening_ferry` bailed on its first line every time. Instrumented over
    # ~58 ferry calls a game: one request, one pad built, and **56 blocked** --
    # the relay makes a single request, is refused once, and never runs again.
    #
    # The cooldown immediately above is the intended behaviour and could never
    # take effect: `launch_retry_round` is compared against the current round by
    # a gate that is never reached, because the stale reply short-circuits ahead
    # of it. Clearing the slot is what makes the cooldown mean what it says.
    #
    # This matters because delivery is the wall behind three separate failures
    # in this log -- the forward Sentinel seat, the Core-ring barrier, and the
    # attacker walking the last seven tiles into turret fire. The ferry is the
    # one mechanism that crosses that ground in a single round.
    ct.write_store(slot, 0)
    return True


def _sign(value):
    return (value > 0) - (value < 0)


def _move_while_stuck(p, ct, target):
    """Explore locally while waiting until a useful Launcher is affordable."""
    source = ct.get_position()
    candidates = []
    for direction in FACING.values():
        position = source.add(direction)
        if (tuple(position) not in _no_go(p, tuple(source))
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


def _note_displacement(p, ct):
    """A successful throw that did not leave us where we asked means we were thrown again.

    This is the only evidence a Builder can get about an enemy Launcher it will
    never see. The sequence is forced by action order: units act in spawn-id
    order, so an enemy pad with a lower id than ours acts *first* every round.
    It picks our passenger off the landing tile before the Builder's own turn
    comes round, which means `_sense` never runs from there and the Builder has
    no idea anything happened -- traced on r03, where builder 64 was thrown
    between (9,16) and (8,12) from round 33 to the end of the game, asking for
    (9,16) again each time because from its point of view it had never been
    near an enemy Launcher.

    The pad's success reply breaks that. It says "I threw you to X"; if the
    Builder is not at X when it reads that, something else moved it, and the
    only thing that moves a Builder without its consent is a Launcher within
    pickup range of X. So X is struck off, permanently, without needing to see
    what is standing next to it.

    The tolerance is the pickup radius: a Builder that landed cleanly and then
    took one ordinary step of its own is not displaced.
    """
    landing = p.last_landing_asked
    if landing is None:
        return
    here = tuple(ct.get_position())
    if _distance_sq(here, landing) > LAUNCH_PICKUP_SQ:
        p.displaced_landings.add(landing)
        _mark_progress(p, ct, "thrown off a landing", landing)


def _launch_beats_walking(p, ct, target):
    """Only pay for a Launcher when it costs less HP than walking would.

    A Launcher is 20 Ti and +10% on every later price, and building one is not
    free in rounds either: the Builder has to stand somewhere adjacent and spend
    a turn on it, taking whatever that tile takes. So it is the right answer to
    a firing line only when walking is genuinely worse, and "there is fire
    somewhere on the route" is not that test.

    Two estimates, both in HP, which is the currency that matters here:

    * **Walking** costs the sum of the threat on every tile the short route
      crosses -- a Builder stands on one tile per round, so a tile's threat is
      exactly what it charges to pass through.
    * **Launching** costs the tile we build from, for the rounds it takes to
      build, and nothing after that: the landing is already chosen clear of
      fire by the pad.

    When the two are close, walking wins by default -- it does not spend the
    titanium or the cost scale, and those are invisible to this comparison.
    """
    here = tuple(ct.get_position())
    path = _bfs_path(p, here, tuple(target), False, allow_hops=False)
    if path is None:
        # No walking route at all: the Launcher is the only way through.
        return True
    walking = sum(_threat_at(p, tile) for tile in path[1:])
    launching = _threat_at(p, here) * LAUNCHER_BUILD_ROUNDS
    return walking > launching


def _retreat_from_fire(p, ct):
    """Get out of the firing line, or hold still if we are already clear.

    Called when the only route to the errand runs through fire the Builder
    would not survive. Standing on a covered tile is the worst of both -- it
    takes the damage and makes no progress -- so the first job is simply to be
    somewhere that is not covered.

    Preference order is: least fire on the tile, then *furthest from any fire*,
    then nearest our own Core. The middle term is what makes this a retreat
    rather than a shuffle -- a Builder that steps sideways off a Sentinel's
    line is one tile from being back on it, and the tile it moved to is often
    covered by the next turret along. Backing off until the whole cluster is
    out of reach is what actually ends the exposure, and heading homeward
    breaks the tie because home is where the mender and our own turrets are.
    """
    here = tuple(ct.get_position())
    threat_tiles = getattr(p, "threat", {})

    def clearance(spot):
        if not threat_tiles:
            return 0
        return min(_distance_sq(spot, tile) for tile in threat_tiles)

    best = None
    best_key = (_threat_at(p, here), -clearance(here), 0)
    for direction in D8:
        spot = ct.get_position().add(direction)
        key = tuple(spot)
        if not _inside(p, key) or key in p.walls or key in p.solids:
            continue
        if key in p.bot_occupied or not ct.can_move(direction):
            continue
        rank = (_threat_at(p, key), -clearance(key),
                _distance_sq(key, p.core) if p.core else 0)
        if rank < best_key:
            best, best_key = direction, rank
    if best is not None:
        ct.move(best)
        _mark_progress(p, ct, "retreated from fire", tuple(ct.get_position()))


def _bfs_step(p, source, target, exact, avoid_launchers=True, ct=None,
              allow_hops=True):
    """First move of the cardinal route, or None when there is no route.

    With a controller in hand the route is checked against the known firing
    lines before its first step is taken; without one this is the plain
    shortest path, which is what the callers that only need a distance want.
    """
    if ct is not None:
        path = _safe_path(p, ct, source, target, exact, avoid_launchers,
                          allow_hops=allow_hops)
    else:
        path = _bfs_path(p, source, target, exact,
                         avoid_launchers=avoid_launchers,
                         allow_hops=allow_hops)
    if path is None or len(path) < 2:
        return None
    return path[1]


def _safe_path(p, ct, source, target, exact, avoid_launchers=True,
               allow_hops=True):
    """A route that avoids fire, or an explicit refusal.

    `_bfs_path` now refuses firing lines and enemy Launcher radii outright, via
    `_no_go`, so the ordinary case needs no second pass: the route it returns is
    already clean. This function only has to decide what to do when there is no
    clean route at all.

    The old shape -- plan short, price it, detour if it kills us, otherwise walk
    it anyway -- was the source of the oscillation. It could return a route
    through a lane that `_leave_the_firing_line` would immediately step back out
    of, so the Builder alternated between the two forever. Preferring safety and
    enforcing safety are not the same rule, and running both at once is a
    livelock.

    So: a clean route is taken. Failing that, a route through fire is taken only
    if the walk is genuinely survivable, because sometimes the errand still has
    to happen and the alternative is standing still. Failing that, None, and the
    caller retreats or buys a Launcher over the top.
    """
    p.blocked_by_fire = False
    path = _bfs_path(p, source, target, exact, avoid_launchers,
                     allow_hops=allow_hops)
    if path is not None:
        return path
    through_fire = _bfs_path(p, source, target, exact, avoid_launchers,
                             allow_hops=allow_hops, allow_fire=True)
    if through_fire is not None and _survives_path(p, ct, through_fire[1:]):
        return through_fire
    p.blocked_by_fire = True
    return None


def _bfs_path(p, source, target, exact, avoid_launchers=True,
              extra_blocked=(), allow_hops=True, allow_fire=False):
    """Full route from source to a goal tile, or None.

    A thin reconstruction over `_travel`; the search itself lives there so that
    movement and target selection cannot use different graphs. A hop is an
    ordinary parent link, so a route through a Launcher rebuilds exactly like a
    walk -- `_step` notices it because the step is not adjacent, and asks the
    pad instead of moving.
    """
    goals = {target} if exact else _adjacent(p, target)
    if source in goals:
        return [source]
    dist, prev = _travel(p, source, goals=goals, hops=allow_hops,
                         allow_fire=allow_fire, extra_blocked=extra_blocked)
    reached = [(dist[g], g) for g in goals if g in dist]
    if not reached:
        return None
    found = min(reached)[1]
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
    """Steps to the nearest of `goals`, or None. Same search as everything else."""
    if source in goals:
        return 0
    dist, _ = _travel(p, source, goals=goals)
    reached = [dist[g] for g in goals if g in dist]
    return min(reached) if reached else None


def _no_go(p, source=None):
    """Ground no Builder may walk on, for every planner in this file.

    There used to be several answers to "is this tile safe", and they disagreed.
    `_leave_the_firing_line` treated a covered tile as forbidden while the route
    planner treated it as merely expensive, so a Builder would step off a lane
    and the next round's path would walk it straight back on -- builder 66
    oscillated between two tiles from round 43 to the end of the game doing
    exactly that. Two notions of safety in one bot is a livelock waiting to
    happen, so there is now one.

    Firing lines are blocked outright rather than priced, and enemy Launcher
    pickup radii with them: being thrown is not damage that can be weighed
    against a shorter route, it is the loss of the Builder's position entirely.

    `source` is exempt: standing somewhere forbidden has to leave a legal move
    out of it, or the Builder is stuck by its own rules.
    """
    # The union is cached for the turn. It is six set unions over every wall
    # tile on the map, and it is rebuilt by every planner that asks a routing
    # question -- which is most of them, several times a turn. Nothing in it
    # moves while the Builder is still deciding: terrain, our own buildings,
    # occupied tiles and the remembered threat map are all written by `_sense`
    # at the top of the turn and not again until the Builder acts.
    #
    # This matters more than a local profile suggests. The cluster the ladder
    # rates on is roughly 1.6x slower than this machine, and two earlier builds
    # of this bot passed `benchmarks.timing` here with zero overruns while the
    # tournament's own compliance stage recorded 29 and 19 timeouts against the
    # same 10 ms limit. A turn that overruns there does not act at all.
    if getattr(p, "nogo_round", None) != getattr(p, "round", -1):
        p.nogo_round = getattr(p, "round", -1)
        p.nogo_base = (p.walls | p.foot | p.solids | p.bot_occupied
                       | _launcher_hazards(p) | set(getattr(p, "threat", ())))
    blocked = p.nogo_base
    return blocked - {source} if source is not None else set(blocked)


def _travel(p, source, goals=None, hops=True, allow_fire=False,
            extra_blocked=(), ignore_bots=False):
    """The single BFS every planner in this file uses.

    There were four of these -- one for movement, one for choosing which target
    to go to, one for distance-to-a-goal-set, one for laying belt -- and they
    disagreed. `_bfs_path` counted a Launcher hop as a one-round edge while
    `_distance_map` did not, so a Builder chose its errand by walking distance
    and then travelled by throwing: a goal that is far when choosing and near
    when moving keeps winning and losing. Traced on r03, builder 11 was ferried
    to (2,9) for an ore at (1,9), walked away from it on landing, asked to be
    thrown to (7,11), walked away from that, and asked for (7,3) -- three
    ferries in twelve rounds, each correct for the goal it held that instant.

    One search means target selection and movement cannot disagree, because
    they are the same computation. Returns (distance, came_from); `came_from`
    carries a hop as an ordinary parent link, so a path through one reconstructs
    exactly like a walk.

    `hops=False` is for the callers that genuinely mean walking -- pricing a
    throw against a walk, or planning conveyor tiles.

    Memoised for the duration of one turn. Several planners ask for the same
    distance map inside a single `run()` -- target selection, then the route to
    the target it chose, then the siege seat search pricing every candidate --
    and each one was paying for a fresh flood of the whole map. A Builder acts
    at most once a turn and every search happens before it acts, so nothing the
    cache could go stale against has changed yet; the entries are dropped the
    moment the round number moves. This is what replaced the CPU-clock guard:
    the same work avoided, without making the answer depend on the machine.
    """
    key = (source, None if goals is None else frozenset(goals), hops,
           allow_fire, tuple(sorted(extra_blocked)), ignore_bots)
    if getattr(p, "travel_cache_round", None) != getattr(p, "round", -1):
        p.travel_cache_round = getattr(p, "round", -1)
        p.travel_cache = {}
    cached = p.travel_cache.get(key)
    if cached is not None:
        return cached
    blocked = _no_go(p, source) | set(extra_blocked)
    if ignore_bots:
        # Other Builders are obstacles that walk away. Treating them as solid is
        # right for choosing a route and wrong for deciding a route is
        # impossible, which is the only question this flag is asked.
        blocked = blocked - p.bot_occupied
    if allow_fire:
        blocked = blocked - set(getattr(p, "threat", ()))
    blocked.discard(source)
    pads = {}
    if hops and LAUNCH_HOPS_IN_PATHS:
        # Every live Launcher is an edge, exactly as this router was written.
        #
        # A cap on the nearest few pads was tried while chasing the turn limit
        # and is not here, because it was not what cost the time: the expense
        # was `_throw_landings` rebuilding the identical 121-candidate list for
        # every pad tile popped off this queue, hundreds of times a turn.
        # Memoising that per turn took the worst Builder turn from 13,075 us to
        # 4,507 against a 10,000 limit, which pays for the whole pad set with
        # room to spare -- and the cap was worth one game in 210 anyway.
        pads = {tile: pad
                for pad in getattr(p, "friendly_launchers", ())
                for tile in _stamp(p, pad, LAUNCH_PICKUP_SQ)}
    goals = set(goals) if goals else None
    dist, prev = {source: 0}, {source: None}
    queue = deque([source])
    while queue:
        cur = queue.popleft()
        if goals and cur in goals:
            break
        neighbours = [(cur[0] + dx, cur[1] + dy) for dx, dy in D4_DELTAS]
        pad = pads.get(cur)
        if pad is not None:
            neighbours.extend(_throw_landings(p, pad))
        for nxt in neighbours:
            if nxt in dist or not _inside(p, nxt) or nxt in blocked:
                continue
            dist[nxt] = dist[cur] + 1
            prev[nxt] = cur
            queue.append(nxt)
    p.travel_cache[key] = (dist, prev)
    return dist, prev


def _distance_map(p, source, hops=True):
    """Every reachable distance, on the same terms movement will use."""
    return _travel(p, source, hops=hops)[0]


def _explore(p, ct):
    me, stride = tuple(ct.get_position()), 4

    # A miner that knows of no ore has a better prior than a grid sweep: a
    # fair map places its shared ore between the Cores. On sweden, seat A's
    # Core at (0,0) has the whole ore band outside its r^2=36 opening vision
    # (seat B sees it), so this seat staffed no economy at all and lost 0-mined
    # by round 317, deterministically — the miner grid-swept while the rush
    # arrived, then spent the rest of the game pinned to mending. Walking the
    # Core-to-Core line crosses the band inside ten rounds even when the
    # symmetry guess is wrong, which is before the alarm can pin anyone.
    if (not p.is_attacker and not p.is_launcher_builder
            and not p.ores and p.core is not None):
        enemy, _ = unpack_enemy(ct.read_store(SLOT_ENEMY_CORE))
        if enemy is None:
            enemy = (p.w - 2 - p.core[0], p.h - 2 - p.core[1])
        mid = ((p.core[0] + enemy[0]) // 2, (p.core[1] + enemy[1]) // 2)
        if max(abs(mid[0] - me[0]), abs(mid[1] - me[1])) > 2:
            if not getattr(p, "ore_prior_announced", False):
                p.ore_prior_announced = True
                print(f"ORE_PRIOR round={ct.get_current_round()} "
                      f"from={me} mid={mid}", file=sys.stderr, flush=True)
            _step(p, ct, Position(*mid), True)
            return

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
    # Re-rank the head of the list by the distance actually walked.
    #
    # Same defect `_pick` had: the sort key is Chebyshev, which is what the
    # target looks like as the crow flies, and the Builder then walks a real
    # path around terrain. Around a wall those orders differ, and the harasser
    # spends the difference walking. Only the head is re-priced, and only within
    # one priority class, so the cheap ordering still decides *what* to hit and
    # this decides *which one* of the equally valuable.
    if HARASS_TRUE_DISTANCE and targets:
        top = HARASS_PRIORITY[p.enemy_economy[targets[0]]]
        head = [t for t in targets[:HARASS_RERANK_CANDIDATES]
                if HARASS_PRIORITY[p.enemy_economy[t]] == top]
        priced = []
        for tile in head:
            walk = _distance(p, me, {tile})
            if walk is not None:
                priced.append((walk, tile))
        if priced:
            priced.sort()
            best_tile = priced[0][1]
            targets = [best_tile] + [t for t in targets if t != best_tile]
    # 2.3.3 inverted the attack rule: a Builder damages an orthogonally
    # adjacent tile and never the one it stands on, so stand *beside* the
    # target rather than on it.
    #
    # Which side it stands on is a free choice and it was being thrown away.
    # A belt is a long line of identical tiles: breaking the one that happens
    # to be in front of us while standing in a Sentinel's lane costs 18 HP a
    # round, and two steps away there is another tile of the same belt worth
    # exactly the same, reachable from cover. The damage is the same, the price
    # is not. So an exposed seat only fires when there is no safe one.
    exposed = _threat_at(p, me)
    if exposed:
        seat = _safe_harass_seat(p, ct, targets)
        if seat is not None:
            _step(p, ct, Position(*seat), True)
            return
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


def _safe_harass_seat(p, ct, targets):
    """An uncovered tile from which some equally good target can be hit.

    Every tile of an enemy belt is worth the same to break, so the question is
    never "which target" but "from where". Returns the nearest unthreatened
    standing tile that is cardinally adjacent to any of them, or None when the
    whole approach is covered and firing exposed really is the only option.
    """
    me = tuple(ct.get_position())
    seats = []
    for target in targets:
        for dx, dy in D4_DELTAS:
            seat = (target[0] + dx, target[1] + dy)
            if not _inside(p, seat) or _threat_at(p, seat):
                continue
            if seat in p.walls or seat in p.solids or seat in p.bot_occupied:
                continue
            seats.append(seat)
    if not seats:
        return None
    return min(seats, key=lambda s: (_cardinal_distance(me, s), s))


def _leave_the_firing_line(p, ct):
    """Never end a turn on a tile a turret can shoot, unless it is worth it.

    The global version of the rule the harasser needed. Almost every job a
    Builder does leaves it free to choose which tile it does the job from, and
    a covered tile costs 7 HP a round to a Gunner or 18 to a Sentinel for
    nothing -- the work gets done either way.

    Two exemptions, and they are the whole reason this is a function rather
    than a blanket ban:

    * **Healing a Core that is under attack.** Healing restores 4 HP for a flat
      1 Ti at any cost scale, so a mender standing in the lane out-heals a
      Gunner and cancels a Sentinel outright. Leaving would trade a Core for a
      Builder.
    * **Nowhere better to stand.** `_retreat_from_fire` already ranks by
      exposure first and only moves to something strictly safer, so when the
      whole area is covered this correctly does nothing and the Builder gets on
      with its work.

    Returns True when it spent the turn moving, so the caller stops there.
    """
    if not LEAVE_FIRING_LINE:
        return False
    here = tuple(ct.get_position())
    if not _threat_at(p, here):
        return False
    alarm = ct.read_store(SLOT_CORE_DAMAGED) & CORE_ALARM_MASK
    if alarm and p.core is not None and _chebyshev(here, p.core) <= 2:
        # Standing beside a Core that is being shot is the mender's post.
        return False
    before = tuple(ct.get_position())
    _retreat_from_fire(p, ct)
    return tuple(ct.get_position()) != before


def _escape_encirclement(p, ct):
    """Leave before the box closes.

    The mirror of `_trap_enemy_builder`, and the reason to write it is that we
    do this to them: a Builder with one exit left is one barrier from being
    worth nothing for the rest of the game, and the barrier costs them 3 Ti.
    Being walled in is not survivable later -- it is only avoidable now -- so
    the check is cheap and unconditional rather than something the Builder gets
    to weigh against its errand.

    Counts *cardinal* exits, because that is how Builders move, and only fires
    when an enemy Builder is close enough to be the one closing it. Terrain that
    happens to be tight is not an ambush.
    """
    if not ESCAPE_ENCIRCLEMENT:
        return False
    here = tuple(ct.get_position())
    exits = [(here[0] + dx, here[1] + dy) for dx, dy in D4_DELTAS
             if _inside(p, (here[0] + dx, here[1] + dy))
             and (here[0] + dx, here[1] + dy) not in p.walls
             and (here[0] + dx, here[1] + dy) not in p.solids
             and (here[0] + dx, here[1] + dy) not in p.bot_occupied]
    # No exits at all is not an escape, it is a fact. The guard below reads
    # `> ESCAPE_MIN_EXITS`, which at the shipped value of 1 lets len(exits) == 0
    # through to a `max()` over an empty list -- so the one situation this
    # function exists to handle, a Builder already fully boxed in, raised
    # ValueError instead. The crash handler swallows it and returns, so the
    # Builder then did nothing at all for the rest of the game: no belt, no
    # heal, no self-destruct, still paying its +20% of cost scale. Traced on
    # quarry against vidar, builder id=31 from round 68 to the end.
    #
    # Falling through instead lets the ordinary machinery have it -- in
    # particular `_write_off`, which retires a Builder that cannot path and
    # refunds the scale so the Core can re-roll it somewhere not walled in.
    if not exits or len(exits) > ESCAPE_MIN_EXITS:
        return False
    closers = [entity_id for entity_id in ct.get_nearby_entities(9)
               if ct.get_team(entity_id) != ct.get_team()
               and ct.get_entity_type(entity_id) == EntityType.BUILDER_BOT]
    if not closers:
        return False
    # Leave by the exit with the most room beyond it, breaking ties away from
    # whoever is doing the walling.
    def room(tile):
        return sum(1 for dx, dy in D4_DELTAS
                   if _inside(p, (tile[0] + dx, tile[1] + dy))
                   and (tile[0] + dx, tile[1] + dy) not in p.walls
                   and (tile[0] + dx, tile[1] + dy) not in p.solids)

    best = max(exits, key=lambda t: (
        room(t), _threat_at(p, t) == 0,
        min(_distance_sq(t, tuple(ct.get_position(c))) for c in closers),
    ))
    for direction in D8:
        if tuple(ct.get_position().add(direction)) == best:
            if ct.can_move(direction):
                ct.move(direction)
                _mark_progress(p, ct, "escaped encirclement", best)
                return True
            break
    return False


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


def _core_is_hurt(p, ct):
    """Has our Core lost any HP at all?

    Read directly rather than through the Core's `repair_alert`, which only
    raises at 50 HP lost -- seven Gunner shots, or about ten rounds of an
    emplaced turret. That threshold exists to summon a Builder from across the
    map; a Builder standing on the Core can simply look.
    """
    core_position = Position(*p.core)
    if not ct.is_in_vision(core_position):
        return False
    core_id = ct.get_tile_building_id(core_position)
    if core_id is None:
        return False
    return ct.get_hp(core_id) < ct.get_max_hp(core_id)


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
    # Same tax, same ordering. A Launcher is +10 on the multiplier, permanently,
    # and the ring is laid in the opening -- before the Harvesters it makes more
    # expensive. Measured: scale reaches 243 by round 30 and a Harvester goes
    # from 20 Ti to 48. Holding the ring until the economy exists is the same
    # trade `_turret_tax_is_affordable` makes for turrets, which was worth
    # 0.633 against 0.610.
    if RING_AFTER_ECONOMY and not _turret_tax_is_affordable(p, ct):
        return False
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
        p.ring_planned_seen = len(p.seen)
    elif len(p.seen) - p.ring_planned_seen >= RING_REPLAN_TILES:
        # The reachability prune is only as good as the map we have seen, and
        # on round 3 we have seen almost none of it. Re-plan as vision grows:
        # a direction that looked open may turn out to dead-end, which deletes
        # a Launcher we were about to pay +10% for. Sites already built stay
        # built -- this re-plans what is left, it does not undo anything.
        p.ring_planned_seen = len(p.seen)
        fresh = _launcher_ring_targets(p, enemy_core)
        p.launcher_ring_targets = [t for t in fresh
                                   if tuple(t) not in p.launcher_ring_done]
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
        if (ct.get_global_resources()
                < ct.get_launcher_cost() + RING_TITANIUM_RESERVE):
            # A screen is worth less than the Harvester it would starve. Yield
            # the round rather than freeze: the caller sends this Builder to
            # mine, and the site is still here next time.
            return True
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
    if BARRIER_INTO_THREAT:
        # Deliberately the opposite rule to the belt's. A conveyor in their
        # firing line is 3 Ti we lose; a barrier in it is 3 Ti *they* have to
        # spend twenty rounds of ammunition on, and while it stands the lane is
        # shut and whatever the turret was covering is starved. The cheapest
        # object on the board is worth most exactly where it will be shot.
        shell |= {spot for spot in getattr(p, "threat", ())
                  if _inside(p, spot) and spot not in p.walls
                  and spot not in p.ores and spot not in p.foot
                  and spot not in p.solids
                  and _distance_sq(spot, p.core) <= CONTEST_MAX_DISTANCE_SQ}
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


def _danger_star(p, radius_sq):
    """Every tile a turret could stand on and hit the Core from.

    Not a disc. Both Gunner and Sentinel fire a *single-tile-wide straight line*
    along one of the eight compass directions -- so a turret only threatens the
    Core if it is aligned with a Core tile on one of those eight rays. The set
    of such tiles is a star of eight arms out of each of the four footprint
    tiles, and it is far smaller than the disc of the same radius.

    Getting this wrong was expensive: a disc at Sentinel reach is 97 tiles where
    the star is 30, so the screen was covering approaches no turret can ever
    shoot from, and spending +10% cost scale per Launcher to do it -- including
    Launchers planted against walls, guarding tiles that were never dangerous.

    The arm lengths fall straight out of the radius. At r^2=32 a cardinal arm
    reaches 5 (25 <= 32) and a diagonal 4 (32 <= 32); at r^2=13 it is 3 and 2.

    Blocking is deliberately ignored. A Sentinel's line is never blocked by
    anything, and a Gunner's blocker is a building the enemy can remove, so a
    tile that is only safe because something stands in the way is not safe.
    """
    star = set()
    for tile in p.foot:
        for direction in D8:
            dx, dy = direction.delta()
            step = 1
            while True:
                spot = (tile[0] + dx * step, tile[1] + dy * step)
                if _distance_sq(spot, tile) > radius_sq:
                    break
                if _inside(p, spot):
                    star.add(spot)
                step += 1
    return star - p.foot


def _forbidden_region(p, danger):
    """The star, plus every tile an enemy Builder could build into it from."""
    forbidden = set(danger)
    for tile in danger:
        for dx, dy in D4_DELTAS:
            spot = (tile[0] + dx, tile[1] + dy)
            if _inside(p, spot) and spot not in p.walls:
                forbidden.add(spot)
    return forbidden | p.foot


def _approach_shell(p, danger):
    """Passable tiles an enemy Builder must cross to reach a firing tile.

    A Builder builds onto an orthogonally adjacent tile, so it does not have to
    stand *in* the danger star to seat a turret there -- one step outside is
    enough. The region to deny is therefore the star grown by one, and the shell
    is what lies immediately outside that.

    Terrain and the map edge already deny it and are simply absent here. That is
    the whole of Lucas's dead-end rule at this stage: an arm of the star that
    runs into rock needs nothing built to close it.
    """
    forbidden = _forbidden_region(p, danger)
    shell = set()
    for tile in forbidden:
        for dx, dy in D4_DELTAS:
            spot = (tile[0] + dx, tile[1] + dy)
            if spot in forbidden or not _inside(p, spot):
                continue
            if spot in p.walls or spot in p.foot:
                continue
            shell.add(spot)
    return shell


def _seals_us_in(p, chosen, spot):
    """Would adding this site wall our own units in behind the screen?

    A Launcher is a building, and buildings are not walkable -- only conveyors
    and splitters are. So every site on the screen is impassable *to us*, and a
    screen that closes a ring closes it against our own guards and our own belt
    as much as against them. The old radius-2 ring knew this and said so; the
    knowledge was lost when the ring moved outward and grew, and the result is
    a Core whose defenders walk the long way round their own Launchers while a
    Sentinel shoots it.

    So the screen is checked for the property that actually matters: from the
    Core's spawn ring, can our units still reach open ground? A site that fails
    is skipped no matter how much shell it would have covered. Denying an
    approach is worthless if it also denies it to the mender.
    """
    blocked = p.walls | {spot} | set(chosen)
    start = next((tile for tile in _spawn_ring(p) if tile not in blocked), None)
    if start is None:
        return True
    seen, queue = {start}, deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in D4_DELTAS:
            nxt = (x + dx, y + dy)
            if nxt in seen or not _inside(p, nxt) or nxt in blocked:
                continue
            if nxt in p.foot:
                continue
            seen.add(nxt)
            queue.append(nxt)
    # Open ground means genuinely out, not just a pocket a few tiles wide.
    return len(seen) < SELF_SEAL_MIN_OPEN


def _spawn_ring(p):
    """The twelve tiles a Core can spawn a Builder onto."""
    return {(x, y)
            for tile in p.foot
            for x in range(tile[0] - 1, tile[0] + 2)
            for y in range(tile[1] - 1, tile[1] + 2)
            if (x, y) not in p.foot and _inside(p, (x, y))}


def _pad_serving(p, tile):
    """A friendly Launcher whose pickup radius covers `tile`, or None."""
    return next((pad for pad in getattr(p, "friendly_launchers", ())
                 if _distance_sq(pad, tile) <= LAUNCH_PICKUP_SQ), None)


def _throw_landings(p, launcher):
    """Tiles a friendly Launcher could put us on, cheapest-to-check form.

    Deliberately generous: legality is the Launcher's business at the moment of
    the throw, and a route that assumes a landing which turns out illegal simply
    re-plans next round. Being pessimistic here is what would keep the hop out
    of routes it should be in.

    Memoised per turn, and that is the whole reason the router can afford to
    treat every Launcher as an edge. This is called once for *every pad tile
    popped off the BFS queue* -- a pad's pickup stamp is eight tiles, each
    expansion screens 121 candidates against four predicates, and the BFS itself
    runs several times a turn. The list cannot change between those calls: it is
    a pure function of the map, `p.walls`, `p.solids` and `p.threat`, none of
    which move while a Builder is still deciding what to do. So the cache
    returns the identical list rather than an approximation of it, and the hop
    semantics are exactly what they were.
    """
    if getattr(p, "landing_cache_round", None) != getattr(p, "round", -1):
        p.landing_cache_round = getattr(p, "round", -1)
        p.landing_cache = {}
    cached = p.landing_cache.get(launcher)
    if cached is not None:
        return cached
    span = int(LAUNCH_RANGE_SQ ** 0.5)
    landings = [(launcher[0] + dx, launcher[1] + dy)
                for dx in range(-span, span + 1)
                for dy in range(-span, span + 1)
                if dx * dx + dy * dy <= LAUNCH_RANGE_SQ
                and _inside(p, (launcher[0] + dx, launcher[1] + dy))
                and (launcher[0] + dx, launcher[1] + dy) not in p.walls
                and (launcher[0] + dx, launcher[1] + dy) not in p.solids
                and not _threat_at(p, (launcher[0] + dx, launcher[1] + dy))]
    p.landing_cache[launcher] = landings
    return landings


def _stamp(p, spot, radius_sq):
    """Tiles a Launcher at `spot` can pick a Builder up from."""
    return {(spot[0] + dx, spot[1] + dy)
            for dx in range(-1, 2) for dy in range(-1, 2)
            if (dx or dy) and dx * dx + dy * dy <= radius_sq
            and _inside(p, (spot[0] + dx, spot[1] + dy))}


def _enemy_reachable(p, shell, danger, enemy_core, screened=()):
    """Drop shell tiles the enemy cannot actually walk to.

    Lucas's constraint: a direction that dead-ends needs no Launcher. Flood from
    the enemy Core across passable tiles, refusing to enter the threat disc --
    an attacker has to reach the shell from outside it. Anything the flood never
    touches is behind terrain, in a pocket, or off the only path in, and a
    Launcher there is +10% on every future price for nothing.

    Unseen tiles are treated as passable. Early on almost nothing is seen, so
    this prunes little and prunes it conservatively; it bites later, once the
    map is known, which is also when the screen is actually affordable.
    """
    if not REACHABILITY_ENABLED:
        return set(shell)
    forbidden = _forbidden_region(p, danger)
    blocked = p.walls | set(screened)
    start = tuple(enemy_core)
    if start in blocked or start in forbidden:
        return set(shell)
    seen, queue = {start}, deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in D4_DELTAS:
            spot = (x + dx, y + dy)
            if spot in seen or not _inside(p, spot) or spot in blocked:
                continue
            seen.add(spot)
            if spot in forbidden:
                # The denied region is the destination, not a corridor. Marking
                # it seen without walking on lets a shell tile count as reached
                # while stopping the flood from leaking through the middle and
                # calling the far side reachable by a route no attacker has.
                continue
            queue.append(spot)
    return {tile for tile in shell if tile in seen}


def _launcher_ring_targets(p, enemy_core):
    """Fewest Launcher sites whose pickup stamps cover the live approach shell.

    The old ring was eight compass sites at RING_RADIUS. Around a 2x2 Core that
    radius cannot hold eight things without them touching, which is exactly the
    "Launchers built right next to each other" seen in the replays -- a geometry
    fault, not a placement one. Two adjacent Launchers also cover almost the
    same tiles, so the second one is +10% on every later price for nothing.

    What a defensive Launcher does is pick up a Builder at LAUNCH_PICKUP_SQ and
    throw it clear, so each one covers a 3x3 stamp. The tiles worth covering are
    the shell just outside the threat disc: an enemy carrying a turret into
    range of the Core has to cross it. So this is a minimum set cover of that
    shell by 3x3 stamps -- greedy, which is within a log factor of optimal and
    is the reason no two chosen sites sit on top of each other.

    Three things shape the result:

    * **Reachability.** Shell tiles the enemy cannot walk to are dropped before
      the cover starts, so a dead end or a pocket behind terrain costs nothing.
    * **Separation.** No site is chosen within RING_MIN_SEPARATION Chebyshev of
      one already taken, which forbids adjacency outright.
    * **One per cardinal.** Greedy optimises total tiles covered and will
      happily leave a thin approach uncovered because it is cheap to ignore.
      A guaranteed site on each cardinal that still has live shell is the
      insurance against being flanked down the cheap side.

    The screen is also the attacker's throw pad, so the enemy-facing site is
    ordered first: it has to be the one that exists when the attacker asks.
    """
    danger = _danger_star(p, RING_THREAT_SQ)
    shell = _approach_shell(p, danger)
    live = _enemy_reachable(p, shell, danger, enemy_core)
    if not live:
        return []

    def buildable(spot):
        return (_inside(p, spot) and spot not in p.walls
                and spot not in p.ores and spot not in p.foot)

    # A site does not have to sit on the shell, only within pickup range of it.
    candidates = set()
    for tile in live:
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                spot = (tile[0] + dx, tile[1] + dy)
                if buildable(spot):
                    candidates.add(spot)

    covers = {spot: {tile for tile in live
                     if _distance_sq(spot, tile) <= LAUNCH_PICKUP_SQ}
              for spot in candidates}
    covers = {spot: tiles for spot, tiles in covers.items() if tiles}

    def spread(spot):
        """How far this site sits from the nearest one already chosen.

        Capped at RING_MIN_SEPARATION: past that the screen is spread enough and
        extra distance buys nothing, so the tie falls through to facing.
        """
        if not chosen:
            return RING_MIN_SEPARATION
        return min(RING_MIN_SEPARATION,
                   min(_chebyshev(spot, taken) for taken in chosen))

    # Closing the enemy off is a cut, not a perimeter. Covering every tile on
    # the boundary is *a* valid answer and a needlessly expensive one: a star
    # has a notched outline, and the notches behind a Launcher stop mattering
    # the moment the approach in front of it is shut. So each pick is followed
    # by a re-flood with the screen so far treated as blocking, and the next
    # pick only has to answer what is still reachable. On a map with a chokepoint
    # this collapses to the two or three sites that hold the gap.
    #
    # One flood per chosen site, not per candidate -- nine BFS passes over a
    # 30x30 grid, against a 10 ms budget, and only when the plan is rebuilt.
    chosen = []
    guard = 0
    while live and len(chosen) < RING_MAX_SITES and guard < RING_MAX_SITES * 2:
        guard += 1
        best = max(
            covers,
            key=lambda spot: (
                len(covers[spot] & live),
                spread(spot),
                -_distance_sq(spot, enemy_core),
            ),
            default=None,
        )
        if best is None or not (covers[best] & live):
            break
        del covers[best]
        if _seals_us_in(p, chosen, best):
            # Covers ground, but at the price of walling our own guards out.
            # Drop it and let the next iteration pick the runner-up.
            continue
        chosen.append(best)
        # Everything within pickup range of the screen is now denied ground:
        # an enemy Builder that steps there is thrown clear before it builds.
        screened = {tile for spot in chosen for tile in
                    _stamp(p, spot, LAUNCH_PICKUP_SQ)} | set(chosen)
        live = _enemy_reachable(p, shell - screened, danger, enemy_core,
                                screened=screened)
        covers = {spot: tiles & live for spot, tiles in covers.items()}
        covers = {spot: tiles for spot, tiles in covers.items() if tiles}

    # One per cardinal, for the approaches greedy found too cheap to bother
    # with. Only where that cardinal still has live shell -- a sealed side gets
    # nothing, which is the whole point of the reachability pass.
    for dx, dy in D4_DELTAS:
        if len(chosen) >= RING_MAX_SITES:
            break
        arc = [tile for tile in live if _cardinal_arc(p, tile) == (dx, dy)]
        if not arc:
            continue
        if any(_cardinal_arc(p, spot) == (dx, dy) for spot in chosen):
            continue
        reachable = [spot for spot in covers if covers[spot] & set(arc)]
        if not reachable:
            continue
        # Spread first here too, and again only as a preference.
        chosen.append(max(reachable,
                          key=lambda s: (spread(s), -_distance_sq(s, enemy_core))))

    # The "+1": one Launcher of depth behind the cut, on the enemy-facing side.
    # A cut is exactly tight -- it holds until the first Launcher in it dies,
    # and then the approach it was holding is open with nothing behind it. The
    # spare sits where they are actually coming from, which is the arc a cut
    # made of minimum sites is most likely to have held with a single tile.
    if RING_EXTRA_SITES and len(chosen) < RING_MAX_SITES and chosen:
        spare = [spot for spot in candidates
                 if spot not in chosen
                 and all(_chebyshev(spot, taken) >= 2 for taken in chosen)]
        for _ in range(RING_EXTRA_SITES):
            if not spare or len(chosen) >= RING_MAX_SITES:
                break
            pick = min(spare, key=lambda s: (_distance_sq(s, enemy_core), s))
            chosen.append(pick)
            spare = [s for s in spare if _chebyshev(s, pick) >= 2]

    chosen.sort(key=lambda site: (_distance_sq(site, enemy_core), site))
    return [Position(*site) for site in chosen]


def _cardinal_arc(p, tile):
    """Which cardinal quadrant a tile falls in, relative to the Core centre."""
    cx, cy = p.core[0] + 0.5, p.core[1] + 0.5
    dx, dy = tile[0] - cx, tile[1] - cy
    if abs(dx) >= abs(dy):
        return (1, 0) if dx > 0 else (-1, 0)
    return (0, 1) if dy > 0 else (0, -1)


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


def _turret_kind(ct, prefer_sentinel, p=None):
    """The turret a defensive role should buy right now.

    The Aug 4 patch inverted the turret table and this lineage never noticed.
    Under 2.3.3 a Gunner paid 2.78x less per point of damage and was +10% cost
    scale against a Sentinel's +20%, so Gunner spam was correct. Under 2.3.4
    both levy the same +20%, and once the count is fixed by that tax rather than
    by titanium, paying 10 Ti more a seat buys 1.71x the damage (6 a round
    against 3.5), 1.6x the HP (40 against 25), 2.46x the range (r^2=32 against
    13) and a line that terrain cannot block.

    The Gunner fallback is why this is a function and not a constant: a
    defensive seat is wanted at a moment that decides something, and a Gunner
    that fires beats a Sentinel that was unaffordable. Rotation is the one row
    the Gunner still wins, which is why this is not applied to every role.
    """
    # Seat B fights at range rather than in a duel.
    #
    # Units act in ascending entity id across both teams, so team A takes every
    # action first, every round, for the whole match -- and that shows up as a
    # 15.2pp seat gap against every opponent on the hard panel (A 0.667, B
    # 0.514). A first-strike advantage is worth most in a symmetric close-range
    # exchange, which is exactly a Gunner duel: both turrets can reach, and the
    # one that fires first wins it. It is worth least where the exchange is not
    # symmetric, which is what a Sentinel's r^2=32 against a Gunner's 13 buys.
    if (SEAT_B_PREFERS_RANGE and getattr(p, "seat_b", False)
            and ct.get_global_resources() >= ct.get_sentinel_cost()
            and ct.get_global_ammo() >= MIN_AMMO_FOR_SENTINEL):
        return EntityType.SENTINEL
    if (prefer_sentinel
            and ct.get_global_resources() >= ct.get_sentinel_cost()
            and ct.get_global_ammo() >= MIN_AMMO_FOR_SENTINEL):
        return EntityType.SENTINEL
    return EntityType.GUNNER


def _spar_turret(ct, position, facing):
    """Fixture only: buy the Sentinel seat whenever titanium allows.

    This is not a candidate. It exists so the internal panel contains the style
    the live ladder actually runs -- economy-funded Sentinel mass -- which no
    bot in the zoo plays, and which our worst live matchups all play.
    """
    if ct.get_global_resources() >= ct.get_sentinel_cost():
        ct.build_sentinel(position, facing)
    else:
        ct.build_gunner(position, facing)


def _build_turret(ct, kind, position, facing):
    if kind is EntityType.SENTINEL:
        ct.build_sentinel(position, facing)
    else:
        _spar_turret(ct, position, facing)


def _aligned_turret_site(p, ct, enemies, kind=EntityType.GUNNER):
    """Best adjacent tile and facing from which a new turret could fire now.

    Shared by home defence and by field engagement so both answer an enemy the
    same way: a real firing solution from a tile we may legally build on, never
    a hopeful compass bearing. _preserves_friendly_turret_lanes keeps the new
    turret out of the line of the ones already standing.

    `kind` decides the reach and the legality check together. A Sentinel sees
    r^2=32 against a Gunner's 13, so a seat search hardcoded to Gunner range
    rejects most of the seats a Sentinel could actually shoot from.
    """
    me = ct.get_position()
    protected_lanes = _friendly_turret_lanes(ct, p)
    sentinel = kind is EntityType.SENTINEL
    reach = SENTINEL_RANGE_SQ if sentinel else GUNNER_RANGE_SQ
    can_build = ct.can_build_sentinel if sentinel else ct.can_build_gunner
    candidates = []
    for direction in D8:
        position = me.add(direction)
        if not _inside(p, tuple(position)) or tuple(position) in p.foot:
            continue
        for enemy_id in enemies:
            target = ct.get_position(enemy_id)
            facing = _ray_direction(tuple(position), tuple(target))
            if (facing is not None
                    and position.distance_squared(target) <= reach
                    and ct.can_fire_from(position, facing, kind, target)
                    and _preserves_friendly_turret_lanes(
                        ct, position, protected_lanes,
                    )
                    and can_build(position, facing)):
                # A covered seat is refused, not ranked down. A turret fires
                # one ray of eight and a Sentinel cannot even rotate off it, so
                # seven directions are always free -- there is essentially never
                # a reason to seat a turret on the one ray that shoots back.
                # Returning None instead sends the Builder walking for a real
                # seat, which is the answer this used to be unable to give
                # because it only ever looked at its own eight neighbours.
                if _threat_at(p, tuple(position)):
                    continue
                candidates.append((
                    COMBAT_PRIORITY.get(ct.get_entity_type(enemy_id), 4),
                    position.distance_squared(target),
                    position.x, position.y, D8.index(facing), position, facing,
                ))
    if not candidates:
        return None
    *_, position, facing = min(candidates)
    return position, facing


def _turret_tax_is_affordable(p, ct):
    """Refuse a turret while the economy is still being bought.

    Measured: every price scales with `get_scale_percent`, and ours reaches
    **243 by round 30** and stays there -- a Harvester goes from 20 Ti to 48 and
    never comes back. Each turret is +20 of that scale, permanently, on every
    Harvester and conveyor bought afterwards.

    So the opening is a race between buying economy at 20 Ti and taxing it to
    48. This bot currently buys about five turrets early and two Harvesters all
    game; sporks buys one Gunner after round 100 and a Harvester every nine
    rounds. Holding the turret budget until the economy exists is the only
    ordering that keeps the multiplier low while the things that compound are
    being bought.

    The exception is damage: a Core under fire needs the answer now, whatever it
    costs later.
    """
    if not ECONOMY_BEFORE_TURRETS:
        return True
    if ct.get_current_round() >= TURRET_HOLD_ROUNDS:
        return True
    if ct.read_store(SLOT_CORE_DAMAGED) & CORE_ALARM_MASK:
        return True
    return p.network_load >= TURRET_HOLD_MIN_HARVESTERS


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
    if (not _turret_tax_is_affordable(p, ct)
            or p.field_gunners_built >= p.max_field_gunners
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
    site = _aligned_turret_site(p, ct, enemies)
    if site is None:
        return False
    position, facing = site
    _spar_turret(ct, position, facing)
    _mark_progress(p, ct, "built field gunner", tuple(position))
    p.field_gunners_built += 1
    return True


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
    # Moving second means their shot lands before our heal, so the seat that
    # loses ties escalates its home defence sooner.
    step = (SEAT_B_TURRET_STEP if (SEAT_AWARE_DEFENCE and getattr(p, "seat_b", False))
            else HOME_TURRET_STEP)
    desired = min(HOME_TURRET_MAX, 1 + damage // step)
    # One turret per enemy Sentinel, before the generic escalation. A Sentinel
    # is the thing that actually kills our Core -- it out-ranges us, its line is
    # never blocked, and it cannot rotate, so a turret seated on it stays
    # useful for as long as it stands. Counting them individually is what stops
    # the guard building its second and third Gunner against the same shooter
    # while a new one goes up unopposed.
    # The 3 Ti answer before the 30 Ti one.
    #
    # A barrier dropped in a live Gunner lane absorbs that Gunner's entire
    # clock: measured in the lab at one Builder holding a Core on zero damage
    # through 201 rounds of sustained fire for about 1 Ti a round, while the
    # shooter burned 2 Ti a shot. It was third in this order, behind a
    # counter-turret and an escalation turret that both consume the turn -- so
    # on the rounds it was most needed it was never reached.
    #
    # Ordering it first is the cost-scale argument again, in its sharpest form.
    # A barrier is 3 Ti and +1% scale; the turret it pre-empts is 20-30 Ti and a
    # permanent +20% on every price the team pays afterwards, including the
    # mending. And it answers the right thing: a Gunner's ray is blocked by
    # terrain where a Sentinel's is not, and Gunner fire is the large majority
    # of what kills a Core. Sentinel lanes are unblockable, find no site here,
    # and fall through to the turret and the mending exactly as before.
    if LANE_BARRIER_FIRST and _block_firing_lane(p, ct, enemies):
        return
    if _counter_sentinels(p, ct):
        return
    if (ct.get_global_ammo() >= MIN_AMMO_FOR_GUNNER
            and p.home_gunners_built < desired):
        kind = _turret_kind(ct, DEFEND_TURRET_SENTINEL, p)
        site = _aligned_turret_site(p, ct, enemies, kind)
        if site is None and kind is EntityType.SENTINEL:
            kind = EntityType.GUNNER
            site = _aligned_turret_site(p, ct, enemies, kind)
        if site is not None:
            position, facing = site
            _build_turret(ct, kind, position, facing)
            _mark_progress(p, ct, "built defensive turret", tuple(position))
            p.home_gunners_built += 1
            return
    if not LANE_BARRIER_FIRST and _block_firing_lane(p, ct, enemies):
        return
    # Every answer above requires a visible target, and a Builder's vision is a
    # fraction of the Core's r^2=36 -- a shooter parked outside it is healed
    # against forever and never killed (Besvikomat's round-3 Gunner ended a
    # 186-round siege untouched at 25/25 HP). The Core publishes the nearest
    # turret it can see through the alarm slot; when nothing is visible here,
    # walk toward that beacon until it is. The turret cannot move, the beacon
    # only exists while the alarm is up, and the Core only names shooters
    # within its own vision, so the walk is short and stays home by
    # construction. Standoff of 2: vision reaches before adjacency does, and
    # the round it is seen the ordinary answers take over.
    sees_turret = any(
        ct.get_entity_type(entity_id) in (EntityType.GUNNER,
                                          EntityType.SENTINEL)
        for entity_id in enemies)
    if not sees_turret:
        shooter = unpack_pos(
            ct.read_store(SLOT_CORE_DAMAGED) >> SHOOTER_POS_SHIFT)
        if shooter is not None:
            here = tuple(ct.get_position())
            if (_chebyshev(here, shooter) > 2
                    and _step(p, ct, Position(*shooter), True)):
                if not getattr(p, "hunt_announced", False):
                    p.hunt_announced = True
                    print(f"HUNT round={ct.get_current_round()} "
                          f"from={here} shooter={shooter}",
                          file=sys.stderr, flush=True)
                return
    _heal_core(p, ct)


def _counter_sentinels(p, ct):
    """Seat one turret against each enemy Sentinel, nearest their Builder first.

    A Sentinel cannot rotate. Whatever it was aimed at when it was built is the
    only thing it will ever shoot, so a turret that can hit it keeps its firing
    solution permanently -- unlike a Gunner duel, where the loser simply turns.
    That makes one-for-one the right exchange rate, and `countered_sentinels` is
    what enforces it: without a tally the guard spends its whole budget on the
    first Sentinel it saw while later ones go up unanswered.

    Where two seats both work, the one nearer a visible enemy Builder wins. The
    Builder is what turns one Sentinel into three, and a turret covering the
    ground it is working on kills the reinforcements as well as the shooter.
    """
    if SEAT_B_SKIPS_DUEL and getattr(p, "seat_b", False):
        # Answering a turret with a turret is the symmetric exchange seat B
        # loses. The 3 Ti lane barrier and the mender are not symmetric, and
        # they run immediately below this in `_defend_core`.
        return False
    sentinels = [entity_id for entity_id in ct.get_nearby_entities()
                 if ct.get_team(entity_id) != ct.get_team()
                 and ct.get_entity_type(entity_id) == EntityType.SENTINEL]
    outstanding = [entity_id for entity_id in sentinels
                   if tuple(ct.get_position(entity_id))
                   not in p.countered_sentinels]
    if not outstanding or ct.get_global_ammo() < MIN_AMMO_FOR_GUNNER:
        return False
    builders = [ct.get_position(entity_id)
                for entity_id in ct.get_nearby_entities()
                if ct.get_team(entity_id) != ct.get_team()
                and ct.get_entity_type(entity_id) == EntityType.BUILDER_BOT]
    outstanding.sort(key=lambda entity_id: (
        min((ct.get_position(entity_id).distance_squared(b)
             for b in builders), default=999),
        ct.get_position(entity_id).distance_squared(Position(*p.core)),
    ))
    for entity_id in outstanding:
        kind = _turret_kind(ct, DEFEND_TURRET_SENTINEL, p)
        site = _aligned_turret_site(p, ct, [entity_id], kind)
        if site is None and kind is EntityType.SENTINEL:
            kind = EntityType.GUNNER
            site = _aligned_turret_site(p, ct, [entity_id], kind)
        if site is None:
            continue
        position, facing = site
        _build_turret(ct, kind, position, facing)
        _mark_progress(p, ct, "countered sentinel", tuple(position))
        p.countered_sentinels.add(tuple(ct.get_position(entity_id)))
        p.home_gunners_built += 1
        return True
    return False


def _patrol_core(p, ct):
    """Walk a circuit round the Core instead of standing on it.

    A guard parked on one tile sees one approach. The Core's own vision is
    r^2=36 and does not move, so a stationary guard adds almost nothing to what
    the Core already knows -- what it can add is sight of the *other* side, and
    the only way to get that is to walk. Patrolling also puts the guard within
    building range of wherever the attack turns up, which is the difference
    between answering it this round and walking four rounds first.

    The circuit is the ring at PATROL_RADIUS, taken in order, skipping anything
    unreachable. Deliberately a fixed cycle rather than a chase: chasing is how
    a guard gets led away from the Core by a scout.
    """
    if p.core is None:
        return False
    ring = [tile for tile in _ring_at(p, PATROL_RADIUS)
            if tile not in p.walls and tile not in p.solids
            and not _threat_at(p, tile)]
    if not ring:
        return False
    here = tuple(ct.get_position())
    if p.patrol_target is None or p.patrol_target == here:
        # Advance to the next station a third of the way round, so the guard
        # sweeps rather than oscillating between two adjacent tiles.
        if p.patrol_target in ring:
            start = ring.index(p.patrol_target)
        else:
            start = min(range(len(ring)),
                        key=lambda i: _distance_sq(ring[i], here))
        p.patrol_target = ring[(start + max(1, len(ring) // 3)) % len(ring)]
    return _step(p, ct, Position(*p.patrol_target), True)


def _ring_at(p, radius):
    """The Chebyshev ring at `radius` around the Core footprint, in cycle order."""
    x0 = min(t[0] for t in p.foot) - radius
    x1 = max(t[0] for t in p.foot) + radius
    y0 = min(t[1] for t in p.foot) - radius
    y1 = max(t[1] for t in p.foot) + radius
    ring = ([(x, y0) for x in range(x0, x1 + 1)]
            + [(x1, y) for y in range(y0 + 1, y1 + 1)]
            + [(x, y1) for x in range(x1 - 1, x0 - 1, -1)]
            + [(x0, y) for y in range(y1 - 1, y0, -1)])
    return [tile for tile in ring if _inside(p, tile)]


def _trap_enemy_builder(p, ct):
    """Wall a loose enemy Builder in, then put a turret on the box.

    Only worth doing when nothing is currently shooting our Core -- it is slow,
    and a Builder spending rounds laying barriers is a Builder not answering an
    attack. But in the quiet it is the best trade on the board: a barrier is
    3 Ti and +1% against a Builder that costs them 30 Ti and +20% and is the
    only thing on their team that can build anything at all.

    Boxing it in first and shooting it after is what makes the turret pay. A
    free Builder walks out of a Gunner's ray in one move; a boxed one cannot
    move at all, so a single Gunner in the corner kills it at leisure -- 25 Ti
    to remove 30 Ti of theirs and every building it would ever have made.
    """
    if not TRAP_ENEMY_BUILDERS:
        return False
    targets = [entity_id for entity_id in ct.get_nearby_entities()
               if ct.get_team(entity_id) != ct.get_team()
               and ct.get_entity_type(entity_id) == EntityType.BUILDER_BOT]
    if not targets:
        return False
    here = tuple(ct.get_position())
    target = min(targets, key=lambda e: _distance_sq(
        tuple(ct.get_position(e)), here))
    spot = tuple(ct.get_position(target))
    # Only in our own half: chasing one across the map is how the guard ends up
    # out of position when the real attack lands.
    if _distance_sq(spot, p.core) > TRAP_MAX_DISTANCE_SQ:
        return False

    escapes = [(spot[0] + dx, spot[1] + dy) for dx, dy in D4_DELTAS
               if _inside(p, (spot[0] + dx, spot[1] + dy))
               and (spot[0] + dx, spot[1] + dy) not in p.walls
               and (spot[0] + dx, spot[1] + dy) not in p.solids]
    if escapes:
        if ct.get_global_resources() < ct.get_barrier_cost():
            return False
        gap = min(escapes, key=lambda t: _cardinal_distance(here, t))
        if _cardinal_distance(here, gap) != 1:
            return _step(p, ct, Position(*gap), False)
        position = Position(*gap)
        if ct.can_build_barrier(position):
            ct.build_barrier(position)
            _mark_progress(p, ct, "walling in enemy builder", gap)
            p.solids.add(gap)
            return True
        return False

    # Boxed. Now the corner turret -- it cannot dodge and it cannot leave.
    if ct.get_global_ammo() < MIN_AMMO_FOR_GUNNER:
        return False
    site = _aligned_turret_site(p, ct, [target])
    if site is None:
        return False
    position, facing = site
    _spar_turret(ct, position, facing)
    _mark_progress(p, ct, "turret on a boxed builder", tuple(position))
    p.home_gunners_built += 1
    return True


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
    protected = _friendly_turret_lanes(ct, p)
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
    if (p.attack_gunners_built < ATTACK_TURRET_CAP
            and _build_basic_gunner(p, ct, enemy_core)):
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
    # One siege Sentinel can never kill a mended Core, and until now that was
    # the hard cap: `p.siege_sentinel is not None` stopped each attacker after
    # exactly one, and SIEGE_SENTINEL_TARGET sat in constants.py unused.
    #
    # The arithmetic the whole field is built on runs both ways. A Builder heals
    # 4 HP for a flat 1 Ti, so the two menders every bot on this ladder now
    # posts restore 8 HP a round -- which is why a Core under one Sentinel's
    # 6 a round never falls, the siege stalls, and `SIEGE_STALL_ROUNDS` gives up
    # on it. Two Sentinels are 12 a round and three are 18, and *that* breaks
    # the equilibrium: past 8 the healing cannot keep up and the Core dies on a
    # clock no amount of mending changes.
    #
    # Each seat is +20% on every later price, so this is bounded rather than
    # unlimited, and the seats are spread by SENTINEL_SPREAD_LINES so one enemy
    # turret cannot answer two of them without rotating.
    if p.siege_sentinels_built >= SIEGE_SENTINEL_TARGET:
        return False
    # This search is the widest in the bot (13x13 around four Core tiles, a
    # full-map BFS and ~160 engine calls) and it runs last, after two others
    # have already spent the turn. It needs a bound: overrunning costs the whole
    # round, for every unit, on the map where it happens.
    #
    # The bound used to be a clock read, and that was a defect rather than a
    # tuning knob. `get_cpu_time_elapsed` makes the bot's *decisions* a function
    # of how busy the machine is, so the same board played twice gives different
    # answers -- measured here at 11 different winners in 210 matches of
    # identical code against identical opponents, which is larger than most of
    # the effects this bot is tuned on. It is also backwards where it matters:
    # the ladder machine is contended, so the search that survives on a quiet
    # laptop is the one that gets cut in the games that count.
    #
    # A round throttle bounds the same work deterministically. Retrying a wide
    # fallback search every single round is what made it expensive; a seat that
    # is not there this round is very rarely there the next.
    if ct.get_current_round() < p.last_siege_search_round + SIEGE_SEARCH_EVERY:
        return False
    p.last_siege_search_round = ct.get_current_round()
    if ct.get_global_ammo() < MIN_AMMO_FOR_SENTINEL:
        return False
    core_tiles = {(enemy_core[0] + dx, enemy_core[1] + dy)
                  for dx in (0, 1) for dy in (0, 1)}
    # Plan against known terrain: with an atlas the whole map qualifies, and
    # without one we must be close enough to have seen the Core's surrounds,
    # or the "seat" may be a wall we simply have not met yet.
    if p.atlas is None and not any(tile in p.seen for tile in core_tiles):
        return False
    me = tuple(ct.get_position())
    distances = _distance_map(p, me)
    protected_lanes = _friendly_turret_lanes(ct, p)
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
                    # Threat first, then arriving soon, then the farthest seat:
                    # distance from the Core is safety the wrap does not have
                    # to buy. A siege Sentinel is 30 Ti and the most expensive
                    # thing this bot builds, so seating it in a known firing
                    # line is the worst single purchase available to it.
                    choices.append((
                        1 if _threat_at(p, spot) else 0,
                        distance, -_distance_sq(spot, core_tile),
                        spot, D8.index(facing), facing,
                    ))
    if not choices:
        return False
    _, _, _, spot, _, facing = min(choices)
    position = Position(*spot)
    if _cardinal_distance(me, spot) != 1:
        _move_cardinal_adjacent(p, ct, spot)
        return True
    if ct.can_build_sentinel(position, facing):
        ct.build_sentinel(position, facing)
        _mark_progress(p, ct, "built siege sentinel", spot)
        p.solids.add(spot)
        p.siege_sentinel = spot
        p.siege_sentinels_built += 1
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

    The gate is knowing where the enemy Core actually is, not having looked it
    up. The old test was `p.atlas is None`, which is the same thing only on the
    published pool: off it -- a generated map, the held-out evaluation set,
    whatever the final is played on -- the atlas is always None, so the whole
    relay switched itself off and the attacker walked. That is the bot's single
    largest tempo advantage (a Gunner beside the enemy Core on round 12 against
    Pantheon's 32) disabled precisely where nobody had tuned against us, and it
    is most of why `ragnarok_fair` sits five places below `ragnarok`.

    `sighted` is already the flag for this: the store carries it set when the
    atlas supplied the Core *or* when a unit has physically seen it, and clear
    when the position is only the symmetry inference's best guess. Ferrying at
    a guess is what the original gate was right to refuse -- a wrong throw
    spends a Launcher and puts the attacker further from the real Core than it
    started -- so the guess still walks.
    """
    if not (sighted or p.atlas is not None or FERRY_ON_INFERENCE):
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
        return _request_launch(p, ct, target, adjacent[1])

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
    protected_lanes = _friendly_turret_lanes(ct, p)
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
                # Refused outright: this search already ranges over every tile
                # within 3 of the enemy Core, so if one of them is covered
                # there are dozens that are not, and walking to one costs a
                # couple of rounds against a turret that dies for nothing.
                if distance is not None and not _threat_at(p, spot):
                    choices.append((distance, spot, D8.index(facing), facing))
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
    _, spot, _, facing = min(choices)
    position = Position(*spot)
    if not ct.is_in_vision(position):
        _step(p, ct, position, False)
        return True
    if _cardinal_distance(me, spot) != 1:
        _move_cardinal_adjacent(p, ct, spot)
        return True
    if ct.can_build_gunner(position, facing):
        _spar_turret(ct, position, facing)
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

    Not re-entrant, and it has to say so. `_step` calls this when a Launcher
    blocks the route, this walks toward its build tile with
    `_move_cardinal_adjacent`, and that calls `_step` again -- which meets the
    same blocking Launcher and calls this again. Traced on the crash hunt: the
    cycle runs to `RecursionError('maximum recursion depth exceeded')`, the
    handler swallows it, and the Builder loses the entire turn having neither
    moved nor built. The guard turns the second entry into an ordinary "no, go
    and walk instead", which is what the outer `_step` does next anyway.
    """
    if getattr(p, "breaking_launcher", False):
        return False
    # No `try/finally` -- the engine's validator rejects `finally` blocks
    # outright. The flag is instead cleared at the top of every turn in `_run`,
    # so even a raise inside the body cannot leave the breaker wedged off for
    # the rest of the match; it loses the mechanic for one turn at most.
    p.breaking_launcher = True
    built = _breaker_gunner_body(p, ct, blocking, route)
    p.breaking_launcher = False
    return built


def _breaker_gunner_body(p, ct, blocking, route):
    if ct.get_global_ammo() < MIN_AMMO_FOR_GUNNER:
        return False
    me = tuple(ct.get_position())
    targets = sorted(p.enemy_launchers if blocking is None else blocking)
    if not targets:
        return False
    distances = _distance_map(p, me)
    protected_lanes = _friendly_turret_lanes(ct, p)
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
        _spar_turret(ct, position, facing)
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


def _friendly_turret_lanes(ct, p=None):
    """Map protected firing-ray tiles to the friendly turret and its target.

    Cached for the turn like `_travel`, and for the same reason: the seat
    searches call it once each and the siege search calls it again, all inside
    one `run()`, and it walks every nearby building against every nearby enemy
    to rebuild the identical answer.
    """
    if p is not None:
        if getattr(p, "lanes_cache_round", None) == getattr(p, "round", -1):
            return p.lanes_cache
        p.lanes_cache_round = getattr(p, "round", -1)
    lanes = {}
    enemies = [
        entity_id for entity_id in ct.get_nearby_entities()
        if ct.get_team(entity_id) != ct.get_team()
    ]
    if not enemies:
        if p is not None:
            p.lanes_cache = lanes
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
    if p is not None:
        p.lanes_cache = lanes
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
