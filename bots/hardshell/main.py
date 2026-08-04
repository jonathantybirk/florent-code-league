"""Hardshell bot -- pure defensive/economy (turtle) strategy.

Never attacks the enemy Core. Builds a Sentinel-anchored perimeter around
our own Core, harvests every ore tile inside that perimeter, and wins on the
round-1000 tiebreaker (most titanium collected, then most harvesters, then
most titanium stored -- see game-rules-overview.txt) instead of by
destroying anything.

Single-file, modeled on bots/green/main.py's style (one Player class,
dispatch by EntityType) rather than bots/strategist's pluggable-strategy
layout -- there's only one strategy here, so there's nothing to plug.
"""

from __future__ import annotations

import random

from fcode import Controller, Direction, EntityType, Environment, Position, Team

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

# --- Communication store slots (16 u32 slots, shared by the team) ---
SLOT_CORE_X = 0
SLOT_CORE_Y = 1
SLOT_HARVESTER_COUNT = 2
SLOT_SENTINEL_COUNT = 3
SLOT_GUNNER_COUNT = 4
SLOT_ORE_LOCATION = 5
SLOT_BARRIER_COUNT = 6
SLOT_THREAT_LEVEL = 7
SLOT_MAX_BUILDERS = 8

# Dynamic workforce cap: grows with confirmed harvester count (more
# harvesters justify more hands), capped outright at ABSOLUTE_MAX_BUILDERS
# and frozen (not shrunk -- no reliable live-count signal exists yet; that's
# a job for a future liveness protocol) once SCALE_EXPANSION_CEILING makes
# further growth not worth its cost. get_scale_percent() returns 100.0 at
# baseline (confirmed empirically -- its own docstring example elsewhere
# says "1.0 with nothing built", which does not match observed behavior),
# so the ceiling below is in those same 100=baseline units.
BASE_BUILDERS = 4
BUILDERS_PER_HARVESTER = 1
ABSOLUTE_MAX_BUILDERS = 16
SCALE_EXPANSION_CEILING = 400.0

# Turrets (10-20% scale each) are far more expensive to the shared cost
# scale than harvesters (5%) -- without this gate, bots whose own vision
# happens to be ore-free default to turret-building the moment they reach
# the ring, well before the team has enough harvesters to afford it, and
# the scale spike starves the economy for the rest of the match. Only
# start the ring once the economy has a base, or once there's genuinely no
# more known ore left to claim.
#
# SLOT_HARVESTER_COUNT alone turns out not to be a reliable signal for
# "enough harvesters exist": multiple bots building one in the same round
# each read the same stale pre-round count and increment from it, so
# simultaneous builds silently undercount (the same class of bug already
# worked around for turret counts in _try_build_turret). Measured on
# `vault`: a match with real, substantial harvester income (2190 titanium
# collected) still showed SLOT_HARVESTER_COUNT==0 at round 900. And ore
# genuinely never "runs out" within economic_zone on a large, ore-rich map
# within a normal match length, so that escape hatch alone doesn't reliably
# open the gate either -- between the two, the ring was very likely never
# forming on big maps at all, Stage 2 or not. A round-count floor is the
# one signal here that can't be wrong: it doesn't depend on the store --
# but only worth using once SLOT_THREAT_LEVEL says there's an actual enemy
# to build it for. Against a non-aggressive opponent, more harvesters is
# strictly the better use of titanium than turrets that never fire a shot
# at anything (measured: an unconditional round trigger cost hardshell an
# otherwise-comfortable win against bots/green, 1280 Ti vs green's 7759 --
# same lesson as EARLY_GUARDS needing to be threat-gated, applied here).
TARGET_HARVESTERS = 4
RING_START_ROUND = 150

# Rush defense: a Gunner right at the Core answers an attacker within a
# couple of rounds of it arriving, instead of waiting for TARGET_HARVESTERS
# -- measured against bots/luc/heimdall's default "rush" doctrine, which
# reliably destroys an undefended Core by round ~30-40 (heimdall's own
# design docs describe this exact exploit: answering an attacker on sighting
# rather than after the Core has already taken damage). Tight radius, well
# inside the ring band, so it's checked and built before any economy move.
HOME_GUARD_RADIUS_SQ = 8

# Two competing measurements: a flat high guard count is a bad trade against
# a non-rushing opponent (5 permanent Gunners cost hardshell an otherwise-
# comfortable win against bots/green -- 50 Ti plus a standing +50% scale
# penalty for the *entire match*), but dropping the *baseline* down and
# escalating reactively off SLOT_THREAT_LEVEL (Core's own vision, r^2=36,
# sighting an enemy) was too slow against bots/luc/heimdall's rush --
# detection only fires once the attacker is already within Core vision,
# too little lead time to erect 3 more Gunners (round ~34-37, same as no
# escalation at all). The baseline itself has to be strong enough on its
# own; reactive escalation only adds *more* on top of that for a sustained
# siege, it can't substitute for it.
BASE_EARLY_GUARDS = 4
ELEVATED_EARLY_GUARDS = 6
THREAT_DECAY_ROUNDS = 30

# Minimum spacing between turrets so bots don't clump them onto one tile.
TURRET_SPACING_SQ = 5

# Gunner's own vision/attack radius^2 (game-rules-turrets.txt) -- the range
# within which rotating to face a sighted enemy can actually pay off.
GUNNER_ATTACK_RADIUS_SQ = 13

# Roughly one reload's worth of ammo per turret, sentinel-weighted for its
# higher per-shot cost (10 vs Gunner's 2).
AMMO_PER_SENTINEL = 10
AMMO_PER_GUNNER = 4
# Titanium the Core won't spend on ammo, so harvester/turret construction
# stays funded even while topping up the ammo pool.
TITANIUM_RESERVE = 40


def pack_pos(pos: Position) -> int:
    """Encode a position into a single u32 for the communication store.

    Offset by +1 so that (0, 0) doesn't encode as 0, which is reserved to
    mean "no data".
    """
    return ((pos.x + 1) << 16) | (pos.y + 1)


def unpack_pos(val: int) -> Position | None:
    if val == 0:
        return None
    return Position((val >> 16) - 1, (val & 0xFFFF) - 1)


def in_bounds(ct: Controller, pos: Position) -> bool:
    return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()


class Player:
    def __init__(self):
        self.num_spawned = 0
        # Core-side only: see _update_max_builders.
        self.max_builders = BASE_BUILDERS

        self.core_pos: Position | None = None
        self.target: Position | None = None
        self.last_pos: Position | None = None
        self.stuck = 0

        # Computed once from map dimensions -- see _compute_home_radius.
        self.home_radius_sq: float | None = None
        self.ring_min_sq: float = 0.0
        self.ring_max_sq: float = 0.0
        self.enemy_ward: Direction | None = None

        # Set right after this bot builds a Sentinel -- the tile directly
        # outward of it, to be shielded with a Barrier. See _try_build_shield.
        self.pending_shield: Position | None = None

    def run(self, ct: Controller) -> None:
        # An uncaught exception here permanently kills this unit for the
        # rest of the match (confirmed the hard way: get_tile_building_id()
        # raising "Position out of vision range" on an out-of-range query
        # silently wiped out most of the team before this guard existed).
        # One bad round on one unit should never cost more than that round.
        try:
            self._run(ct)
        except Exception:
            pass

    def _run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self._run_core(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._run_builder(ct)
        elif etype == EntityType.GUNNER:
            self._run_gunner(ct)
        elif etype == EntityType.SENTINEL:
            self._run_sentinel(ct)

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def _run_core(self, ct: Controller) -> None:
        pos = ct.get_position()
        ct.write_store(SLOT_CORE_X, pos.x)
        ct.write_store(SLOT_CORE_Y, pos.y)

        self._update_threat_level(ct)
        self._update_max_builders(ct)
        self._maybe_convert_ammo(ct)

        if self.num_spawned >= self.max_builders:
            return
        ti = ct.get_global_resources()
        cost = ct.get_builder_bot_cost()
        if ti < cost:
            return

        dirs = list(DIRECTIONS)
        random.shuffle(dirs)
        for d in dirs:
            spawn_pos = pos.add(d)
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                self.num_spawned += 1
                return

    def _update_max_builders(self, ct: Controller) -> None:
        # SLOT_HARVESTER_COUNT undercounts (see the TARGET_HARVESTERS
        # comment) but is monotonic-ish and only used here to loosely scale
        # workforce, not to gate a hard decision -- an undercount just means
        # growing a little more conservatively than the true harvester count
        # would justify, which is fine for a cost-aware cap. Frozen (not
        # shrunk) past the scale ceiling: there's no reliable live-builder-
        # count signal yet to shrink toward, only a cumulative
        # ever-spawned one (self.num_spawned).
        if ct.get_scale_percent() >= SCALE_EXPANSION_CEILING:
            ct.write_store(SLOT_MAX_BUILDERS, self.max_builders)
            return
        harvester_count = ct.read_store(SLOT_HARVESTER_COUNT)
        self.max_builders = min(ABSOLUTE_MAX_BUILDERS, BASE_BUILDERS + BUILDERS_PER_HARVESTER * harvester_count)
        ct.write_store(SLOT_MAX_BUILDERS, self.max_builders)

    def _update_threat_level(self, ct: Controller) -> None:
        # Core's own vision (r^2=36) comfortably covers HOME_GUARD_RADIUS_SQ
        # and then some -- cheap early warning with no extra scanning. Any
        # enemy unit sighted refreshes the decay window; builders read this
        # to decide whether the home guard should be at its cheap baseline
        # or temporarily reinforced.
        my_team = ct.get_team()
        sighted = any(ct.get_team(uid) != my_team for uid in ct.get_nearby_units())
        level = THREAT_DECAY_ROUNDS if sighted else max(0, ct.read_store(SLOT_THREAT_LEVEL) - 1)
        ct.write_store(SLOT_THREAT_LEVEL, level)

    def _maybe_convert_ammo(self, ct: Controller) -> None:
        sentinel_count = ct.read_store(SLOT_SENTINEL_COUNT)
        gunner_count = ct.read_store(SLOT_GUNNER_COUNT)
        ammo_target = AMMO_PER_SENTINEL * sentinel_count + AMMO_PER_GUNNER * gunner_count
        if ammo_target <= 0 or ct.get_global_ammo() >= ammo_target:
            return

        spendable = ct.get_global_resources() - TITANIUM_RESERVE
        if spendable <= 0:
            return

        amount = min(spendable, ammo_target - ct.get_global_ammo())
        if amount > 0 and ct.can_convert_ammo(amount):
            ct.convert_ammo(amount)

    # ------------------------------------------------------------------
    # Builder bot
    # ------------------------------------------------------------------

    def _run_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        if self.core_pos is None:
            self._read_core_pos(ct)
        if self.home_radius_sq is None and self.core_pos is not None:
            self._compute_home_radius(ct, self.core_pos)

        if self.last_pos == pos:
            self.stuck += 1
        else:
            self.stuck = 0
        self.last_pos = pos

        if ct.get_action_cooldown() == 0:
            if not self._try_build_shield(ct):
                if not self._try_build_home_guard(ct):
                    if not self._try_heal(ct):
                        if not self._try_build_harvester(ct):
                            harvester_count = ct.read_store(SLOT_HARVESTER_COUNT)
                            threatened = ct.read_store(SLOT_THREAT_LEVEL) > 0
                            ring_unlocked = (
                                harvester_count >= TARGET_HARVESTERS
                                or (threatened and ct.get_current_round() >= RING_START_ROUND)
                                or self._pick_ore_target(ct) is None
                            )
                            if ring_unlocked:
                                self._try_build_turret(ct)

        self._move_toward_target(ct)
        self._share_ore(ct)

    def _read_core_pos(self, ct: Controller) -> None:
        x = ct.read_store(SLOT_CORE_X)
        y = ct.read_store(SLOT_CORE_Y)
        if x > 0 or y > 0:
            self.core_pos = Position(x, y)

    def _compute_home_radius(self, ct: Controller, core_pos: Position) -> None:
        w, h = ct.get_map_width(), ct.get_map_height()
        radius = max(min(w, h) * 0.4, 4.0)
        self.home_radius_sq = radius * radius
        # Ring band for turret placement: inside the perimeter, but far
        # enough out to clear the Core's spawn ring (dist_sq<=2).
        self.ring_min_sq = max(8.0, self.home_radius_sq * 0.25)
        self.ring_max_sq = max(self.ring_min_sq + 1.0, self.home_radius_sq * 0.9)

        # Rough "where the enemy probably is" direction from round-0
        # information only -- no map oracle. Maps are symmetric (mirrored
        # or 180-degree rotated), and the Core's footprint is 2x2 with
        # get_position() reporting its NW cell, so the far edges sit at
        # width-2/height-2 (same insight bots/luc/heimdall's doctrine.py
        # uses for its own opening choice). This is only ever a heuristic
        # compass direction, not a real position estimate.
        mirror = Position(w - 2 - core_pos.x, h - 2 - core_pos.y)
        self.enemy_ward = core_pos.direction_to(mirror)

    def _in_home(self, pos: Position) -> bool:
        # True boundary of the defended area -- used for build eligibility
        # (turret/barrier/harvester placement), including the outward
        # build tile one step past a ring-band bot, which needs this looser
        # bound to be buildable at all.
        return self.core_pos is not None and pos.distance_squared(self.core_pos) <= self.home_radius_sq

    def _in_economic_zone(self, pos: Position) -> bool:
        # Tighter than _in_home: ore-seeking and idle patrol use this so
        # bots never chase resources, or wander, past ring_max_sq -- once
        # the ring/barrier line goes up along that band, anything beyond it
        # would be economically stranded (no route back to the Core without
        # crossing our own wall). Keeps every harvester/conveyor a bot ever
        # needs entirely on the inside of where barriers get built.
        return self.core_pos is not None and pos.distance_squared(self.core_pos) <= self.ring_max_sq

    def _try_build_shield(self, ct: Controller) -> bool:
        # Completes the ambush pairing from _try_build_turret: a Barrier
        # directly outward of a Sentinel we just built. _run_sentinel
        # already skips friendly-occupied tiles by team, so it fires straight
        # past its own Barrier at whatever's beyond -- the Barrier's job is
        # purely to block a Gunner's line and a Builder Bot's approach,
        # protecting the Sentinel itself.
        #
        # The shield tile is rarely adjacent to where the bot is standing
        # right after building the Sentinel (the Sentinel's facing can be
        # diagonal, unlike the orthogonal step to place it), so this can't
        # just be a one-shot attempt -- _pick_target routes the bot there
        # first (see below) and this gets checked every round until it
        # either succeeds or turns out to be unbuildable.
        if self.pending_shield is None:
            return False
        if not self._in_home(self.pending_shield):
            self.pending_shield = None
            return False
        if ct.can_build_barrier(self.pending_shield):
            ct.build_barrier(self.pending_shield)
            ct.write_store(SLOT_BARRIER_COUNT, ct.read_store(SLOT_BARRIER_COUNT) + 1)
            self.pending_shield = None
            self.target = None
            return True
        # Orthogonally adjacent and still can't build it (occupied by
        # something else, most likely) -- no amount of waiting fixes that.
        if ct.get_position().distance_squared(self.pending_shield) <= 1:
            self.pending_shield = None
        return False

    def _try_build_home_guard(self, ct: Controller) -> bool:
        # Checked first, every round, ahead of healing/harvesting/the ring --
        # rush defense before expansion. Self-healing like _turret_nearby
        # (no store counter): a lost guard gets replaced by the next bot
        # that passes within HOME_GUARD_RADIUS_SQ, since we only count
        # what's actually alive right now, not a cumulative total.
        if self.core_pos is None:
            return False
        pos = ct.get_position()
        if pos.distance_squared(self.core_pos) > HOME_GUARD_RADIUS_SQ:
            return False
        guard_count = self._count_home_guards(ct, self.core_pos)
        guard_target = ELEVATED_EARLY_GUARDS if ct.read_store(SLOT_THREAT_LEVEL) > 0 else BASE_EARLY_GUARDS
        if guard_count >= guard_target:
            return False
        if ct.get_global_resources() < ct.get_gunner_cost():
            return False

        # Spread facings around the compass (step by 2 through the
        # 8-direction list, so the first 4 guards land on the 4 cardinals
        # rather than 4 clustered adjacent directions -- a 5th wraps and
        # doubles up on one, which is fine, it's a bonus past the base
        # count anyway) -- we have no information about which way an
        # attacker will come from.
        facing = DIRECTIONS[(guard_count * 2) % len(DIRECTIONS)]
        for d in Direction:
            build_pos = pos.add(d)
            if self._in_home(build_pos) and ct.can_build_gunner(build_pos, facing):
                ct.build_gunner(build_pos, facing)
                ct.write_store(SLOT_GUNNER_COUNT, ct.read_store(SLOT_GUNNER_COUNT) + 1)
                self.target = None
                return True
        return False

    def _count_home_guards(self, ct: Controller, core_pos: Position) -> int:
        my_team = ct.get_team()
        count = 0
        for bid in ct.get_nearby_buildings():
            if ct.get_entity_type(bid) != EntityType.GUNNER:
                continue
            if ct.get_team(bid) != my_team:
                continue
            if ct.get_position(bid).distance_squared(core_pos) <= HOME_GUARD_RADIUS_SQ:
                count += 1
        return count

    def _try_heal(self, ct: Controller) -> bool:
        pos = ct.get_position()
        for d in Direction:
            check = pos.add(d)
            if ct.can_heal(check):
                ct.heal(check)
                return True
        return False

    def _try_build_harvester(self, ct: Controller) -> bool:
        if self.core_pos is None:
            return False
        ti = ct.get_global_resources()
        cost = ct.get_harvester_cost()
        if ti < cost:
            return False
        pos = ct.get_position()
        for d in Direction:
            build_pos = pos.add(d)
            if not self._in_home(build_pos):
                continue
            if ct.can_build_harvester(build_pos):
                ct.build_harvester(build_pos)
                count = ct.read_store(SLOT_HARVESTER_COUNT)
                ct.write_store(SLOT_HARVESTER_COUNT, count + 1)
                self._try_build_conveyor_toward_core(ct, build_pos)
                self.target = None
                return True
        return False

    def _try_build_conveyor_toward_core(self, ct: Controller, harvester_pos: Position) -> None:
        if self.core_pos is None:
            return
        ti = ct.get_global_resources()
        cost = ct.get_conveyor_cost()
        if ti < cost:
            return
        toward_core = harvester_pos.direction_to(self.core_pos)
        if toward_core == Direction.CENTRE:
            return
        facing = _nearest_cardinal(toward_core)
        conv_pos = harvester_pos.add(facing)
        if ct.can_build_conveyor(conv_pos, facing):
            ct.build_conveyor(conv_pos, facing)

    def _try_build_turret(self, ct: Controller) -> bool:
        if self.core_pos is None:
            return False
        pos = ct.get_position()
        dist_sq = pos.distance_squared(self.core_pos)
        if not (self.ring_min_sq <= dist_sq <= self.ring_max_sq):
            return False
        if self._turret_nearby(ct, pos):
            return False

        # Face straight outward from the core -- diagonals are valid turret
        # facings (unlike conveyors/splitters), so this naturally spreads
        # the ring across all 8 compass lanes as bots approach from
        # different angles.
        facing = pos.direction_to(self.core_pos).opposite()
        if facing == Direction.CENTRE:
            facing = random.choice(DIRECTIONS)

        # No global target counter here on purpose: a store-based count can
        # only ever go up (there's no reliable per-unit signal for "my
        # turret just died"), so gating on it would permanently lock the
        # ring at whatever peak count it once reached and block rebuilding
        # after combat losses. Instead the ring self-limits on the spacing
        # check above -- an open, correctly-spaced slot is always fair game.
        # Sentinel is the default (long unblockable range is the point of
        # this bot); Gunner is only a fallback when Sentinel isn't
        # affordable yet but Gunner is, so a cheap placeholder still goes up.
        if ct.get_global_resources() >= ct.get_sentinel_cost():
            build_pos = self._try_build_one_turret(
                ct, pos, facing, ct.can_build_sentinel, ct.build_sentinel, SLOT_SENTINEL_COUNT
            )
            if build_pos is not None:
                # Ambush pairing (see _try_build_shield): shield the tile
                # directly outward of the Sentinel we just placed.
                self.pending_shield = build_pos.add(facing)
            return build_pos is not None
        build_pos = self._try_build_one_turret(
            ct, pos, facing, ct.can_build_gunner, ct.build_gunner, SLOT_GUNNER_COUNT
        )
        return build_pos is not None

    def _try_build_one_turret(self, ct: Controller, pos, facing, can_build, build, slot) -> Position | None:
        for d in Direction:
            build_pos = pos.add(d)
            if self._in_home(build_pos) and can_build(build_pos, facing):
                build(build_pos, facing)
                ct.write_store(slot, ct.read_store(slot) + 1)
                self.target = None
                return build_pos
        return None

    def _turret_nearby(self, ct: Controller, pos: Position) -> bool:
        my_team = ct.get_team()
        for bid in ct.get_nearby_buildings():
            if ct.get_entity_type(bid) not in (EntityType.SENTINEL, EntityType.GUNNER):
                continue
            if ct.get_team(bid) != my_team:
                continue
            if pos.distance_squared(ct.get_position(bid)) <= TURRET_SPACING_SQ:
                return True
        return False

    # -- movement --

    def _move_toward_target(self, ct: Controller) -> None:
        if ct.get_move_cooldown() != 0:
            return
        pos = ct.get_position()
        if self.target is None or pos == self.target or self.stuck >= 3:
            self.target = self._pick_target(ct)
            self.stuck = 0
        if self.target is None:
            return
        desired = pos.direction_to(self.target)
        if desired == Direction.CENTRE:
            return
        primary = [desired, desired.rotate_left(), desired.rotate_right()]
        for d in primary:
            if self._try_move(ct, d):
                return
        remaining = [d for d in DIRECTIONS if d not in primary]
        random.shuffle(remaining)
        for d in remaining:
            if self._try_move(ct, d):
                return

    def _try_move(self, ct: Controller, d: Direction) -> bool:
        # A Harvester only relays its output one tile per round to an
        # adjacent building -- getting titanium all the way back to the
        # Core needs an actual conveyor chain, not just the single relay tile
        # _try_build_conveyor_toward_core drops next to the harvester. Rather
        # than a dedicated router, lay one more link toward the core on
        # whatever empty tile a bot is about to step onto anyway (same
        # opportunistic pattern bots/green and bots/strategist use) -- over
        # many rounds of ordinary harvesting/ring-building/patrol traffic
        # this incidentally stitches a connected network back to the Core.
        # Building consumes this round's action (blocking the move), so a
        # bot alternates lay-a-segment / walk-onto-it-next-round as it goes.
        pos = ct.get_position()
        next_pos = pos.add(d)
        # in_bounds first -- is_tile_empty raises GameError off-map, unlike
        # can_move/can_build_conveyor which just return False.
        if self.core_pos is not None and in_bounds(ct, next_pos) and ct.is_tile_empty(next_pos):
            cardinal = _nearest_cardinal(next_pos.direction_to(self.core_pos))
            if ct.can_build_conveyor(next_pos, cardinal):
                ct.build_conveyor(next_pos, cardinal)
        if ct.can_move(d):
            ct.move(d)
            return True
        return False

    def _pick_target(self, ct: Controller) -> Position | None:
        if self.core_pos is None:
            return None

        # Finishing a pending ambush shield takes priority over everything
        # else this bot would otherwise do -- it's a cheap, short errand
        # (see _try_build_shield), not worth abandoning for a fresh ore/ring
        # target just because it isn't reachable in one step yet.
        if self.pending_shield is not None:
            return self.pending_shield

        ore = self._pick_ore_target(ct)
        if ore is not None:
            return ore

        slot = self._pick_turret_slot(ct)
        if slot is not None:
            return slot

        # Perimeter and economy both maxed out -- patrol inside the home
        # radius so idle bots stay on hand as roving healers.
        for _ in range(8):
            candidate = self._random_home_point(ct)
            if candidate is not None:
                return candidate
        return self.core_pos

    def _pick_ore_target(self, ct: Controller) -> Position | None:
        pos = ct.get_position()
        best = None
        best_dist = float("inf")
        for tile in ct.get_nearby_tiles():
            if ct.get_tile_env(tile) != Environment.ORE_TITANIUM:
                continue
            if ct.get_tile_building_id(tile) is not None:
                continue
            if not self._in_economic_zone(tile):
                continue
            d = pos.distance_squared(tile)
            if d < best_dist:
                best_dist = d
                best = tile
        if best is not None:
            return best

        # Nothing in our own (builder-bot-sized) vision -- fall back to ore
        # a teammate has already spotted elsewhere in the home area, so the
        # harvester gate below isn't tripped early just because this one
        # bot's local view happens to be ore-free.
        #
        # Tile queries aren't vision-scoped (unlike get_nearby_*), so this
        # can double-check the shared tile is still actually unclaimed even
        # from here -- essential, since nothing ever clears
        # SLOT_ORE_LOCATION otherwise. Without this check, once the last
        # visible ore tile anywhere gets a Harvester built on it, the store
        # keeps pointing at that now-claimed tile forever (no bot's own
        # vision ever finds anything to overwrite it with), which
        # permanently poisons the "ore genuinely exhausted" signal
        # _run_builder's harvester gate depends on to ever unlock the ring
        # -- measured: zero Sentinels built in 700 rounds on `duel` before
        # this fix, every builder stuck treating phantom ore as still
        # pending.
        #
        # get_tile_building_id() turns out to *not* be usable at arbitrary
        # range despite nothing in its docstring saying so -- it raised
        # "Position out of vision range" for a shared tile outside this
        # bot's own vision and permanently killed the unit (no exception
        # guard existed before this was found -- see run()). Only
        # re-verify when the tile happens to be in vision right now;
        # otherwise trust the shared value as-is, same residual staleness
        # risk as before, but never a query outside what's actually safe.
        shared = unpack_pos(ct.read_store(SLOT_ORE_LOCATION))
        if shared is not None and self._in_economic_zone(shared) and pos.distance_squared(shared) > 4:
            if not ct.is_in_vision(shared) or ct.get_tile_building_id(shared) is None:
                return shared
        return None

    def _share_ore(self, ct: Controller) -> None:
        for tile in ct.get_nearby_tiles():
            if ct.get_tile_env(tile) != Environment.ORE_TITANIUM:
                continue
            if ct.get_tile_building_id(tile) is not None:
                continue
            if not self._in_economic_zone(tile):
                continue
            ct.write_store(SLOT_ORE_LOCATION, pack_pos(tile))
            return

    def _pick_turret_slot(self, ct: Controller) -> Position | None:
        # No target-count cap here: since destroyed turrets never get
        # decremented from the store counters (see _try_build_turret), a
        # cap would eventually stop bots from ever pathing back to the ring
        # to replace combat losses. Worst case, once the ring really is
        # full, a bot just walks to an occupied slot, fails to build, and
        # picks a new target next round -- a little wasted movement, not a
        # correctness problem.
        #
        # Just point at a ring slot in a random compass direction -- this is
        # only a walking target, not a build decision. get_nearby_buildings()
        # is centered on this bot, not on the candidate tile, so a spacing
        # check here would be meaningless; the real spacing/legality check
        # happens in _try_build_turret once the bot actually arrives.
        ring = int(((self.ring_min_sq + self.ring_max_sq) / 2) ** 0.5)

        # Lean toward the enemy-facing arc (see _compute_home_radius):
        # that's where a Sentinel's reach actually matters -- hitting their
        # lane/conveyors, not empty terrain -- and where an ambush shield is
        # worth pairing with one. Not a hard order: a failed build attempt
        # here just re-picks a target next round anyway (see
        # _try_build_turret), so this is a strong lean, not a permanent
        # claim that could starve the rest of the ring.
        if self.enemy_ward is not None:
            enemy_arc = [self.enemy_ward, self.enemy_ward.rotate_left(), self.enemy_ward.rotate_right()]
        else:
            enemy_arc = []
        other_arc = [d for d in DIRECTIONS if d not in enemy_arc]
        random.shuffle(enemy_arc)
        random.shuffle(other_arc)
        dirs = enemy_arc + other_arc if random.random() < 0.7 else other_arc + enemy_arc

        for d in dirs:
            dx, dy = d.delta()
            candidate = Position(self.core_pos.x + dx * ring, self.core_pos.y + dy * ring)
            if in_bounds(ct, candidate):
                return candidate
        return None

    def _random_home_point(self, ct: Controller) -> Position | None:
        if self.core_pos is None:
            return None
        radius = int(self.ring_max_sq**0.5)
        if radius <= 0:
            return None
        dx = random.randint(-radius, radius)
        dy = random.randint(-radius, radius)
        candidate = Position(self.core_pos.x + dx, self.core_pos.y + dy)
        if not in_bounds(ct, candidate):
            return None
        if not self._in_economic_zone(candidate):
            return None
        return candidate

    # ------------------------------------------------------------------
    # Gunner
    # ------------------------------------------------------------------

    def _run_gunner(self, ct: Controller) -> None:
        # get_gunner_target()/can_fire() aren't team-aware -- they'll happily
        # return a friendly Builder Bot standing in the firing line (nothing
        # in the API docs restricts fire() to enemies, unlike heal(), which
        # is explicitly friendly-only). Must filter by team ourselves, same
        # as _run_sentinel below.
        my_team = ct.get_team()
        target = ct.get_gunner_target()
        if target is not None:
            building_id = ct.get_tile_building_id(target)
            bot_id = ct.get_tile_builder_bot_id(target)
            occupant = building_id if building_id is not None else bot_id
            if occupant is not None and ct.get_team(occupant) != my_team:
                if ct.can_fire(target):
                    ct.fire(target)
                return

        # Nothing to shoot on the current facing this round -- try to turn
        # toward the nearest sighted enemy instead of sitting blind. Only
        # reached when firing this round was never on the table anyway (no
        # target at all), so this never trades away a shot we could have
        # taken. An earlier version rotated whenever the facing lacked a
        # *kill* (including "blocked by an ally" or "out of ammo") and
        # measured worse against heimdall (round 36/53/32 vs 63/77/65) --
        # it kept re-turning away from a lane that would have cleared on its
        # own next round. Gating strictly on "no target at all" avoids that.
        self._maybe_rotate_to_enemy(ct, my_team)

    def _maybe_rotate_to_enemy(self, ct: Controller, my_team: Team) -> None:
        pos = ct.get_position()
        best: Position | None = None
        best_dist = float("inf")
        for uid in ct.get_nearby_units(dist_sq=GUNNER_ATTACK_RADIUS_SQ):
            if ct.get_team(uid) == my_team:
                continue
            d = pos.distance_squared(ct.get_position(uid))
            if d < best_dist:
                best_dist, best = d, ct.get_position(uid)
        for bid in ct.get_nearby_buildings(dist_sq=GUNNER_ATTACK_RADIUS_SQ):
            if ct.get_team(bid) == my_team:
                continue
            bpos = ct.get_position(bid)
            d = pos.distance_squared(bpos)
            if d < best_dist:
                best_dist, best = d, bpos
        if best is None:
            return
        desired = pos.direction_to(best)
        if desired == Direction.CENTRE or desired == ct.get_direction():
            return
        if ct.can_rotate(desired):
            ct.rotate(desired)

    # ------------------------------------------------------------------
    # Sentinel
    # ------------------------------------------------------------------

    def _run_sentinel(self, ct: Controller) -> None:
        # No get_sentinel_target() exists (unlike Gunner) -- scan the raw
        # attack line ourselves for the first enemy-occupied tile.
        my_team = ct.get_team()
        for tile in ct.get_attackable_tiles():
            building_id = ct.get_tile_building_id(tile)
            bot_id = ct.get_tile_builder_bot_id(tile)
            occupant = building_id if building_id is not None else bot_id
            if occupant is None or ct.get_team(occupant) == my_team:
                continue
            if ct.can_fire(tile):
                ct.fire(tile)
                return


def _nearest_cardinal(d: Direction) -> Direction:
    """Snap any direction to the nearest cardinal direction.

    Conveyors can only face cardinal directions (N/E/S/W).
    """
    return {
        Direction.NORTH: Direction.NORTH,
        Direction.NORTHEAST: Direction.NORTH,
        Direction.EAST: Direction.EAST,
        Direction.SOUTHEAST: Direction.EAST,
        Direction.SOUTH: Direction.SOUTH,
        Direction.SOUTHWEST: Direction.SOUTH,
        Direction.WEST: Direction.WEST,
        Direction.NORTHWEST: Direction.WEST,
        Direction.CENTRE: Direction.NORTH,
    }[d]
