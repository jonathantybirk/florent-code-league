"""AutistimusPrime — Florent Code League 2026.

Design rules, every one derived from a measured engine fact (docs/ground-truth.md):

  G01/G02  titanium_collected counts ONLY stacks landing on a Core footprint tile. An unconnected
           harvester, or a chain that dead-ends one tile short, scores exactly zero.
  G05      Never route an economy chain into a turret: it eats one 10 Ti stack, scores 0, and jams the
           chain permanently. Ammo logistics is a separate branch.
  G07      Cost scaling is ONE GLOBAL scale over all entity types. A builder is +20 percentage points
           forever, so builders are rationed hard.
  G10/G11  Every turret API is team-blind. get_gunner_target() happily returns a friendly, can_fire()
           returns True on it, and firing destroys it. Check the occupant's team before every shot.
  G14      Builders cannot attack an adjacent tile at all, but CAN fire at their own tile while standing
           on an enemy conveyor/splitter. That is the only sabotage that exists.
  G23      get_tile_env() raises outside vision and an uncaught exception PERMANENTLY deletes the unit.
  G20      Units do not share module globals. Cross-unit state is the 16 store slots (1-round lag) only;
           per-unit `self` persists all 1000 rounds, so each unit carries its own map memory for free.

CHAIN CONSTRUCTION (the thing that actually wins games)

A harvester with no complete path into the Core is worth strictly less than nothing: it costs titanium,
permanently raises the global cost scale, and delivers zero. So the chain is laid BEHIND the builder as
it walks from the ore back to the Core, which makes every belt's facing exactly the direction we truly
travelled — no guessing, no broken bends:

    build harvester on ore  ->  walk one step coreward  ->  build belt on the tile just vacated,
    facing the way we walked  ->  repeat  ->  on reaching the Core, step aside once so the final tile
    is buildable, and cap it with a belt facing into the Core footprint.

Bot name is deliberate; the team knows.
"""

from fcode import Controller, Direction, EntityType, Environment, Position

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
ALL_DIRS = tuple(d for d in Direction if d != Direction.CENTRE)

# --- Communication store (16 slots, writes visible next round) ----------------
S_CORE_X = 0
S_CORE_Y = 1
S_SPAWN_ORD = 2
S_CONNECTED = 3
S_CLAIM_0 = 4
N_CLAIMS = 6
S_ENEMY_CORE = 10
S_THREAT = 11

# Each builder is +20 percentage points of GLOBAL cost scale, permanently. An economy simulation across
# all 15 maps put the optimum near 3-4; 5 costs 40 scale points for ~0.15% more mined titanium.
MAX_BUILDERS = 4
# Keep enough banked to finish a chain in flight — a half-built chain delivers exactly zero.
CHAIN_RESERVE = 45
# Budget 3ms locally against the ladder's 10ms. Reads 0 on Windows (G21), where this is advisory only.
CPU_BUDGET_US = 6000


def cardinal_of(dx, dy):
    """Snap a delta to the cardinal direction that dominates it."""
    if abs(dx) >= abs(dy):
        return Direction.EAST if dx > 0 else Direction.WEST
    return Direction.SOUTH if dy > 0 else Direction.NORTH


def pack(pos):
    return ((pos.x + 1) << 8) | (pos.y + 1)


def unpack(val):
    if val <= 0:
        return None
    return ((val >> 8) - 1, (val & 0xFF) - 1)


class Player:
    def __init__(self):
        # Core
        self.spawned = 0

        # Builder
        self.ordinal = None
        self.phase = "seek"            # seek -> harvest -> belt -> seek
        self.target_ore = None
        self.owed = None               # (Position, Direction) belt we must build on a vacated tile
        self.owed_is_final = False
        self.stuck = 0
        self.last_pos = None

        # Shared per-unit knowledge (self persists the whole match — G20)
        self.core_pos = None
        self.core_tiles = set()
        self.known_ore = set()
        self.known_walls = set()
        self.seen = set()

        self.errors = 0

    # ------------------------------------------------------------------
    # Entry point — an escaping exception permanently deletes this unit (G23)
    # ------------------------------------------------------------------

    def run(self, ct: Controller) -> None:
        try:
            etype = ct.get_entity_type()
        except Exception:
            self.errors += 1
            return
        try:
            if etype == EntityType.CORE:
                self._run_core(ct)
            elif etype == EntityType.BUILDER_BOT:
                self._run_builder(ct)
            elif etype == EntityType.GUNNER:
                self._run_gunner(ct)
            elif etype == EntityType.SENTINEL:
                self._run_sentinel(ct)
        except Exception:
            self.errors += 1

    # ------------------------------------------------------------------
    # Guarded controller access
    # ------------------------------------------------------------------

    def _in_bounds(self, ct, pos):
        try:
            return 0 <= pos.x < ct.get_map_width() and 0 <= pos.y < ct.get_map_height()
        except Exception:
            return False

    def _env(self, ct, pos):
        if not self._in_bounds(ct, pos):
            return None
        try:
            if not ct.is_in_vision(pos):
                return None
            return ct.get_tile_env(pos)
        except Exception:
            return None

    def _building_at(self, ct, pos):
        if not self._in_bounds(ct, pos):
            return None
        try:
            return ct.get_tile_building_id(pos)
        except Exception:
            return None

    def _bot_at(self, ct, pos):
        if not self._in_bounds(ct, pos):
            return None
        try:
            return ct.get_tile_builder_bot_id(pos)
        except Exception:
            return None

    def _is_enemy(self, ct, entity_id):
        if entity_id is None:
            return False
        try:
            return ct.get_team(entity_id) != ct.get_team()
        except Exception:
            return False

    def _can_act(self, ct):
        try:
            return ct.get_action_cooldown() == 0
        except Exception:
            return False

    def _can_move_now(self, ct):
        try:
            return ct.get_move_cooldown() == 0
        except Exception:
            return False

    def _cpu_left(self, ct):
        try:
            return ct.get_cpu_time_elapsed() < CPU_BUDGET_US
        except Exception:
            return True

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def _run_core(self, ct):
        pos = ct.get_position()
        self.core_pos = pos
        ct.write_store(S_CORE_X, pos.x)
        ct.write_store(S_CORE_Y, pos.y)

        if self.spawned >= MAX_BUILDERS or not self._can_act(ct):
            return
        try:
            balance = ct.get_global_resources()
            cost = ct.get_builder_bot_cost()
        except Exception:
            return
        # Finishing a chain in flight always beats starting another builder (G02).
        if balance < cost + CHAIN_RESERVE:
            return
        for d in ALL_DIRS:
            target = pos.add(d)
            try:
                if ct.can_spawn(target):
                    ct.spawn_builder(target)
                    self.spawned += 1
                    ct.write_store(S_SPAWN_ORD, ct.read_store(S_SPAWN_ORD) + 1)
                    return
            except Exception:
                continue

    # ------------------------------------------------------------------
    # Builder
    # ------------------------------------------------------------------

    def _run_builder(self, ct):
        pos = ct.get_position()

        if self.ordinal is None:
            try:
                self.ordinal = ct.read_store(S_SPAWN_ORD)
            except Exception:
                self.ordinal = 0
        if self.core_pos is None:
            try:
                x, y = ct.read_store(S_CORE_X), ct.read_store(S_CORE_Y)
                if x > 0 or y > 0:
                    self.core_pos = Position(x, y)
            except Exception:
                pass

        self._observe(ct, pos)

        if self.last_pos is not None and self.last_pos == pos:
            self.stuck += 1
        else:
            self.stuck = 0
        self.last_pos = pos

        # 1. Settle the belt we owe. Highest-value action in the game: nothing scores until the chain
        #    reaches the Core, so finishing always outranks starting (G02).
        if self._settle_owed(ct, pos):
            return
        # 2. Range-0 sabotage — the only attack a builder has (G14). Cuts every harvester upstream.
        if self._sabotage(ct, pos):
            return
        # 3. Phase work.
        if self.phase == "harvest" and self._try_harvester(ct, pos):
            return
        if self.phase == "belt" and self._belt_step(ct, pos):
            return
        if self.phase == "seek":
            self._seek(ct, pos)
            if self.phase == "harvest" and self._try_harvester(ct, pos):
                return
        # 4. Repair anything friendly and damaged beside us.
        if self._heal(ct, pos):
            return
        # 5. Otherwise walk.
        self._walk(ct, pos)

    def _observe(self, ct, pos):
        """Fold this round's vision into private map memory (~66us for a full scan)."""
        if not self._cpu_left(ct):
            return
        try:
            tiles = ct.get_nearby_tiles()
        except Exception:
            return
        for tile in tiles:
            key = (tile.x, tile.y)
            if key not in self.core_tiles:
                # Learn our Core's real 2x2 footprint from vision rather than guessing the anchor.
                bid = self._building_at(ct, tile)
                if bid is not None:
                    try:
                        if (ct.get_entity_type(bid) == EntityType.CORE
                                and ct.get_team(bid) == ct.get_team()):
                            self.core_tiles.add(key)
                    except Exception:
                        pass
            if key in self.seen:
                continue
            env = self._env(ct, tile)
            if env is None:
                continue
            self.seen.add(key)
            if env == Environment.WALL:
                self.known_walls.add(key)
            elif env == Environment.ORE_TITANIUM:
                self.known_ore.add(key)

    # --- chain construction -------------------------------------------

    def _settle_owed(self, ct, pos):
        """Build the belt we owe on the tile we just vacated, facing the way we walked."""
        if self.owed is None:
            return False
        belt_pos, facing = self.owed
        if pos.distance_squared(belt_pos) != 1:
            self.owed = None          # drifted away; the chain is broken here, restart
            self._abandon()
            return False
        if self._building_at(ct, belt_pos) is not None:
            self.owed = None          # already occupied (usually our own earlier belt)
            if self.owed_is_final:
                self._finish_chain(ct)
            return False
        if not self._can_act(ct):
            return False
        try:
            if ct.can_build_conveyor(belt_pos, facing):
                ct.build_conveyor(belt_pos, facing)
                self.owed = None
                if self.owed_is_final:
                    self._finish_chain(ct)
                return True
        except Exception:
            self.owed = None
            return False
        return False

    def _core_dir_from(self, ct, pos):
        """Direction to an orthogonally adjacent Core footprint tile, or None.

        Checked live against the building actually on the tile rather than trusting a cached
        footprint: a builder that never happened to scan its own Core would otherwise never
        recognise the terminal tile, and the chain would never be capped — scoring zero (G02).
        """
        for d in CARDINALS:
            n = pos.add(d)
            if (n.x, n.y) in self.core_tiles:
                return d
            bid = self._building_at(ct, n)
            if bid is None:
                continue
            try:
                if ct.get_entity_type(bid) == EntityType.CORE and ct.get_team(bid) == ct.get_team():
                    self.core_tiles.add((n.x, n.y))
                    return d
            except Exception:
                continue
        return None

    def _nearest_core_tile(self, pos):
        if self.core_tiles:
            best, best_d = None, None
            for key in self.core_tiles:
                d = (key[0] - pos.x) ** 2 + (key[1] - pos.y) ** 2
                if best_d is None or d < best_d:
                    best_d, best = d, key
            return Position(best[0], best[1])
        return self.core_pos

    def _belt_step(self, ct, pos):
        """One step of laying the chain back toward the Core."""
        if not self._can_move_now(ct):
            return False

        core_dir = self._core_dir_from(ct, pos)
        if core_dir is not None:
            # Terminal tile: we are beside the Core. We cannot build on our own tile, so step aside
            # once and cap this tile with a belt facing into the footprint.
            if self._building_at(ct, pos) is not None:
                self._finish_chain(ct)
                return False
            for d in CARDINALS:
                if d == core_dir:
                    continue
                n = pos.add(d)
                if (n.x, n.y) in self.core_tiles:
                    continue
                try:
                    if ct.can_move(d):
                        self.owed = (pos, core_dir)
                        self.owed_is_final = True
                        ct.move(d)
                        return True
                except Exception:
                    continue
            return False

        target = self._nearest_core_tile(pos)
        if target is None:
            self._abandon()
            return False
        step = self._step_toward(ct, pos, target)
        if step is None:
            self.stuck += 1
            if self.stuck >= 5:
                self._abandon()
            return False
        try:
            ct.move(step)
        except Exception:
            return False
        # Owe a belt on the tile we just left, facing exactly the way we walked.
        if (pos.x, pos.y) not in self.known_ore:
            self.owed = (pos, step)
            self.owed_is_final = False
        return True

    def _finish_chain(self, ct):
        self.owed_is_final = False
        self.phase = "seek"
        self.target_ore = None
        try:
            ct.write_store(S_CONNECTED, ct.read_store(S_CONNECTED) + 1)
            ct.write_store(S_CLAIM_0 + (self.ordinal % N_CLAIMS), 0)
        except Exception:
            pass

    def _abandon(self):
        self.phase = "seek"
        self.target_ore = None
        self.owed = None
        self.owed_is_final = False
        self.stuck = 0

    # --- phases --------------------------------------------------------

    def _seek(self, ct, pos):
        ore = self._pick_ore(ct, pos)
        if ore is None:
            return
        self.target_ore = ore
        self.phase = "harvest"
        try:
            ct.write_store(S_CLAIM_0 + (self.ordinal % N_CLAIMS), pack(Position(ore[0], ore[1])))
        except Exception:
            pass

    def _try_harvester(self, ct, pos):
        if self.target_ore is None:
            return False
        ore = Position(self.target_ore[0], self.target_ore[1])
        if pos.distance_squared(ore) != 1:
            return False
        if self._building_at(ct, ore) is not None:
            self._abandon()
            return False
        if not self._can_act(ct):
            return False
        try:
            if ct.get_global_resources() < ct.get_harvester_cost():
                return False
            if ct.can_build_harvester(ore):
                ct.build_harvester(ore)
                # A harvester orthogonally adjacent to the Core footprint already delivers straight
                # into it — the chain is complete with zero conveyors. Building one anyway would add
                # a second output and split the harvester's fixed 10 Ti/4 rounds round-robin.
                if self._core_dir_from(ct, ore) is not None:
                    self._finish_chain(ct)
                else:
                    self.phase = "belt"   # walk home laying the belt behind us
                return True
        except Exception:
            return False
        return False

    def _pick_ore(self, ct, pos):
        claimed = set()
        for i in range(N_CLAIMS):
            if i == (self.ordinal % N_CLAIMS):
                continue
            try:
                other = unpack(ct.read_store(S_CLAIM_0 + i))
            except Exception:
                other = None
            if other is not None:
                claimed.add(other)
        best, best_d = None, None
        for key in self.known_ore:
            if key in claimed:
                continue
            tile = Position(key[0], key[1])
            if self._building_at(ct, tile) is not None:
                continue
            d = pos.distance_squared(tile)
            if best_d is None or d < best_d:
                best_d, best = d, key
        return best

    def _walk(self, ct, pos):
        if not self._can_move_now(ct):
            return
        if self.phase == "harvest" and self.target_ore is not None:
            target = Position(self.target_ore[0], self.target_ore[1])
            step = self._step_toward(ct, pos, target)
            if step is not None:
                try:
                    ct.move(step)
                except Exception:
                    pass
                return
            self.stuck += 1
            if self.stuck >= 5:
                self._abandon()
            return
        self._explore(ct, pos)

    def _explore(self, ct, pos):
        """Spread out from the Core to find ore. Deterministic — never the global random module (G26)."""
        core = self._nearest_core_tile(pos)
        if core is None:
            order = CARDINALS
        else:
            away = cardinal_of(pos.x - core.x, pos.y - core.y)
            order = (away,) + tuple(d for d in CARDINALS if d != away)
        offset = (self.ordinal or 0) % len(order)
        for i in range(len(order)):
            d = order[(i + offset) % len(order)]
            try:
                if ct.can_move(d):
                    ct.move(d)
                    return
            except Exception:
                continue

    def _step_toward(self, ct, pos, target):
        want = cardinal_of(target.x - pos.x, target.y - pos.y)
        options = [want]
        try:
            options.append(want.rotate_left())
            options.append(want.rotate_right())
        except Exception:
            pass
        for d in options:
            if d not in CARDINALS:
                continue
            try:
                if ct.can_move(d):
                    return d
            except Exception:
                continue
        for d in CARDINALS:
            try:
                if ct.can_move(d):
                    return d
            except Exception:
                continue
        return None

    # --- builder combat / upkeep ---------------------------------------

    def _sabotage(self, ct, pos):
        """Fire at our own tile while standing on an enemy belt (G14) — the only builder attack."""
        bid = self._building_at(ct, pos)
        if not self._is_enemy(ct, bid) or not self._can_act(ct):
            return False
        try:
            if ct.get_global_resources() < 6:
                return False
            if ct.can_fire(pos):
                ct.fire(pos)
                return True
        except Exception:
            return False
        return False

    def _heal(self, ct, pos):
        if not self._can_act(ct):
            return False
        for d in CARDINALS:
            target = pos.add(d)
            if not self._in_bounds(ct, target):
                continue
            try:
                if ct.can_heal(target):
                    ct.heal(target)
                    return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------
    # Turrets — every API here is team-blind (G10). Verify before firing.
    # ------------------------------------------------------------------

    def _run_gunner(self, ct):
        try:
            target = ct.get_gunner_target()
        except Exception:
            return
        if target is None:
            return
        occupant = self._building_at(ct, target)
        if occupant is None:
            occupant = self._bot_at(ct, target)
        if not self._is_enemy(ct, occupant):
            # Friendly or unknown in the ray. Firing destroys our own unit, and the engine keeps
            # offering this same target forever (G11) — hold fire rather than shoot through it.
            return
        try:
            if ct.can_fire(target):
                ct.fire(target)
        except Exception:
            return

    def _run_sentinel(self, ct):
        """No get_sentinel_target() exists; the pattern is a 3-row band (G15) and it will burn a 10 Ti
        magazine on empty air. Only ever fire at a confirmed enemy occupant."""
        try:
            tiles = ct.get_attackable_tiles()
        except Exception:
            return
        for tile in tiles:
            occupant = self._building_at(ct, tile)
            if occupant is None:
                occupant = self._bot_at(ct, tile)
            if not self._is_enemy(ct, occupant):
                continue
            try:
                if ct.can_fire(tile):
                    ct.fire(tile)
                    return
            except Exception:
                continue
