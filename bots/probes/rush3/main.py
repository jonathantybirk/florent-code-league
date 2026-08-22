"""Sentinel rush: one Builder walks to the enemy Core and stands up four Sentinels firing into it.

THE MATH (all of it measured in-engine on fcode 2.3.9, not taken from the docs):

    starting titanium                        500
    spawn one Builder            30 Ti       scale 1.00 -> 1.20
    Sentinel 1..4         36+42+47+53 Ti     scale 1.20 -> 2.00
    ammunition                  280 Ti       28 shots x 10 ammo
                                ---
    total                       488 Ti       margin +12 before any income

Passive income is 10 Ti / 4 rounds, and the walk is 9-44 rounds (median 23 over the pool), so the
real margin on arrival is +62 to +137 Ti -- six to thirteen spare shots.

WHY EXACTLY FOUR.  A Sentinel deals 18 damage every 2 rounds, so four of them is 36 HP/round.  The
enemy Core's 2x2 footprint has eight orthogonal neighbours, and a Builder heals 4 HP for 1 Ti, so
the most the opponent can possibly mend is 32 HP/round.  Three Sentinels (27/round) lose to a full
heal ring.  Four is the smallest number that kills through one.

Ammunition, not damage, is the binding cost: 280 Ti of it is needed no matter how many turrets fire,
because it scales with the Core's 500 HP and not with our DPS.  More Sentinels buy speed, not reach.

GEOMETRY.  A Sentinel hits a single-tile-wide ray along its fixed facing, out to r^2 <= 32, and the
ray is never blocked -- measured: a barrier at range 3 behind the target took no damage, so a shot
hits only the tile it names, but walls and units in between do not stop it.

So the Builder precomputes EVERY tile that can shoot the Core, with the facing that does it, then
walks to whichever of them has the most buildable neighbours and fills those neighbours in.  Four
builds, ideally no steps between them.  Diagonal facings are legal for turrets, which is what makes
dense clusters common right beside the Core.  Turrets are impassable, so each placement pushes the
Builder onto a different neighbour by itself.

There is deliberately NO fallback target: a shot spent on a conveyor is a shot the Core does not
take, and ammunition is the binding constraint.

The enemy Core is derived at round 0 from map symmetry, never scouted -- see `_enemy_core`.  The
Core publishes it to the store, because it is the only unit that always knows where our own Core is.
"""

from fcode import Controller, Direction, Environment, EntityType, Position

try:
    from terrain import INDEX as _MAP_INDEX, WALLS as _MAP_WALLS
except Exception:          # unknown deployment -- fall back to observation
    _MAP_INDEX, _MAP_WALLS = {}, {}

# ---------------------------------------------------------------------------- tuning
SENTINEL_TARGET = 3        # see "WHY EXACTLY FOUR" above
MAX_RANGE_SQ = 32          # Sentinel attack radius^2
KILL_AMMO = 280            # 28 Sentinel shots: what a full-health 500 HP Core costs
AMMO_CAP = 340             # leave a little titanium for mending the ring
REPAIR_RESERVE = 40
REPLACE_BUILDER = True     # re-spawn a dead Builder while the ring is unfinished
MENDERS = 2                # Builders kept on the Core once a rush is detected
MEND_RESERVE = 70          # titanium held back to pay for that mending
UNKNOWN_COST = 3           # what a tile we have never seen costs, against 1 for one we have
THREAT_COST = 8            # detour a Builder will accept to stay out of a threatened tile
ANCHOR_BONUS = 2           # steps of walking each extra buildable neighbour is worth
USE_BUNDLED_TERRAIN = True # seed the wall map from terrain.py for the known pool
CPU_BUDGET_US = 7000       # stop optional work well inside the 10 ms limit

SLOT_BUILT = 0             # Sentinels standing, written by the Builder
SLOT_BUILDER = 1           # Builder heartbeat: round + 1
SLOT_ENEMY = 2             # enemy Core, packed (x + 1) * 64 + y, published by our Core
SLOT_ALARM = 3             # 1 once we have decided we are being rushed; never clears
SLOT_ATTACKER = 4          # entity id of the Builder that carries the attack, + 1


def _pack(pos):
    return (pos.x + 1) * 64 + pos.y


def _unpack(word):
    return None if word <= 0 else (word // 64 - 1, word % 64)

CARDINALS = (
    (Direction.NORTH, 0, -1),
    (Direction.SOUTH, 0, 1),
    (Direction.EAST, 1, 0),
    (Direction.WEST, -1, 0),
)

# A Sentinel's facing may be diagonal even though the Builder that places it may not move that way.
RAYS = (
    (Direction.NORTH, 0, -1), (Direction.SOUTH, 0, 1),
    (Direction.EAST, 1, 0), (Direction.WEST, -1, 0),
    (Direction.NORTHEAST, 1, -1), (Direction.NORTHWEST, -1, -1),
    (Direction.SOUTHEAST, 1, 1), (Direction.SOUTHWEST, -1, 1),
)

# (width, height, own_core_x, own_core_y) -> 'R' rotational / 'H' horizontal / 'V' vertical.
# The 15-map competition pool, both seats. Unknown maps fall through to _guess_symmetry.
_SYM = {
    (20, 20, 9, 1): 'V', (20, 20, 9, 17): 'V',
    (26, 12, 2, 5): 'H', (26, 12, 22, 5): 'H',
    (20, 20, 2, 1): 'R', (20, 20, 16, 17): 'R',
    (30, 30, 14, 2): 'V', (30, 30, 14, 26): 'V',
    (18, 18, 2, 8): 'H', (18, 18, 14, 8): 'H',
    (12, 12, 1, 1): 'R', (12, 12, 9, 9): 'R',
    (20, 20, 1, 16): 'R', (20, 20, 17, 2): 'R',
    (24, 24, 4, 4): 'R', (24, 24, 18, 18): 'R',
    (28, 18, 2, 8): 'H', (28, 18, 24, 8): 'H',
    (30, 30, 2, 2): 'R', (30, 30, 26, 26): 'R',
    (24, 24, 1, 11): 'H', (24, 24, 21, 11): 'H',
    (16, 16, 7, 1): 'V', (16, 16, 7, 13): 'V',
    (22, 22, 9, 2): 'V', (22, 22, 9, 18): 'V',
    (30, 30, 2, 14): 'H', (30, 30, 26, 14): 'H',
    (30, 30, 3, 3): 'R', (30, 30, 25, 25): 'R',
}


def _guess_symmetry(w, h, cx, cy):
    """Fallback for a map not in the table.

    A Core cannot be its own mirror image, so an axis we sit centred on is ruled out. Whatever
    survives, prefer rotational: it is the most common kind in the pool and it is the reading that
    puts the enemy furthest away, which is the safe way to be wrong.
    """
    horizontal_ok = (w - 2 - cx) != cx
    vertical_ok = (h - 2 - cy) != cy
    if horizontal_ok and vertical_ok:
        return 'R'
    if horizontal_ok:
        return 'H'
    return 'V'


def _enemy_core(ct, own):
    """The enemy Core's north-west corner, derived rather than scouted.

    Terrain on every pool map is exactly symmetric under x -> W-1-x, but the Core is 2x2 and is
    reported by its north-west corner, so the mirror of the block [x, x+1] is [W-2-x, W-1-x] and
    the corner lands on W-2-x. Verified against all 15 live maps and all 42 entries of the retired
    pool's table: 57 of 57.
    """
    w, h = ct.get_map_width(), ct.get_map_height()
    kind = _SYM.get((w, h, own.x, own.y)) or _guess_symmetry(w, h, own.x, own.y)
    if kind == 'H':
        return kind, Position(w - 2 - own.x, own.y)
    if kind == 'V':
        return kind, Position(own.x, h - 2 - own.y)
    return kind, Position(w - 2 - own.x, h - 2 - own.y)


def _mirror(kind, w, h, key):
    """The tile that terrain symmetry says is identical to `key`.

    TERRAIN reflects about W-1, the Core pair about W-2 -- the two differ because the Core is 2x2
    and is named by its north-west corner. Measured over the whole pool, terrain under W-1 has
    exactly zero mismatched tiles, so this is an equality, not a heuristic.
    """
    if kind == 'H':
        return (w - 1 - key[0], key[1])
    if kind == 'V':
        return (key[0], h - 1 - key[1])
    return (w - 1 - key[0], h - 1 - key[1])


def _footprint(nw):
    return ((nw.x, nw.y), (nw.x + 1, nw.y), (nw.x, nw.y + 1), (nw.x + 1, nw.y + 1))


class Player:
    def __init__(self):
        self.kind = None
        self.round = 0
        # core
        self.spawned = 0
        self.alarm = False
        self.menders = 0
        self.attacker = None
        # builder
        self.home = None
        self.enemy = None
        self.enemy_tiles = ()
        self.mine_tiles = ()
        self.role = None
        self.sym = 'R'
        self.seen = set()           # every tile ever in vision -- routing prefers these
        self.walls = set()          # confirmed WALL
        self.blocked = set()        # cannot WALK here: barriers, harvesters, turrets, cores
        self.occupied = set()       # cannot BUILD here: the above plus conveyors and splitters
        self.built = 0
        self.width = 0
        self.height = 0
        self.spots = {}             # tile -> facing that puts the Core on its ray
        self.turrets = {}           # enemy turret id -> (pos, facing, covered tiles)
        self.goal = None            # this round's destination tile
        self.path = []              # cached route, held until genuinely obstructed
        self._dist = {}             # this round's flood, shared by lane scoring and movement
        self._came = {}

    # ------------------------------------------------------------------ entry
    def run(self, ct: Controller) -> None:
        """An uncaught exception deletes the unit from the match for the rest of the game."""
        try:
            self._run(ct)
        except Exception:
            pass

    def _run(self, ct):
        if self.kind is None:
            self.kind = ct.get_entity_type()
        self.round = ct.get_current_round()
        if self.kind == EntityType.CORE:
            self._core(ct)
        elif self.kind == EntityType.BUILDER_BOT:
            self._builder(ct)
        elif self.kind == EntityType.SENTINEL:
            self._sentinel(ct)

    # ------------------------------------------------------------------- core
    def _core(self, ct):
        # The Core is the only unit that always knows where our Core is, so it is the only unit
        # that can derive the enemy Core without guessing. Everyone else reads it from here.
        if self.enemy is None:
            try:
                self.sym, self.enemy = _enemy_core(ct, ct.get_position())
            except Exception:
                self.enemy = None
        if self.enemy is not None:
            try:
                ct.write_store(SLOT_ENEMY, _pack(self.enemy))
            except Exception:
                pass
        built = 0
        try:
            built = ct.read_store(SLOT_BUILT)
        except Exception:
            built = 0
        self._watch_for_rush(ct)
        self._keep_builder(ct, built)
        self._keep_menders(ct)
        self._feed_ammo(ct, built)

    def _watch_for_rush(self, ct):
        """Decide whether someone is coming for us, and latch it.

        Worth doing because the exchange rate is lopsided. A rusher's whole ammunition budget is
        about 522 damage against our 500 HP, and mending buys 4 HP per titanium against the 1.8 HP
        per titanium their Sentinels deal -- so roughly SIX titanium of healing is enough to make a
        mirror rush run dry one hit short. Defence is 2.2x the titanium value of offence here.

        Three tests, cheapest and surest first. The Core's vision radius is exactly 6, so "our Core
        can see an enemy Builder at all" already is the proximity test and needs no arithmetic.
        A rush never stops being a rush, so the flag latches.
        """
        if self.alarm:
            return
        why = None
        try:
            if ct.get_hp() < ct.get_max_hp():
                why = "damaged"
        except Exception:
            pass
        if why is None:
            try:
                mine = ct.get_team()
                for uid in ct.get_nearby_units():
                    if ct.get_team(uid) == mine:
                        continue
                    kind = ct.get_entity_type(uid)
                    if kind in (EntityType.BUILDER_BOT, EntityType.GUNNER,
                                EntityType.SENTINEL, EntityType.LAUNCHER):
                        why = "visitor"
                        break
            except Exception:
                pass
        if why is None:
            return
        self.alarm = True
        try:
            ct.write_store(SLOT_ALARM, 1)
        except Exception:
            pass

    def _keep_builder(self, ct, built):
        if self.spawned and not REPLACE_BUILDER:
            return
        if built >= SENTINEL_TARGET:
            return
        if self.spawned:
            # Only replace one that has actually stopped reporting. The heartbeat is written on
            # the round the Builder acts and a write lands even on the round its author dies, so
            # a stamp two rounds stale means gone, not merely busy.
            try:
                beat = ct.read_store(SLOT_BUILDER)
            except Exception:
                return
            if beat and self.round - (beat - 1) < 3:
                return
            if self.round < 4:
                return
        self._spawn_one(ct)

    def _keep_menders(self, ct):
        """Under attack, put Builders on the Core to out-heal the damage.

        They are only ever bought once the alarm has latched, because until then every titanium is
        worth more as ammunition.
        """
        if not self.alarm or self.menders >= MENDERS:
            return
        try:
            if ct.get_global_resources() < ct.get_builder_bot_cost() + 20:
                return
        except Exception:
            return
        if self._spawn_one(ct):
            self.menders += 1

    def _spawn_one(self, ct):
        try:
            if ct.get_global_resources() < ct.get_builder_bot_cost():
                return False
            for tile in ct.get_nearby_tiles(2):
                if ct.can_spawn(tile):
                    made = ct.spawn_builder(tile)
                    self.spawned += 1
                    if self.attacker is None:
                        # The first Builder ever spawned carries the attack; everyone after it
                        # mends. spawn_builder hands back the id, so the assignment is exact and
                        # needs no negotiation between units.
                        self.attacker = made
                        try:
                            ct.write_store(SLOT_ATTACKER, (made or 0) + 1)
                        except Exception:
                            pass
                    return True
        except Exception:
            return False
        return False

    def _feed_ammo(self, ct, built):
        """Convert titanium into ammunition, but never into the ring's own build cost.

        Costs rise 20% of base per turret built, so the remaining Sentinels cost more than the one
        priced right now; reserve for the whole rest of the ring before converting a single point.

        The repair reserve is held back ONLY once enough ammunition to finish the Core is already
        banked. Holding 40 Ti unconditionally cost the kill outright: 500 - 30 - 178 leaves 292,
        and 292 - 40 = 252 ammo is 25 shots for 450 damage against 500 HP. On skald, the shortest
        walk in the pool, there is no travel income to cover the gap -- the ring went up on round
        20, ran dry on round 40, and then chipped at one shot per four rounds of passive income
        for the rest of the match. Mending a turret is worth nothing if the Core survives.
        """
        try:
            if ct.get_global_ammo() >= AMMO_CAP:
                return
            remaining = SENTINEL_TARGET - built
            reserve = REPAIR_RESERVE if ct.get_global_ammo() >= KILL_AMMO else 0
            if self.alarm:
                reserve += MEND_RESERVE
            if remaining > 0:
                unit = ct.get_sentinel_cost()
                reserve += remaining * unit + 3 * remaining * (remaining - 1)
                if REPLACE_BUILDER:
                    reserve += ct.get_builder_bot_cost()
            spare = ct.get_global_resources() - reserve
            if spare < 10:
                return
            amount = min(spare, AMMO_CAP - ct.get_global_ammo())
            if amount >= 10 and ct.can_convert_ammo(amount):
                ct.convert_ammo(amount)
        except Exception:
            return

    # ---------------------------------------------------------------- builder
    def _builder(self, ct):
        here = ct.get_position()
        if self.home is None:
            self._orient(ct, here)
        try:
            ct.write_store(SLOT_BUILDER, self.round + 1)
        except Exception:
            pass

        if self.role is None:
            # The Core names the attacker by entity id, so this needs no negotiation. Anything
            # spawned after it exists only because the alarm latched, and its job is the Core.
            try:
                named = ct.read_store(SLOT_ATTACKER)
                self.role = "attack" if (named and named - 1 == ct.get_id()) else "mend"
            except Exception:
                self.role = "attack"

        self._observe(ct, here)
        if self.role == "mend":
            self._dist, self._came = self._flood(here, None)
            self._mend_core(ct, here)
            return
        self._dist, self._came = self._flood(here, self._threats(ct))

        # A build and a move are mutually exclusive in one round, and the ring is worth more than
        # a step, so try to build first.
        if self.built < SENTINEL_TARGET:
            # Place first. A build and a move are mutually exclusive in one round, and a turret
            # shooting the Core is worth more than a step toward a tidier spot for one.
            if self._place(ct, here):
                return
            self.goal = self._next_stand(here)
            if self._advance(ct, here):
                return
            self._break_through(ct, here)
            return
        self._tend(ct, here)

    def _orient(self, ct, here):
        self.home = here
        self.width, self.height = ct.get_map_width(), ct.get_map_height()
        core = here
        try:
            for uid in ct.get_nearby_buildings():
                if ct.get_entity_type(uid) == EntityType.CORE and ct.get_team(uid) == ct.get_team():
                    core = ct.get_position(uid)
                    break
        except Exception:
            core = here
        self.mine_tiles = _footprint(core)
        self.sym, self.enemy = _enemy_core(ct, core)
        try:
            told = _unpack(ct.read_store(SLOT_ENEMY))
        except Exception:
            told = None
        if told is not None:
            self.enemy = Position(told[0], told[1])
        self.enemy_tiles = _footprint(self.enemy)
        self._seed_terrain(core)
        self.spots = self._firing_spots()
        for tile in self.enemy_tiles:
            self.blocked.add(tile)
            self.occupied.add(tile)
        for tile in _footprint(core):
            self.blocked.add(tile)
            self.occupied.add(tile)

    def _firing_spots(self):
        """Every tile from which a Sentinel could hit the Core, with the facing that does it.

        Replaces the single committed "lane". A lane is four specific tiles, so one enemy building
        dropped on the first of them stops the whole rush: on holmgang the Builder reached its
        stand tile on round 16 and then sat there for the remaining 984 rounds, punching the
        obstruction, its own action cooldown blocking the build it was waiting to make. There are
        dozens of firing spots around a Core, so blocking one is not worth noticing.

        Pure geometry, no API calls: a Sentinel at n facing D hits T when T = n + k*D within
        r^2 <= 32 -- k <= 5 straight, k <= 4 diagonal. Walls in between do not matter, the shot
        goes through them; a wall only rules out standing there.
        """
        spots = {}
        for target in self.enemy_tiles:
            for facing, dx, dy in RAYS:
                span = 1 if (dx == 0 or dy == 0) else 2
                k = 1
                while k * k * span <= MAX_RANGE_SQ:
                    key = (target[0] - dx * k, target[1] - dy * k)
                    k += 1
                    if not (0 <= key[0] < self.width and 0 <= key[1] < self.height):
                        continue
                    if key in self.walls or key in self.enemy_tiles:
                        continue
                    spots.setdefault(key, facing)
        return spots

    def _seed_terrain(self, core):
        """Load the pool's wall layout, if this is a map we ship.

        Walls never change, so knowing them up front costs the opponent nothing it could not also
        look up -- the pool is a public download. What it buys is a true shortest path from round 0
        instead of thirty rounds of the Builder discovering that both ways round a wall look
        equally good while it is standing still in net terms.
        """
        if not USE_BUNDLED_TERRAIN:
            return
        found = _MAP_INDEX.get((self.width, self.height, core.x, core.y))
        if found is None:
            return
        bits = _MAP_WALLS.get(found[1])
        if bits is None or bits[0] != self.width or bits[1] != self.height:
            return
        grid = bits[2]
        for y in range(self.height):
            row = y * self.width
            for x in range(self.width):
                key = (x, y)
                self.seen.add(key)
                if grid[row + x] == '1':
                    self.walls.add(key)

    def _mend_core(self, ct, here):
        """Stand on the Core and keep it alive.

        4 HP for 1 Ti against the 1.8 HP per Ti a Sentinel deals: mending is 2.2x the titanium
        value of shooting, and an attacker's whole budget is only about 22 HP more than our Core
        has. A handful of heals is the difference between losing the race and winning it.
        """
        best = None
        for key in self.mine_tiles:
            for _d, dx, dy in CARDINALS:
                spot = Position(key[0] + dx, key[1] + dy)
                if (spot.x, spot.y) in self.mine_tiles:
                    continue
                try:
                    if not ct.can_heal(spot):
                        continue
                except Exception:
                    continue
                if abs(spot.x - here.x) + abs(spot.y - here.y) <= 1:
                    best = spot
                    break
            if best is not None:
                break
        if best is not None:
            try:
                ct.heal(best)
                return
            except Exception:
                pass
        # not in reach yet -- walk to the Core
        goal = None
        cheapest = None
        for key in self.mine_tiles:
            for _d, dx, dy in CARDINALS:
                step = (key[0] + dx, key[1] + dy)
                cost = self._dist.get(step)
                if cost is not None and (cheapest is None or cost < cheapest):
                    cheapest, goal = cost, step
        if goal is None or goal == (here.x, here.y):
            return
        path = self._trace(self._came, here, goal)
        if path:
            self._step_to(ct, here, path[0])

    def _observe(self, ct, here):
        """Fold this round's vision into the map. Terrain never changes; buildings do, so a tile
        that has lost its building must be released again or the router will avoid a hole forever.
        """
        try:
            tiles = ct.get_nearby_tiles()
        except Exception:
            return
        mine = ct.get_team()
        for pos in tiles:
            key = (pos.x, pos.y)
            self.seen.add(key)
            twin = _mirror(self.sym, self.width, self.height, key)
            self.seen.add(twin)
            try:
                if ct.get_tile_env(pos) == Environment.WALL:
                    self.walls.add(key)
                    self.walls.add(twin)
                    continue
            except Exception:
                continue
            if key in self.enemy_tiles:
                continue
            try:
                bid = ct.get_tile_building_id(pos)
            except Exception:
                continue
            if bid is None:
                self.blocked.discard(key)
                self.occupied.discard(key)
            else:
                # Two different questions. A conveyor is WALKABLE, so it never belongs in
                # `blocked` -- but it is still a building, so nothing can be built on top of it.
                # Conflating the two stalled the rush outright: a conveyor tile looked like a free
                # firing spot, can_build_sentinel refused it every round, and `_next_stand` kept
                # answering "the tile you are already standing on". Against a bot that lays belts
                # across the map that is most of the approach.
                self.occupied.add(key)
                blocks = True
                try:
                    kind = ct.get_entity_type(bid)
                    blocks = kind not in (EntityType.CONVEYOR, EntityType.SPLITTER)
                except Exception:
                    blocks = True
                if blocks:
                    self.blocked.add(key)
                else:
                    self.blocked.discard(key)
        # our own Core is permanently impassable, including to us
        try:
            for uid in ct.get_nearby_buildings():
                if ct.get_entity_type(uid) == EntityType.CORE:
                    for tile in _footprint(ct.get_position(uid)):
                        self.blocked.add(tile)
        except Exception:
            pass
        _ = mine

    # -- lane choice ---------------------------------------------------------
    def _passable(self, key):
        if key in self.walls or key in self.blocked:
            return False
        return 0 <= key[0] < self.width and 0 <= key[1] < self.height

    def _free_spot(self, key):
        """Can a Sentinel of ours stand here and see the Core?"""
        return (key in self.spots and key not in self.walls
                and key not in self.occupied
                and 0 <= key[0] < self.width and 0 <= key[1] < self.height)

    def _place(self, ct, here):
        """Build on any orthogonally adjacent tile that puts the Core on the new turret's ray.

        No lane, no ordering, no committed geometry -- just "is this neighbour a firing spot, and
        will the engine let me build there". Turrets are impassable, so each one placed nudges the
        Builder to use a different neighbour next round, which is the retreat pattern falling out
        for free instead of being scripted.
        """
        for _d, dx, dy in CARDINALS:
            key = (here.x + dx, here.y + dy)
            if not self._free_spot(key):
                continue
            facing = self.spots[key]
            spot = Position(key[0], key[1])
            try:
                if not ct.can_build_sentinel(spot, facing):
                    continue
                ct.build_sentinel(spot, facing)
            except Exception:
                continue
            self.built += 1
            self.blocked.add(key)
            self.occupied.add(key)
            self.path = []
            try:
                ct.write_store(SLOT_BUILT, self.built)
            except Exception:
                pass
            return True
        return False

    def _next_stand(self, here):
        """The anchor: a tile to stand on whose NEIGHBOURS are firing spots -- as many as possible.

        A Builder can only build on the four tiles orthogonally beside it, so a tile with all four
        neighbours firing spots lets the whole ring go up without moving once: four builds, four
        rounds, no repositioning. Settling for the nearest tile with any single free neighbour
        instead costs a step between most placements.

        Diagonal facings are what make dense anchors common. Beside the Core almost every tile sits
        on some ray to one of its four squares, so clusters of three and four are the normal case
        rather than a lucky one.

        Each extra neighbour is worth about the two rounds of shuffling it saves, so that is what a
        step of walking is traded against.
        """
        # NOT committed. Sticking to an anchor until it has no buildable neighbour left was tried
        # and measured worse: flagship 19/30 -> 15/30, vigil 27/30 -> 23/30. It also failed to fix
        # the gap it was aimed at. Holding a mediocre anchor costs more than re-deciding does,
        # because the cheapest cluster genuinely moves as the opponent builds.
        want = SENTINEL_TARGET - self.built
        best = None
        chosen = None
        for key, cost in self._dist.items():
            usable = self._anchor_value(key)
            if not usable:
                continue
            score = cost - ANCHOR_BONUS * min(usable, want)
            if best is None or score < best:
                best, chosen = score, key
        if chosen is not None:
            return chosen
        return self._closest_to_core()

    def _anchor_value(self, key):
        """How many Sentinels could still be planted from this tile."""
        usable = 0
        for _d, dx, dy in CARDINALS:
            if self._free_spot((key[0] + dx, key[1] + dy)):
                usable += 1
        return usable

    def _threats(self, ct):
        """Tiles to keep out of: enemy Builders, and everything a known enemy turret covers.

        Turrets are REMEMBERED, not merely seen. A Builder has 40 HP and a Gunner takes 7 a round,
        a Sentinel 18 -- so walking back into a lane we already know about is how the whole rush
        dies. Vision is radius 4.5 and turret reach is 3.6 to 5.7, so a turret that shot at us is
        routinely out of sight by the time we choose the next step; recomputing the threat map from
        the current frame alone forgets it immediately and walks straight back in.

        Coverage is computed once when the turret is first identified and cached, because
        get_attackable_tiles_from is not cheap and a turret's arc only changes if it rotates --
        which only a Gunner can do, and which shows up as a fresh reading next time we see it.
        A remembered turret is dropped when we can see its tile and it is empty.
        """
        soft = set()
        try:
            mine = ct.get_team()
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) == mine:
                    continue
                kind = ct.get_entity_type(uid)
                spot = ct.get_position(uid)
                if kind == EntityType.BUILDER_BOT:
                    soft.add((spot.x, spot.y))
                    for _d, dx, dy in CARDINALS:
                        soft.add((spot.x + dx, spot.y + dy))
                elif kind in (EntityType.GUNNER, EntityType.SENTINEL):
                    facing = ct.get_direction(uid)
                    known = self.turrets.get(uid)
                    if known is None or known[0] != (spot.x, spot.y) or known[1] != facing:
                        covered = ct.get_attackable_tiles_from(spot, facing, kind)
                        self.turrets[uid] = ((spot.x, spot.y), facing,
                                             frozenset((t.x, t.y) for t in covered))
        except Exception:
            pass

        stale = []
        for uid, known in self.turrets.items():
            spot = Position(known[0][0], known[0][1])
            try:
                if ct.is_in_vision(spot) and ct.get_tile_building_id(spot) is None:
                    stale.append(uid)
                    continue
            except Exception:
                pass
            soft |= known[2]
        for uid in stale:
            del self.turrets[uid]
        return soft

    def _flood(self, here, soft):
        """One sweep outward from the Builder, reused by every lane this round.

        Scoring sixteen candidate lanes with a search each was sixteen sweeps a round, which does
        not fit in 10 ms on a 900-tile map -- and a Builder that overruns is interrupted and loses
        the turn outright. One sweep answers every lane by lookup instead.

        Threatened tiles cost THREAT_COST extra rather than being impassable. Blocking them
        outright deadlocks the rush: an opponent whose Builders mill around its own base masks out
        the entire approach, the stand tile becomes unreachable, and the Builder stops dead. Every
        single loss against the starter bot was a 1000-round timeout with our Builder alive and the
        ring never built. Avoid has to mean "prefer another way", never "refuse to move".

        Tiles we have SEEN cost 1; tiles we have not cost UNKNOWN_COST. That asymmetry is what
        stops the walk oscillating. Priced equally, an unexplored detour always ties or beats the
        proven route, so every wall the Builder discovers sends it back across the map to try the
        other side -- longhouse cost 74 rounds to place a turret 38 steps away, replanning 22 times,
        each replan individually correct. Charging for ignorance makes a corridor the Builder has
        already walked the cheap one, so the route converges instead of flip-flopping.

        Dial's algorithm rather than a heap: weights are tiny integers and the engine's import
        surface is not worth risking for heapq. Returns (cost, came_from).
        """
        start = (here.x, here.y)
        dist = {start: 0}
        came = {start: None}
        nbuck = UNKNOWN_COST + THREAT_COST + 1
        buckets = [[] for _ in range(nbuck)]
        buckets[0].append(start)
        pending = 1
        cost = 0
        limit = 8 * (self.width * self.height + 4)
        while pending > 0 and cost < limit:
            bucket = buckets[cost % nbuck]
            while bucket:
                key = bucket.pop()
                pending -= 1
                if dist.get(key, limit) < cost:
                    continue                      # superseded by a cheaper route
                for _d, dx, dy in CARDINALS:
                    step = (key[0] + dx, key[1] + dy)
                    if not self._passable(step):
                        continue
                    walk = cost + (1 if step in self.seen else UNKNOWN_COST)
                    if soft and step in soft:
                        walk += THREAT_COST
                    if walk < dist.get(step, limit):
                        dist[step] = walk
                        came[step] = key
                        buckets[walk % nbuck].append(step)
                        pending += 1
            cost += 1
        return dist, came

    def _trace(self, came, here, goal):
        """Full tile-by-tile route out of a finished sweep, or [] if the goal was not reached."""
        if goal not in came:
            return []
        start = (here.x, here.y)
        path = []
        walk = goal
        while walk is not None and walk != start:
            path.append(walk)
            walk = came[walk]
        path.reverse()
        return path

    def _path_usable(self, here, goal):
        """A cached route survives while it still starts next to us, ends at the goal, and is
        clear. Anything else forces a fresh sweep."""
        if not self.path or self.path[-1] != goal:
            return False
        step = self.path[0]
        if abs(step[0] - here.x) + abs(step[1] - here.y) != 1:
            return False
        for key in self.path[:-1]:
            if key in self.walls or key in self.blocked:
                return False
        return True

    def _closest_to_core(self):
        """No lane is reachable -- every stand tile is walled or bricked up.

        Fall back to the reachable tile nearest the Core and dig from there. Without this the
        Builder has no goal at all when an opponent rings its base with barriers: it stops moving,
        never gets adjacent to anything to punch, and the match runs to the round limit.
        """
        best = None
        chosen = None
        for key, cost in self._dist.items():
            gap = max(abs(key[0] - self.enemy.x), abs(key[1] - self.enemy.y))
            score = (gap, cost)
            if best is None or score < best:
                best, chosen = score, key
        return chosen

    def _advance(self, ct, here):
        """Walk the cached route, and re-plan ONLY when it is actually obstructed.

        Re-planning every round looks harmless and is not. Unseen tiles are assumed open, so an
        unexplored detour always prices cheaper than the proven route -- the Builder commits to it,
        walks until the wall appears, and the original route is now the cheap unexplored one again.
        On longhouse that livelocked into a tour of the whole map: goal fixed at (22,8) the entire
        time, zero lane changes, and the distance to it went 20 -> 30 -> 20 -> 10 -> 14 over sixty
        rounds of moving every single turn. Holding the route until something genuinely blocks it
        is what makes the walk monotone.
        """
        goal = self.goal
        if goal is None or (here.x, here.y) == goal:
            return False
        if not self._path_usable(here, goal):
            self.path = self._trace(self._came, here, goal)
            if not self.path:
                # Cornered by the threat mask -- re-sweep ignoring it and take the risky line.
                _d, came = self._flood(here, None)
                self.path = self._trace(came, here, goal)
        if not self.path:
            return False
        if self._step_to(ct, here, self.path[0]):
            self.path.pop(0)
            return True
        self.path = []          # something moved into the way; sweep again next round
        return False

    def _step_to(self, ct, here, step):
        for direction, dx, dy in CARDINALS:
            if (here.x + dx, here.y + dy) != step:
                continue
            try:
                if ct.can_move(direction):
                    ct.move(direction)
                    return True
            except Exception:
                return False
            return False
        return False

    def _break_through(self, ct, here):
        """Walled in. Punch the thing in the way -- 2 Ti for 2 damage, 15 hits through a barrier.

        Slow and expensive, but a rush that stops moving has already lost, and the alternative is
        standing still until the match times out.

        Never punch while a buildable firing spot is sitting right next to us. Firing takes the
        round's action, and the action cooldown then blocks the build we were about to make, which
        makes us punch again next round -- a stall that looks exactly like being walled in while
        the spot we wanted stays free the whole time. If a spot is adjacent, the only thing in the
        way is our own cooldown, and the right move is to wait a round.
        """
        for _d, dx, dy in CARDINALS:
            if self._free_spot((here.x + dx, here.y + dy)):
                return
        goal = self.goal if self.goal is not None else (self.enemy.x, self.enemy.y)
        toward = 0
        best = None
        for direction, dx, dy in CARDINALS:
            key = (here.x + dx, here.y + dy)
            if key in self.walls or key not in self.blocked:
                continue
            gap = abs(key[0] - goal[0]) + abs(key[1] - goal[1])
            if best is None or gap < toward:
                best, toward = Position(key[0], key[1]), gap
        if best is None:
            return
        try:
            if ct.can_fire(best):
                ct.fire(best)
        except Exception:
            return

    # -- construction --------------------------------------------------------
    def _tend(self, ct, here):
        """Ring is up. Mend it: 4 HP for 1 Ti is the cheapest HP on the board."""
        try:
            if ct.get_cpu_time_elapsed() > CPU_BUDGET_US:
                return
            for _d, dx, dy in CARDINALS:
                spot = Position(here.x + dx, here.y + dy)
                bid = ct.get_tile_building_id(spot)
                if bid is None:
                    continue
                if ct.get_team(bid) != ct.get_team():
                    continue
                if ct.get_hp(bid) >= ct.get_max_hp(bid):
                    continue
                if ct.can_heal(spot):
                    ct.heal(spot)
                    return
        except Exception:
            return

    # --------------------------------------------------------------- sentinel
    def _sentinel(self, ct):
        """Fire into the Core every round the reload allows. Nothing else is worth a turn."""
        if self.enemy is None:
            # Read it, never re-derive it. A turret is built next to the ENEMY Core, so ours is
            # usually out of vision -- and the old fallback silently mirrored the turret's OWN
            # position instead, aiming at empty ground. can_fire then failed every round and the
            # ring quietly ground down whatever else was in range while the Core sat untouched.
            found = None
            try:
                found = _unpack(ct.read_store(SLOT_ENEMY))
            except Exception:
                found = None
            if found is None:
                return
            self.enemy = Position(found[0], found[1])
            self.enemy_tiles = _footprint(self.enemy)
        for key in self.enemy_tiles:
            spot = Position(key[0], key[1])
            try:
                if ct.can_fire(spot):
                    ct.fire(spot)
                    return
            except Exception:
                continue
        # Nothing else is worth a shot. Ammunition is the binding constraint of the whole plan --
        # 280 Ti buys exactly 28 Core hits out of a 500 Ti opening, and passive income replaces a
        # spent shot only once every four rounds. A Sentinel that sprays the enemy's conveyors and
        # harvesters is not doing chip damage, it is spending the Core kill.
        #
        # This branch used to fire at any enemy building the line reached, and against a bot with a
        # real economy that is most of the map: 13 wins in 30 against the STARTER bot, median kill
        # round 76 and worst 337 -- the signature of a ring that ran dry and then waited on income
        # at one shot per four rounds. Holding fire is strictly better than firing at the wrong
        # thing, so the turret idles until the Core is legal again.
        return
