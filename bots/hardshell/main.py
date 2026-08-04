"""Turtle bot -- pure defensive/economy strategy.

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

from fcode import Controller, Direction, EntityType, Environment, Position

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]

# --- Communication store slots (16 u32 slots, shared by the team) ---
SLOT_CORE_X = 0
SLOT_CORE_Y = 1
SLOT_HARVESTER_COUNT = 2
SLOT_SENTINEL_COUNT = 3
SLOT_GUNNER_COUNT = 4
SLOT_ORE_LOCATION = 5

MAX_BUILDERS = 8

# Turrets (10-20% scale each) are far more expensive to the shared cost
# scale than harvesters (5%) -- without this gate, bots whose own vision
# happens to be ore-free default to turret-building the moment they reach
# the ring, well before the team has enough harvesters to afford it, and
# the scale spike starves the economy for the rest of the match. Only
# start the ring once the economy has a base, or once there's genuinely no
# more known ore left to claim.
TARGET_HARVESTERS = 4

# Minimum spacing between turrets so bots don't clump them onto one tile.
TURRET_SPACING_SQ = 5

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

        self.core_pos: Position | None = None
        self.target: Position | None = None
        self.last_pos: Position | None = None
        self.stuck = 0

        # Computed once from map dimensions -- see _compute_home_radius.
        self.home_radius_sq: float | None = None
        self.ring_min_sq: float = 0.0
        self.ring_max_sq: float = 0.0

    def run(self, ct: Controller) -> None:
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

        self._maybe_convert_ammo(ct)

        if self.num_spawned >= MAX_BUILDERS:
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
            self._compute_home_radius(ct)

        if self.last_pos == pos:
            self.stuck += 1
        else:
            self.stuck = 0
        self.last_pos = pos

        if ct.get_action_cooldown() == 0:
            if not self._try_heal(ct):
                if not self._try_build_harvester(ct):
                    harvester_count = ct.read_store(SLOT_HARVESTER_COUNT)
                    if harvester_count >= TARGET_HARVESTERS or self._pick_ore_target(ct) is None:
                        self._try_build_turret(ct)

        self._move_toward_target(ct)
        self._share_ore(ct)

    def _read_core_pos(self, ct: Controller) -> None:
        x = ct.read_store(SLOT_CORE_X)
        y = ct.read_store(SLOT_CORE_Y)
        if x > 0 or y > 0:
            self.core_pos = Position(x, y)

    def _compute_home_radius(self, ct: Controller) -> None:
        w, h = ct.get_map_width(), ct.get_map_height()
        radius = max(min(w, h) * 0.4, 4.0)
        self.home_radius_sq = radius * radius
        # Ring band for turret placement: inside the perimeter, but far
        # enough out to clear the Core's spawn ring (dist_sq<=2).
        self.ring_min_sq = max(8.0, self.home_radius_sq * 0.25)
        self.ring_max_sq = max(self.ring_min_sq + 1.0, self.home_radius_sq * 0.9)

    def _in_home(self, pos: Position) -> bool:
        return self.core_pos is not None and pos.distance_squared(self.core_pos) <= self.home_radius_sq

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
            return self._try_build_one_turret(
                ct, pos, facing, ct.can_build_sentinel, ct.build_sentinel, SLOT_SENTINEL_COUNT
            )
        return self._try_build_one_turret(
            ct, pos, facing, ct.can_build_gunner, ct.build_gunner, SLOT_GUNNER_COUNT
        )

    def _try_build_one_turret(self, ct: Controller, pos, facing, can_build, build, slot) -> bool:
        for d in Direction:
            build_pos = pos.add(d)
            if self._in_home(build_pos) and can_build(build_pos, facing):
                build(build_pos, facing)
                ct.write_store(slot, ct.read_store(slot) + 1)
                self.target = None
                return True
        return False

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
            if not self._in_home(tile):
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
        shared = unpack_pos(ct.read_store(SLOT_ORE_LOCATION))
        if shared is not None and self._in_home(shared) and pos.distance_squared(shared) > 4:
            return shared
        return None

    def _share_ore(self, ct: Controller) -> None:
        for tile in ct.get_nearby_tiles():
            if ct.get_tile_env(tile) != Environment.ORE_TITANIUM:
                continue
            if ct.get_tile_building_id(tile) is not None:
                continue
            if not self._in_home(tile):
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
        dirs = list(DIRECTIONS)
        random.shuffle(dirs)
        for d in dirs:
            dx, dy = d.delta()
            candidate = Position(self.core_pos.x + dx * ring, self.core_pos.y + dy * ring)
            if in_bounds(ct, candidate):
                return candidate
        return None

    def _random_home_point(self, ct: Controller) -> Position | None:
        if self.home_radius_sq is None:
            return None
        radius = int(self.home_radius_sq**0.5)
        if radius <= 0:
            return None
        dx = random.randint(-radius, radius)
        dy = random.randint(-radius, radius)
        candidate = Position(self.core_pos.x + dx, self.core_pos.y + dy)
        if not in_bounds(ct, candidate):
            return None
        if candidate.distance_squared(self.core_pos) > self.home_radius_sq:
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
        target = ct.get_gunner_target()
        if target is None:
            return
        building_id = ct.get_tile_building_id(target)
        bot_id = ct.get_tile_builder_bot_id(target)
        occupant = building_id if building_id is not None else bot_id
        if occupant is None or ct.get_team(occupant) == ct.get_team():
            return
        if ct.can_fire(target):
            ct.fire(target)

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
