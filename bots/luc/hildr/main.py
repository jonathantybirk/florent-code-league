"""hildr -- the Sentinel rush, with a Core that does the race arithmetic.

Lineage: sentinel_rush_cluster (v70) -> rush_econ_pivot (v72) -> this. The walk, the firing-spot
geometry and the router are theirs. What is new is everything the Core decides.

THE RACE.  Two rushes meeting is a sum, not a fight.  A Sentinel deals 9 HP/round, a Builder heals
4 HP/round for 1 Ti, and every shot costs 10 Ti for 18 HP -- so mending is 2.2x cheaper per
titanium than shooting.  Whoever is hit has the cheaper job, IF they have menders at home and
titanium to pay them.  Ladder replays of v70 read exactly like that:

  * pure rushers (Landers, Jacobs Code, Pantheon): nobody mends; the ring that stands first wins.
  * mending rushers (not adgato, Viktor5776): four Builders at home the round our Builder is
    seen, ~2000 HP healed, our ammunition gone by round 40, then their ring kills our naked Core.
  * economies (TRRR, Troupe, Besvikomat): 10-60 Builders and 3000-5000 HP of mending.  Unkillable
    by a ring; timeouts, which they win on titanium collected because we mined nothing.

So the Core keeps the books every round:

  our_dps    = 9 x our Sentinels alive              (heartbeats, slots 4..9)
  their_heal = 4 x enemy Builders beside their Core  (counted by the Sentinels, slot 10)
  their_dps  = 9 x Sentinels + 7 x Gunners that can reach our Core (Core vision, r^2 36)
  our_heal   = 4 x our Builders standing beside our Core

  T_us   = their Core HP / (our_dps - their_heal)   -- inf if we cannot out-damage the menders
  T_them = our  Core HP / (their_dps - our_heal)     -- inf once we out-mend them

Spend titanium on whichever side of that we are losing: menders when T_them is the smaller number,
ammunition when T_us is.  Titanium stays titanium until a Sentinel actually needs it -- v70
converted 250 Ti to ammunition on round 0 and had nothing left to hire a mender with when the
enemy ring arrived.

HOLD.  If the menders make the kill impossible, or it needs more ammunition than we have, the ring
stops shooting the Core (slot 11).  Shots go to menders standing on a turret's ray instead -- three
shots, 30 Ti, for a unit that cost them 60-80 and was worth 4 HP/round -- and everything else is
banked.  When the bank covers the finish, the Core says GO and the ring empties it in one burst
that the menders cannot keep up with.

The long game is decided on titanium collected, and only Harvesters collect.  A home Builder lays
one Harvester and a belt to the Core once the ring is up and nothing is shooting us.
"""

from fcode import Controller, Direction, Environment, EntityType, Position

try:
    from terrain import INDEX as _MAP_INDEX, WALLS as _MAP_WALLS
except Exception:          # unknown deployment -- fall back to observation
    _MAP_INDEX, _MAP_WALLS = {}, {}

# ---------------------------------------------------------------------------- tuning
SENTINEL_TARGET = 4        # smallest ring that kills through a full heal ring (36 > 32 HP/round)
MAX_RANGE_SQ = 32          # Sentinel attack radius^2
REPLACE_BUILDER = True     # re-spawn a dead attack Builder while the ring is unfinished
UNKNOWN_COST = 3           # what a tile we have never seen costs, against 1 for one we have
THREAT_COST = 8            # detour a Builder will accept to stay out of a threatened tile
ANCHOR_BONUS = 2           # steps of walking each extra buildable neighbour is worth
USE_BUNDLED_TERRAIN = True # seed the wall map from terrain.py for the known pool
CPU_BUDGET_US = 7000       # stop optional work well inside the 10 ms limit

HOME_BUILDER_AT_START = False  # a Builder at home on round 0 costs 60 Ti effective: six shots, the kill
MENDERS_MAX = 5            # never more than this many Builders minding the Core
MENDERS_RACE = 4           # the squad bought when their ring will stand before ours
RACE_MARGIN = 1            # rounds our ring must lead theirs by to go all-in
MEND_RESERVE = 30          # titanium kept for mending while anything is shooting us
AMMO_PER_SENTINEL = 20     # ammunition kept banked per living Sentinel (two shots each)
BURST_SLACK = 0.85         # GO when the bank covers this fraction of the finish
ECON_ROUND = 40            # no Harvester before this unless the ring is already up
ECON_MARGIN = 40           # titanium kept over the build cost before the miner starts a job
GO_LOW_HP = 120            # always finish a Core this low if we out-damage the menders

# communication store
SLOT_BUILT = 0             # Sentinels placed, written by the attack Builder
SLOT_BUILDER = 1           # attack Builder heartbeat: round + 1
SLOT_ENEMY = 2             # enemy Core, packed (x + 1) * 64 + y, published by our Core
SLOT_THREAT = 3            # round + 1 while something that can hit our Core is in sight
SLOT_BEAT0 = 4             # Sentinel heartbeats, one slot each: round + 1
SLOT_BEATS = 6             # slots 4..9
SLOT_EHEAL = 10            # enemy Builders beside the enemy Core, written by the Sentinels
SLOT_GO = 11               # 1: shoot the Core.  0: hold, snipe menders, bank
SLOT_EHP = 12              # enemy Core HP, written by the Sentinels (0 = unknown)
SLOT_MINER = 13            # miner heartbeat: round + 1, so only one Builder mines
SLOT_ECON_OK = 14          # round + 1 while the Core is willing to pay for mining
SLOT_ETA = 15              # attack Builder: steps to its anchor + 1 (0 = unknown / done)


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
    horizontal_ok = (w - 2 - cx) != cx
    vertical_ok = (h - 2 - cy) != cy
    if horizontal_ok and vertical_ok:
        return 'R'
    if horizontal_ok:
        return 'H'
    return 'V'


def _enemy_core(ct, own):
    """The enemy Core's north-west corner, derived from map symmetry rather than scouted."""
    w, h = ct.get_map_width(), ct.get_map_height()
    kind = _SYM.get((w, h, own.x, own.y)) or _guess_symmetry(w, h, own.x, own.y)
    if kind == 'H':
        return kind, Position(w - 2 - own.x, own.y)
    if kind == 'V':
        return kind, Position(own.x, h - 2 - own.y)
    return kind, Position(w - 2 - own.x, h - 2 - own.y)


def _mirror(kind, w, h, key):
    if kind == 'H':
        return (w - 1 - key[0], key[1])
    if kind == 'V':
        return (key[0], h - 1 - key[1])
    return (w - 1 - key[0], h - 1 - key[1])


def _footprint(nw):
    return ((nw.x, nw.y), (nw.x + 1, nw.y), (nw.x, nw.y + 1), (nw.x + 1, nw.y + 1))


def _ring(tiles):
    """The eight tiles orthogonally beside a 2x2 footprint -- where a mender can stand."""
    out = []
    for key in tiles:
        for _d, dx, dy in CARDINALS:
            step = (key[0] + dx, key[1] + dy)
            if step not in tiles and step not in out:
                out.append(step)
    return out


def _fresh(beat, rnd, slack=2):
    return beat > 0 and rnd - (beat - 1) <= slack


class Player:
    def __init__(self):
        self.kind = None
        self.round = 0
        # core
        self.spawned = 0
        self.cover = {}             # enemy turret id -> (pos, facing, hits our Core)
        self.spawn_role = 0
        self.own_tiles = ()
        self.last_hit = -1000
        self.prev_hp = None
        self.drops = []
        self.go = 1
        self.seen_turrets = {}      # enemy turret id -> round first seen near our Core
        self.eta = 0
        self.plan = None            # 'race' or 'mend', decided once their ring is in sight
        self.plan_round = 0
        # builder
        self.home = None
        self.enemy = None
        self.enemy_tiles = ()
        self.mine_tiles = ()
        self.role = None
        self.chain = None           # [ore, c1 .. ck] with ck beside our Core
        self.post = None            # mender: the ring tile we stand on
        self.sym = 'R'
        self.seen = set()
        self.walls = set()
        self.ore = set()
        self.blocked = set()        # cannot WALK here: barriers, harvesters, turrets, cores
        self.occupied = set()       # cannot BUILD here: the above plus conveyors and splitters
        self.built = 0
        self.width = 0
        self.height = 0
        self.spots = {}             # tile -> facing that puts the Core on its ray
        self.turrets = {}           # enemy turret id -> (pos, facing, covered tiles)
        self.goal = None
        self.path = []
        self._dist = {}
        self._came = {}
        # sentinel
        self.slot = None
        self.core_id = None

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

    def _read(self, ct, slot, default=0):
        try:
            return ct.read_store(slot)
        except Exception:
            return default

    def _write(self, ct, slot, value):
        try:
            ct.write_store(slot, max(0, int(value)))
        except Exception:
            pass

    # ------------------------------------------------------------------- core
    def _core(self, ct):
        if self.enemy is None:
            try:
                self.sym, self.enemy = _enemy_core(ct, ct.get_position())
                self.own_tiles = _footprint(ct.get_position())
            except Exception:
                self.enemy = None
        if self.enemy is not None:
            self._write(ct, SLOT_ENEMY, _pack(self.enemy))

        built = self._read(ct, SLOT_BUILT)
        alive = self._sentinels_alive(ct)
        their_dps, their_near = self._scan_home(ct)
        menders = self._menders_home(ct)
        try:
            ti = ct.get_global_resources()
            ammo = ct.get_global_ammo()
            hp = ct.get_hp()
        except Exception:
            return

        # Damage we can see coming, and damage we have actually taken: a Sentinel at the far
        # corner of its range is outside Core vision, so the HP ledger is the floor.
        drop = (self.prev_hp - hp) if self.prev_hp is not None else 0
        self.prev_hp = hp
        self.drops.append(max(0, drop))
        del self.drops[:-4]
        observed = (sum(self.drops) / len(self.drops)) if self.drops else 0
        their_dps = max(their_dps, observed)
        threatened = their_dps > 0
        if threatened:
            self.last_hit = self.round
        self._write(ct, SLOT_THREAT, self.round + 1 if threatened else 0)

        # ---- the books
        eheal = 4 * self._read(ct, SLOT_EHEAL)
        ehp = self._read(ct, SLOT_EHP) or 500
        our_dps = 9 * alive
        net_us = our_dps - eheal
        self.eta = self._read(ct, SLOT_ETA)
        remaining = max(0, SENTINEL_TARGET - built)
        ring_reserve = self._ring_reserve(ct, remaining)

        # ---- the race, called once
        # Rounds until each ring is complete.  Ours: the attack Builder's walk plus the builds
        # left.  Theirs: their Builder's distance from our Core once it is in sight, then the
        # placements we have watched.  A ring placed first wins the all-in exchange outright, so
        # the call is made the moment their Builder shows up and is not revisited: flip-flopping
        # buys one mender, which is exactly enough to lose the race and not enough to survive it.
        our_eta = 99
        if built >= SENTINEL_TARGET:
            our_eta = 0
        elif self.eta:
            our_eta = (self.eta - 1) + remaining
        their_eta = None
        if their_dps > 0:
            placed = len(self.seen_turrets)
            rounds = sorted(self.seen_turrets.values())
            rate = 1.5
            if len(rounds) >= 2:
                rate = max(1.0, (rounds[-1] - rounds[0]) / (len(rounds) - 1))
            their_eta = max(0, SENTINEL_TARGET - placed) * rate
        elif their_near is not None:
            their_eta = max(0, their_near - 1) + SENTINEL_TARGET * 1.5
        if self.plan is None and their_eta is not None:
            self.plan = 'race' if our_eta + RACE_MARGIN <= their_eta else 'mend'
            self.plan_round = self.round
        if self.plan == 'race' and self.round - self.plan_round > 8 and their_eta is not None:
            # re-check once the dust settles: an attacker that died, or a ring that never came
            if our_eta > their_eta + 4 and hp < 400:
                self.plan = 'mend'
        mend_first = self.plan == 'mend' and threatened
        mend_reserve = MEND_RESERVE if (threatened and menders) else 0

        # What the kill costs from here, if the ring is to keep shooting.
        full = 9 * SENTINEL_TARGET
        kill_ammo = (10.0 * ehp / 18.0) * (full / max(1, full - eheal)) if net_us > 0 or alive == 0 else 0
        bank = ammo + max(0, ti - ring_reserve - mend_reserve)
        t_us = None
        if net_us > 0:
            t_us = ehp / net_us

        # ---- menders
        want_menders = 0
        if self.plan == 'mend':
            want_menders = MENDERS_RACE
            if their_dps > 0:
                want_menders = min(MENDERS_MAX, max(MENDERS_RACE, (int(their_dps) + 8) // 9 + 1))
        elif self.plan is None and threatened:
            want_menders = min(MENDERS_MAX, (int(their_dps) + 8) // 9 + 1)
        if HOME_BUILDER_AT_START:
            want_menders = max(want_menders, 1)
        mining = _fresh(self._read(ct, SLOT_MINER), self.round, 2)
        home_builders = menders + (1 if mining else 0)
        need_menders = max(0, want_menders - home_builders)

        # ---- the attack Builder, then menders, then ammunition
        spawned_now = self._keep_attacker(ct, built)
        if not spawned_now and need_menders:
            cost = self._builder_cost(ct)
            if self.plan == 'mend' or mend_first:
                spare = ti - (ring_reserve if alive == 0 and built == 0 else 0)
            else:
                spare = ti - ring_reserve - mend_reserve - max(0, kill_ammo - ammo)
            if ti >= cost and spare >= cost:
                spawned_now = self._spawn_home(ct)

        # ---- GO / HOLD for the ring
        go = 1
        if alive and eheal > 0:
            if net_us <= 0:
                go = 0
            else:
                slack = BURST_SLACK * (0.6 if self.go else 1.0)
                go = 1 if (bank >= slack * kill_ammo or ehp <= GO_LOW_HP) else 0
        self.go = go
        self._write(ct, SLOT_GO, go)

        # ---- ammunition, lazily
        self._feed_ammo(ct, alive, go, ring_reserve, need_menders, threatened, mend_first)

        # ---- mining
        econ_ok = (not threatened and self.round - self.last_hit > 12
                   and (built >= SENTINEL_TARGET or self.round >= ECON_ROUND)
                   and need_menders == 0)
        self._write(ct, SLOT_ECON_OK, self.round + 1 if econ_ok else 0)

    def _builder_cost(self, ct):
        try:
            return ct.get_builder_bot_cost()
        except Exception:
            return 60

    def _ring_reserve(self, ct, remaining):
        if remaining <= 0:
            return 0
        try:
            unit = ct.get_sentinel_cost()
        except Exception:
            unit = 60
        return remaining * unit + 3 * remaining * (remaining - 1)

    def _sentinels_alive(self, ct):
        n = 0
        for i in range(SLOT_BEATS):
            if _fresh(self._read(ct, SLOT_BEAT0 + i), self.round, 2):
                n += 1
        return n

    def _menders_home(self, ct):
        """Our Builders standing on the ring around the Core -- the ones that can heal it now."""
        n = 0
        try:
            mine = ct.get_team()
            for uid in ct.get_nearby_units(8):
                if ct.get_team(uid) != mine or ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                    continue
                n += 1
        except Exception:
            pass
        return n

    def _scan_home(self, ct):
        """Enemy damage per round that can reach our Core, and the nearest enemy Builder's
        distance (Chebyshev, to the footprint) or None."""
        dps = 0
        near = None
        try:
            mine = ct.get_team()
            own = set(self.own_tiles)
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) == mine:
                    continue
                kind = ct.get_entity_type(uid)
                if kind == EntityType.BUILDER_BOT:
                    p = ct.get_position(uid)
                    d = min(max(abs(p.x - t[0]), abs(p.y - t[1])) for t in own)
                    if near is None or d < near:
                        near = d
                    continue
                if kind not in (EntityType.GUNNER, EntityType.SENTINEL):
                    continue
                p = ct.get_position(uid)
                facing = ct.get_direction(uid)
                known = self.cover.get(uid)
                if known is None or known[0] != (p.x, p.y) or known[1] != facing:
                    hits = False
                    try:
                        for t in ct.get_attackable_tiles_from(p, facing, kind):
                            if (t.x, t.y) in own:
                                hits = True
                                break
                    except Exception:
                        hits = True
                    known = ((p.x, p.y), facing, hits)
                    self.cover[uid] = known
                if known[2]:
                    dps += 9 if kind == EntityType.SENTINEL else 7
                    if uid not in self.seen_turrets:
                        self.seen_turrets[uid] = self.round
        except Exception:
            pass
        return dps, near

    def _race(self, alive, their_dps, eheal, menders, hp, ehp):
        """Project both kills a few dozen rounds out.

        Our ring grows one Sentinel a round once the attack Builder reaches its anchor (it
        publishes the walk left).  Theirs grows at the pace we have watched it grow, two rounds
        a turret until we have seen better.  Returns (rounds until their Core dies, rounds until
        ours does), None where the menders win.
        """
        walk = max(0, self.eta - 1) if self.eta else (0 if alive else 99)
        remaining = max(0, SENTINEL_TARGET - alive)
        rounds = sorted(self.seen_turrets.values())
        rate = 2.0
        if len(rounds) >= 2:
            rate = max(1.0, (rounds[-1] - rounds[0]) / (len(rounds) - 1))
        last = rounds[-1] if rounds else self.round
        theirs_now = their_dps
        t_us = t_them = None
        hu, ht = hp, ehp
        for r in range(1, 81):
            ours = 9 * min(SENTINEL_TARGET, alive + max(0, r - walk)) if remaining else 9 * alive
            if theirs_now > 0:
                grown = int((self.round + r - last) / rate)
                theirs = min(36, theirs_now + 9 * max(0, grown))
            else:
                theirs = 0
            ht -= max(0, ours - eheal)
            hu -= max(0, theirs - 4 * menders)
            if t_us is None and ht <= 0:
                t_us = r
            if t_them is None and hu <= 0:
                t_them = r
            if t_us is not None and t_them is not None:
                break
        return t_us, t_them

    def _keep_attacker(self, ct, built):
        if built >= SENTINEL_TARGET:
            return False
        if self.spawned and not REPLACE_BUILDER:
            return False
        if self.spawned:
            beat = self._read(ct, SLOT_BUILDER)
            if _fresh(beat, self.round, 2):
                return False
            if self.round < 4:
                return False
        self.spawn_role = 0
        return self._spawn_one(ct, toward_enemy=True)

    def _spawn_home(self, ct):
        self.spawn_role = 1
        ok = self._spawn_one(ct, toward_enemy=False)
        return ok

    def _spawn_one(self, ct, toward_enemy):
        """Attackers spawn on the ring tile nearest the enemy (the seats otherwise start with
        different walks); menders on an orthogonal ring tile so they can heal without a step."""
        try:
            if ct.get_global_resources() < ct.get_builder_bot_cost():
                return False
            ring = set(_ring(self.own_tiles))
            best = None
            chosen = None
            for tile in ct.get_nearby_tiles(2):
                if not ct.can_spawn(tile):
                    continue
                key = (tile.x, tile.y)
                gap = abs(tile.x - self.enemy.x) + abs(tile.y - self.enemy.y)
                if toward_enemy:
                    score = gap
                else:
                    score = (0 if key in ring else 100) + gap
                if best is None or score < best:
                    best, chosen = score, tile
            if chosen is None:
                return False
            ct.spawn_builder(chosen)
            self.spawned += 1
            return True
        except Exception:
            return False

    def _feed_ammo(self, ct, alive, go, ring_reserve, need_menders, threatened, mend_first):
        """Keep two shots per living Sentinel banked, and nothing more: titanium is flexible,
        ammunition is not.  The burst is paid for the round the Core says GO."""
        try:
            ammo = ct.get_global_ammo()
            ti = ct.get_global_resources()
            reserve = ring_reserve + (MEND_RESERVE if threatened else 0)
            if need_menders and mend_first:
                reserve += self._builder_cost(ct)
            if alive == 0:
                # nothing can shoot yet; a small float so the first turret fires the round it stands
                want = 20 if ammo < 20 else 0
            elif go:
                want = AMMO_PER_SENTINEL * alive - ammo
            else:
                want = 10 - ammo                   # one sniping shot at a time
            if want <= 0:
                return
            spare = ti - reserve
            amount = min(want, spare)
            if amount >= 10 and ct.can_convert_ammo(amount):
                ct.convert_ammo(amount)
        except Exception:
            return

    # ---------------------------------------------------------------- builder
    def _builder(self, ct):
        here = ct.get_position()
        if self.home is None:
            self._orient(ct, here)
        if self.role is None:
            # The Core spawns an attacker only while no attacker is reporting and the ring is
            # unfinished; everything else it spawns minds the Core.  Same snapshot, same rule.
            ring_done = self._read(ct, SLOT_BUILT) >= SENTINEL_TARGET
            attacker_alive = _fresh(self._read(ct, SLOT_BUILDER), self.round, 2)
            self.role = 'home' if (ring_done or attacker_alive) else 'attack'

        if self.role == 'home':
            self._home(ct, here)
            return

        self._write(ct, SLOT_BUILDER, self.round + 1)
        self._observe(ct, here)
        self._dist, self._came = self._flood(here, self._threats(ct))

        if self.built < SENTINEL_TARGET:
            self.goal = self._next_stand(here)
            walk = self._dist.get(self.goal, 99) if self.goal is not None else 99
            if self._anchor_value((here.x, here.y)):
                walk = 0                           # a spot beside us: we build this round
            self._write(ct, SLOT_ETA, min(98, walk) + 1)
            if self._place(ct, here):
                return
            if self._advance(ct, here):
                return
            self._break_through(ct, here)
            return
        self._write(ct, SLOT_ETA, 1)
        self._report_enemy(ct)
        self._tend(ct, here)

    def _report_enemy(self, ct):
        """Menders beside the enemy Core and its HP, for the Core's arithmetic."""
        try:
            ring = set(_ring(self.enemy_tiles))
            mine = ct.get_team()
            n = 0
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) == mine or ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                    continue
                p = ct.get_position(uid)
                if (p.x, p.y) in ring:
                    n += 1
            self._write(ct, SLOT_EHEAL, n)
            bid = ct.get_tile_building_id(Position(self.enemy.x, self.enemy.y))
            if bid is not None:
                self._write(ct, SLOT_EHP, ct.get_hp(bid))
        except Exception:
            pass

    # -- home: mend, and mine when nothing is shooting ------------------------
    def _home(self, ct, here):
        self._observe(ct, here)
        threatened = _fresh(self._read(ct, SLOT_THREAT), self.round, 1)
        core_tiles = self.mine_tiles
        # 1. heal the Core if it is hurt and we are beside it
        try:
            for _d, dx, dy in CARDINALS:
                key = (here.x + dx, here.y + dy)
                if key not in core_tiles:
                    continue
                bid = ct.get_tile_building_id(Position(key[0], key[1]))
                if bid is not None and ct.get_hp(bid) < ct.get_max_hp(bid) and ct.can_heal(Position(key[0], key[1])):
                    ct.heal(Position(key[0], key[1]))
                    return
        except Exception:
            pass
        # 2. mining, if the Core is paying and nobody else is on it
        if not threatened and _fresh(self._read(ct, SLOT_ECON_OK), self.round, 1):
            miner = self._read(ct, SLOT_MINER)
            mine_is_me = self.chain is not None and self.chain != []
            if mine_is_me or not _fresh(miner, self.round, 2):
                self._dist, self._came = self._flood(here, None)
                if self._mine(ct, here):
                    self._write(ct, SLOT_MINER, self.round + 1)
                    return
        # 3. mend anything of ours beside us
        try:
            for _d, dx, dy in CARDINALS:
                spot = Position(here.x + dx, here.y + dy)
                bid = ct.get_tile_building_id(spot)
                if bid is None or ct.get_team(bid) != ct.get_team():
                    continue
                if ct.get_hp(bid) < ct.get_max_hp(bid) and ct.can_heal(spot):
                    ct.heal(spot)
                    return
        except Exception:
            pass
        # 4. stand on the ring
        self._to_post(ct, here)

    def _to_post(self, ct, here):
        if self.post is not None and (here.x, here.y) == self.post:
            return
        self._dist, self._came = self._flood(here, None)
        # closest free ring tile; prefer the side facing the enemy so the walk to mine is short
        best = None
        chosen = None
        for key in _ring(self.mine_tiles):
            if key in self.walls or key in self.blocked:
                continue
            cost = self._dist.get(key)
            if cost is None:
                continue
            if self._tile_has_builder(ct, key) and key != (here.x, here.y):
                continue
            score = cost
            if best is None or score < best:
                best, chosen = score, key
        self.post = chosen
        if chosen is None or chosen == (here.x, here.y):
            return
        path = self._trace(self._came, here, chosen)
        if path:
            self._step_to(ct, here, path[0])

    def _tile_has_builder(self, ct, key):
        try:
            for uid in ct.get_nearby_units(4):
                if ct.get_entity_type(uid) == EntityType.BUILDER_BOT:
                    p = ct.get_position(uid)
                    if (p.x, p.y) == key:
                        return True
        except Exception:
            pass
        return False

    def _mine(self, ct, here):
        """One Harvester and a belt to the Core.  Returns True while there is a job in hand."""
        if self.chain is None:
            self.chain = self._plan_chain(ct) or []
        if not self.chain:
            return False
        try:
            ti = ct.get_global_resources()
        except Exception:
            return False
        # Lay the belt from the Core end outward; every tile points at the next one toward the
        # Core, and the last one points into the Core itself.
        for idx in range(len(self.chain) - 1, 0, -1):
            key = self.chain[idx]
            if key in self.occupied:
                continue
            onward = self.chain[idx + 1] if idx + 1 < len(self.chain) else self._core_tile_beside(key)
            facing = None
            for direction, dx, dy in CARDINALS:
                if (key[0] + dx, key[1] + dy) == onward:
                    facing = direction
                    break
            if facing is None:
                continue
            try:
                if ti < ct.get_conveyor_cost() + ECON_MARGIN:
                    return True
            except Exception:
                pass
            if abs(key[0] - here.x) + abs(key[1] - here.y) == 1:
                try:
                    if ct.can_build_conveyor(Position(key[0], key[1]), facing):
                        ct.build_conveyor(Position(key[0], key[1]), facing)
                        self.occupied.add(key)
                        return True
                except Exception:
                    pass
            self._walk_beside(ct, here, key)
            return True
        ore = self.chain[0]
        if ore not in self.occupied:
            try:
                if ti < ct.get_harvester_cost() + ECON_MARGIN:
                    return True
            except Exception:
                pass
            if abs(ore[0] - here.x) + abs(ore[1] - here.y) == 1:
                try:
                    if ct.can_build_harvester(Position(ore[0], ore[1])):
                        ct.build_harvester(Position(ore[0], ore[1]))
                        self.occupied.add(ore)
                        self.chain = []
                        return True
                except Exception:
                    pass
            self._walk_beside(ct, here, ore)
            return True
        self.chain = []
        return False

    def _core_tile_beside(self, key):
        for _d, dx, dy in CARDINALS:
            step = (key[0] + dx, key[1] + dy)
            if step in self.mine_tiles:
                return step
        return key

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
        self.sym, self.enemy = _enemy_core(ct, core)
        told = _unpack(self._read(ct, SLOT_ENEMY))
        if told is not None:
            self.enemy = Position(told[0], told[1])
        self.enemy_tiles = _footprint(self.enemy)
        self.mine_tiles = _footprint(core)
        self._seed_terrain(core)
        self.spots = self._firing_spots()
        for tile in self.enemy_tiles:
            self.blocked.add(tile)
            self.occupied.add(tile)
        for tile in _footprint(core):
            self.blocked.add(tile)
            self.occupied.add(tile)

    def _firing_spots(self):
        """Every tile from which a Sentinel could hit the Core, with the facing that does it."""
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
                elif grid[row + x] == '2':
                    self.ore.add(key)

    # ------------------------------------------------------------------ economy
    def _plan_chain(self, ct):
        """Pick an ore tile and the belt that carries it home: [ore, c1, ..., ck], ck beside the Core."""
        ring = []
        for key in self.mine_tiles:
            for _d, dx, dy in CARDINALS:
                step = (key[0] + dx, key[1] + dy)
                if step not in self.mine_tiles and self._passable(step) and step not in self.occupied:
                    ring.append(step)
        if not ring:
            return None
        dist = {}
        came = {}
        frontier = []
        for key in ring:
            dist[key] = 0
            came[key] = None
            frontier.append(key)
        goal = None
        while frontier and goal is None:
            nxt = []
            for key in frontier:
                if key in self.ore and key not in self.occupied:
                    goal = key
                    break
                if dist[key] > 12:
                    continue
                for _d, dx, dy in CARDINALS:
                    step = (key[0] + dx, key[1] + dy)
                    if step in dist or step in self.walls or step in self.mine_tiles:
                        continue
                    if step in self.occupied and step not in self.ore:
                        continue
                    if not (0 <= step[0] < self.width and 0 <= step[1] < self.height):
                        continue
                    dist[step] = dist[key] + 1
                    came[step] = key
                    nxt.append(step)
            if goal is not None:
                break
            frontier = nxt
        if goal is None:
            return None
        chain = []
        walk = goal
        while walk is not None:
            chain.append(walk)
            walk = came[walk]
        return chain

    def _walk_beside(self, ct, here, key):
        """One step toward standing NEXT TO a tile -- building never happens from on top of it."""
        best = None
        chosen = None
        for _d, dx, dy in CARDINALS:
            step = (key[0] + dx, key[1] + dy)
            cost = self._dist.get(step)
            if cost is not None and (best is None or cost < best):
                best, chosen = cost, step
        if chosen is None or chosen == (here.x, here.y):
            return
        path = self._trace(self._came, here, chosen)
        if path:
            self._step_to(ct, here, path[0])

    def _observe(self, ct, here):
        try:
            tiles = ct.get_nearby_tiles()
        except Exception:
            return
        for pos in tiles:
            key = (pos.x, pos.y)
            self.seen.add(key)
            twin = _mirror(self.sym, self.width, self.height, key)
            self.seen.add(twin)
            try:
                env = ct.get_tile_env(pos)
                if env == Environment.WALL:
                    self.walls.add(key)
                    self.walls.add(twin)
                    continue
                if env == Environment.ORE_TITANIUM:
                    self.ore.add(key)
                    self.ore.add(twin)
            except Exception:
                continue
            if key in self.enemy_tiles or key in self.mine_tiles:
                continue
            try:
                bid = ct.get_tile_building_id(pos)
            except Exception:
                continue
            if bid is None:
                self.blocked.discard(key)
                self.occupied.discard(key)
            else:
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

    # -- lane choice ---------------------------------------------------------
    def _passable(self, key):
        if key in self.walls or key in self.blocked:
            return False
        return 0 <= key[0] < self.width and 0 <= key[1] < self.height

    def _free_spot(self, key):
        return (key in self.spots and key not in self.walls
                and key not in self.occupied
                and 0 <= key[0] < self.width and 0 <= key[1] < self.height)

    def _place(self, ct, here):
        """Build on an adjacent firing spot -- unless that spot is on our own route to the anchor.

        v72 on fimbulwinter: one step short of an anchor with three free neighbours, the Builder
        dropped turrets on the two tiles its route ran through, walled itself off, and took a
        nine-round detour to reach the other side.  A turret placed where we were about to walk
        costs more rounds than it saves.
        """
        at_goal = self.goal is None or (here.x, here.y) == self.goal
        if not at_goal and not self._path_usable(here, self.goal):
            self.path = self._trace(self._came, here, self.goal)
        route = set(self.path) if not at_goal else set()
        for _d, dx, dy in CARDINALS:
            key = (here.x + dx, here.y + dy)
            if not self._free_spot(key):
                continue
            if key in route:
                continue
            if not at_goal and self.goal is not None and not self._still_reachable(here, key):
                continue
            if self.built + 1 < SENTINEL_TARGET and not self._exit_besides(here, key):
                continue                           # three turrets and a wall make a cell
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
            self._write(ct, SLOT_BUILT, self.built)
            return True
        return False

    def _exit_besides(self, here, key):
        for _d, dx, dy in CARDINALS:
            step = (here.x + dx, here.y + dy)
            if step != key and self._passable(step):
                return True
        return False

    def _still_reachable(self, here, key):
        """Would the anchor still be as close with a turret on `key`?  One extra sweep, only on the
        rounds we are about to build off-anchor."""
        before = self._dist.get(self.goal)
        if before is None:
            return True
        self.blocked.add(key)
        dist, _came = self._flood(here, None)
        self.blocked.discard(key)
        after = dist.get(self.goal)
        return after is not None and after <= before + 1

    def _next_stand(self, here):
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
        """How many Sentinels could be planted from this tile -- keeping an exit if the ring
        will not be finished here.  Three turrets and a wall make a cell; on midgard the Builder
        sat in one for the rest of the match with the fourth spot two tiles away."""
        usable = 0
        exits = 0
        for _d, dx, dy in CARDINALS:
            step = (key[0] + dx, key[1] + dy)
            if self._passable(step):
                exits += 1
            if self._free_spot(step):
                usable += 1
        want = SENTINEL_TARGET - self.built
        if usable < want:
            usable = min(usable, exits - 1)
        return max(0, usable)

    def _threats(self, ct):
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
        """Dial's algorithm from the Builder; seen tiles cost 1, unseen UNKNOWN_COST, threatened
        tiles THREAT_COST extra.  Returns (cost, came_from)."""
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
                    continue
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
        best = None
        chosen = None
        for key, cost in self._dist.items():
            gap = max(abs(key[0] - self.enemy.x), abs(key[1] - self.enemy.y))
            score = (gap, cost)
            if best is None or score < best:
                best, chosen = score, key
        return chosen

    def _advance(self, ct, here):
        goal = self.goal
        if goal is None or (here.x, here.y) == goal:
            return False
        if not self._path_usable(here, goal):
            self.path = self._trace(self._came, here, goal)
            if not self.path:
                _d, came = self._flood(here, None)
                self.path = self._trace(came, here, goal)
        if not self.path:
            return False
        if self._step_to(ct, here, self.path[0]):
            self.path.pop(0)
            return True
        self.path = []
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
        if self.enemy is None:
            found = _unpack(self._read(ct, SLOT_ENEMY))
            if found is None:
                return
            self.enemy = Position(found[0], found[1])
            self.enemy_tiles = _footprint(self.enemy)
        if self.slot is None:
            # claim the first heartbeat slot nobody living is using
            for i in range(SLOT_BEATS):
                if not _fresh(self._read(ct, SLOT_BEAT0 + i), self.round, 2):
                    self.slot = i
                    break
            if self.slot is None:
                self.slot = SLOT_BEATS - 1
        self._write(ct, SLOT_BEAT0 + self.slot, self.round + 1)
        self._report_enemy(ct)

        go = self._read(ct, SLOT_GO, 1)
        if go:
            for key in self.enemy_tiles:
                spot = Position(key[0], key[1])
                try:
                    if ct.can_fire(spot):
                        ct.fire(spot)
                        return
                except Exception:
                    continue
            return
        # HOLD: the menders make the Core a bad target.  Snipe a mender on our ray instead.
        try:
            ring = set(_ring(self.enemy_tiles))
            mine = ct.get_team()
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) == mine or ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                    continue
                p = ct.get_position(uid)
                if (p.x, p.y) not in ring:
                    continue
                if ct.can_fire(p):
                    ct.fire(p)
                    return
        except Exception:
            return
