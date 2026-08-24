"""brynhildr -- hildr's Sentinel rush in steward's armour.

Lineage: hildr@7a6d86c (the rush, the race arithmetic, the walk) + the measured half of
steward_hardened_reinforced@366cd1b (the economy that wins timeouts, the home guard that
survives sieges).  Everything hildr did is still here; what is new is why it lost.

WHAT THE LADDER REPLAYS OF hildr@7a6d86c SHOWED (2026-08-23)

  * Every loss to TRRR, I Stone and farming_200s was a round-1000 timeout on titanium
    collected.  On holmgang hildr ended with 1,845 Ti banked, four idle Builders and ZERO
    Harvesters against TRRR's 10,405: TRRR walled all eight tiles around our Core with
    barriers, the belt planner needs a free Core-adjacent tile, and nobody shot the wall.
    The ring was dug out by round 136 and never rebuilt, because hildr only restarted the
    ring when the attack Builder was DEAD -- a live attacker tended nothing for 700 rounds.
  * On paths the ring stood all game and the Core sat on 15 Ti for 800 rounds: the 20-ammo
    snipe float was re-fired every time passive income refilled it, so the stall-economy
    miner was never affordable.
  * Losses to gsxWins were Core kills: two enemy Sentinels at 18 HP/round against menders
    that could not be paid -- mending costs 4.5 Ti/round at that rate and passive income is
    2.5 -- and no turret of ours ever answered them.

WHAT IS DIFFERENT

  Economy is a first-class purchase, not a stall reflex.  Once the ring is up (or by round
  ECON_ROUND) the Core buys a miner unless the kill is funded from the bank right now --
  hildr's all-in survives exactly where it was right, the pure race.  Miners lay Harvesters
  and belts, JOIN existing belts, REPAIR holes (steward's REPAIR_NETWORK), recount
  Harvesters that died, and shoot their way out of a barrier box.  The snipe float is
  refilled only after the miner is paid.

  Home defence is steward's, in hildr's priority order: mend first (4 HP/Ti beats anything),
  then a 3 Ti barrier in a live Gunner lane, then -- when a siege has lasted and the bank
  allows -- one counter-turret seated on a ray to the turret shooting us (a Sentinel cannot
  rotate off it), and a rotatable Gunner against Builders loitering at our Core.  Guard
  Sentinels shoot turrets, then Builders, then the enemy economy, then untended barriers.

  The ring rebuilds itself: the attack Builder re-plants any Sentinel it sees destroyed, on a
  spot no known enemy turret covers, and the Core resets the ring when every heartbeat is
  gone whether or not the attacker survived.

  Comms re-plan (16 slots): the attacker's ETA rides in its heartbeat, the Core's orders to
  the home squad are flags in one word, and home Builders heartbeat in three slots carrying
  their mining state and Harvester tally.
"""

from fcode import Controller, Direction, Environment, EntityType, Position

try:
    from terrain import INDEX as _MAP_INDEX, WALLS as _MAP_WALLS
except Exception:          # unknown deployment -- fall back to observation
    _MAP_INDEX, _MAP_WALLS = {}, {}

# ---------------------------------------------------------------------------- tuning (hildr)
SENTINEL_TARGET = 4        # smallest ring that kills through a full heal ring (36 > 32 HP/round)
MAX_RANGE_SQ = 32          # Sentinel attack radius^2
GUNNER_RANGE_SQ = 13
REPLACE_BUILDER = True     # re-spawn a dead attack Builder while the ring is unfinished
UNKNOWN_COST = 3           # what a tile we have never seen costs, against 1 for one we have
CHAIN_STAGING_EXCLUDED = {
    ((14, 18), (6, 4)), ((14, 18), (6, 12)),
    ((16, 16), (2, 11)),
    ((24, 24), (20, 20)), ((16, 16), (7, 13)),
    ((20, 20), (16, 9)), ((12, 8), (0, 6)),
}
THREAT_COST = 8            # detour a Builder will accept to stay out of a threatened tile
ANCHOR_BONUS = 2           # steps of walking each extra buildable neighbour is worth
USE_BUNDLED_TERRAIN = True # seed the wall map from terrain.py for the known pool
CPU_BUDGET_US = 7000       # stop optional work well inside the 10 ms limit

HOME_BUILDER_AT_START = False  # a Builder at home on round 0 costs 60 Ti effective: six shots, the kill
MENDERS_MAX = 5            # never more than this many Builders minding the Core
RACE_MARGIN = 0            # rounds our ring must lead theirs by to go all-in (a dead heat races)
MEND_RESERVE = 30          # titanium kept for mending while anything is shooting us
AMMO_PER_SENTINEL = 20     # ammunition kept banked per living Sentinel (two shots each)
BURST_SLACK = 0.85         # GO when the bank covers this fraction of the finish
ECON_ROUND = 40            # no Harvester before this unless the ring is already up
ECON_MARGIN = 20           # titanium kept over the build cost before the miner starts a job
ECON_RESERVE = 90          # titanium set aside for the Harvester and belt while the kill is far off
SNIPE_BANK = 20            # ammunition banked before the ring snipes: two shots kill a Harvester
GO_LOW_HP = 120            # always finish a Core this low if we out-damage the menders
TIE_FLOOR = 8              # titanium never converted: the dead-heat tiebreak (hildr keeps 5)
STALL_ROUNDS = 15          # HOLD this long with a quiet home means the game is now an income race
RING_EXTRA_MAX = 2         # Sentinels added past four when the stall bank outgrows the burst
ATTACKER_DIG_REACH = 0     # steps the attack Builder walks to dig out a turret shooting the ring

# ---------------------------------------------------------------------------- tuning (new)
ECON_AFTER_RING = True     # the first miner is bought once the ring is up, not once the rush stalls
ECON_OPENING = True        # ...or right behind the attacker, at 1.2x scale instead of the 2.2x the ring leaves
BELT_MARGIN = 10           # titanium kept over a conveyor's cost before it is laid
SILENT_TURRET_ROUNDS = 10  # a turret that has not landed damage for this long is a loaded gun, not a siege
MINERS_MAX = 3             # home Builders mining at once (hildr's MINERS_STALL)
HARVESTERS_MAX = 5         # Harvesters the miners keep laying while the Core pays
LONG_GAME_ROUND = 120      # past this, a second miner: the tiebreak is titanium collected
JOIN_BELTS = True          # a new chain may end on an existing belt of ours instead of the Core
REPAIR_BELTS = True        # relay a conveyor shot out of our own line (3 Ti restores the whole line)
REPAIR_ATTEMPT_LIMIT = 3   # give a tile up after this many failed relays: a turret owns it
RING_LOST_ROUNDS = 12      # no Sentinel heartbeat for this long: the ring is gone, start over
REBUILD_RING = True        # the attacker re-plants Sentinels it sees destroyed
QUICK_LOSS_ROUNDS = 15     # a Sentinel dead this soon after placement poisons its spot
RING_PAUSE_LOSSES = 3      # quick losses before the attacker stops feeding the grinder...
RING_PAUSE_ROUNDS = 80     # ...for this long (Torsko dug 22 rebuilt Sentinels out of the same two spots)
SLOT_BUILT_PAUSED = 256    # bit in SLOT_BUILT: the attacker is holding; the Core frees the ring reserve
AVOID_COVERED_SPOTS = True # never plant a Sentinel on a tile a known enemy turret covers, if there is a choice
LANE_BARRIERS = True       # a 3 Ti barrier in a live enemy Gunner lane onto our Core
COUNTER_TURRETS = True     # a home turret seated on a ray to a turret that is shooting our Core
ANTI_BUILDER_GUNNER = False  # measured off: a harassment squad digs a Gunner out faster than it kills one
HOME_TURRET_MAX = 3        # home turrets, all kinds, standing at once
HOME_TURRET_LIFETIME = 4   # home turrets ever bought: nine Gunners went up and came down on holmgang
HOME_TURRET_COOLDOWN = 40  # rounds after a home turret dies before another is bought
DEFEND_AFTER_ROUNDS = 8    # rounds of sustained fire before a counter-turret is bought (hp < 300 skips the wait)
LOITER_ROUNDS = 6          # rounds an enemy Builder has to hang about our Core before a Gunner answers it
LOITER_REACH = 2           # Chebyshev distance from the footprint that counts as loitering
ROTATE_RESERVE = 40        # a Gunner turns only while the bank holds this much (rotation is 10 Ti)
DENY_ORE = True            # the idle attacker barriers enemy-half ore tiles (a Harvester denied for the match)
SHIELD_RING = True         # a barrier in every Gunner lane onto a ring Sentinel (steward's wrap, only where needed)
DENY_REACH = 6             # walking steps the attacker will go to deny an ore
BREAK_OUT = True           # a walled-in home Builder shoots the enemy barrier in its way
REPLACEMENT_DAMP_AFTER = 8 # hildr/steward: past this many spawns, each further Builder needs 150 Ti behind it

# communication store
SLOT_BUILT = 0             # Sentinels placed, written by the attack Builder (the Core writes 0 to restart)
SLOT_BUILDER = 1           # attack Builder heartbeat: (round + 1) + 65536 * (eta + 1 | scouting bits, see ATK_*)
SLOT_ENEMY = 2             # enemy Core, packed (x + 1) * 64 + y, + 65536 * (ring_extra | HOLD_REBUILD), by our Core
HOLD_REBUILD = 4           # bit in the extra word: do not replace a lost Sentinel, the kill is funded as we stand
RING_HOLD = 8              # bit in the extra word: stop placing Sentinels, the titanium is the mend squad's
MEND_SQUAD_MAX = 4         # menders bought under the mend plan: 16 HP a round outlasts a ring's 29 shots
RING_RESUME_QUIET = 25     # rounds without damage, at 400+ HP, before a held ring is released
SLOT_ORDERS = 3            # Core -> home squad: (round + 1) + 65536 * flags (see ORD_*)
SLOT_BEAT0 = 4             # Sentinel heartbeats, one slot each: round + 1
SLOT_BEATS = 5             # slots 4..8
SLOT_SHOOTER = 9           # Core -> home: a turret hitting our Core, packed, + 65536 * (1 Sentinel | 2 + facing*4 Gunner)
SLOT_EHEAL = 10            # enemy Builders beside the enemy Core, written by the ring
SLOT_GO = 11               # 1: shoot the Core.  0: hold, snipe menders, bank.  2: one volley
SLOT_EHP = 12              # enemy Core HP, written by the ring (0 = unknown)
SLOT_HOME0 = 13            # home Builder heartbeats: (round + 1) + 65536 * (mining | harvesters << 1)
SLOT_HOMES = 3             # slots 13..15

ATK_ECON = 1 << 8          # the attacker has seen a Harvester or belt of theirs
ATK_RUSH = 1 << 9          # the attacker has seen a Builder of theirs on our side of the map
ATK_BUILDERS_SHIFT = 10    # bits 10-12: distinct enemy Builders the attacker has seen, 0-7

ORD_THREAT = 1             # something that can hit our Core is in sight / hitting it
ORD_ECON = 2               # the Core is willing to pay for mining
ORD_TURRET = 4             # a counter-turret may be bought against the turret shooting us
ORD_GUNNER = 8             # an anti-Builder Gunner may be bought
ORD_QUIET = 16             # nothing has hit us for a while (miners may roam)
ORD_MINERS_SHIFT = 5       # bits 5-6: home Builders (by slot) that may mine, 0-3
ORD_HARVEST_SHIFT = 7      # bits 7-9: Harvesters standing, 0-7, as tallied by the miners
ORD_SAVE = 1 << 10         # a counter-turret is wanted and not yet affordable: no 1 Ti heals while the Core can take it
ORD_RACE = 1 << 11         # the ring is shooting and the kill is funded: menders mend, nothing else


def _pack(pos, extra=0):
    return (pos.x + 1) * 64 + pos.y + extra * 65536


def _unpack(word):
    word %= 65536
    return None if word <= 0 else (word // 64 - 1, word % 64)


def _extra(word):
    return word // 65536


def _beat(word):
    return word % 65536


def _flags(word):
    return word // 65536


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


def _cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _on_ray(origin, delta, targets, reach_sq):
    """Does a turret at origin facing delta reach any of targets along its line?"""
    dx, dy = delta
    if dx == 0 and dy == 0:
        return False
    for key in targets:
        ox, oy = key[0] - origin[0], key[1] - origin[1]
        if ox * ox + oy * oy > reach_sq:
            continue
        if dx == 0:
            if ox == 0 and oy * dy > 0:
                return True
        elif dy == 0:
            if oy == 0 and ox * dx > 0:
                return True
        elif ox * dy == oy * dx and ox * dx > 0:
            return True
    return False


def _facing_to(frm, to):
    """The compass direction from frm to an orthogonal neighbour to, else None."""
    for direction, dx, dy in CARDINALS:
        if (frm[0] + dx, frm[1] + dy) == to:
            return direction
    return None


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
        self.last_damage = -1000
        self.threat_start = None
        self.prev_hp = None
        self.drops = []
        self.go = 1
        self.seen_turrets = {}      # enemy turret id -> round first seen near our Core
        self.eta = 0
        self.plan = None            # 'race' or 'mend', decided once their ring is in sight
        self.prev_ehp = None
        self.prev_ammo = None
        self.converted = 0
        self.heals = []
        self.shots = []
        self.go_held = False
        self.hold_total = 0
        self.spawn_total = 0
        self.prev_menders = 0
        self.home_deaths = 0
        self.quiet_since = 0
        self.ring_extra = 0
        self.plan_round = 0
        self.ring_seen = 0
        self.loiter = 0
        self.home_turrets = 0
        self.shooter = None
        self.miners_hwm = 0         # miners ever wanted: a working miner keeps working through a burst
        self.scout_econ = False     # the attacker has seen their economy
        self.scout_rush = False     # the attacker has seen their attacker, or we have
        self.hold_rebuild = False   # the kill is funded with the ring as it stands: no replacements
        self.ring_was_full = False  # every Sentinel of the ring has reported at least once
        self.place_rounds = []      # rounds our ring grew, for the measured placement rate
        self.prev_built = 0
        self.ring_hold = False      # the mend plan: no more Sentinels until home is safe
        self.gunners_close = 0
        self.gunners_far = 0
        self.sentinels_on_us = 0
        self.turret_ids = set()     # every home turret of ours the Core has ever seen
        self.turret_lost = -1000    # round a home turret was last seen gone
        # builder
        self.home = None
        self.enemy = None
        self.enemy_tiles = ()
        self.mine_tiles = ()
        self.role = None
        self.chain = None           # [ore, c1 .. ck] with ck beside the chain end
        self.chain_end = None       # the tile the last conveyor of the chain points into
        self.replan_at = 0
        self.post = None            # mender: the ring tile we stand on
        self.digging = False
        self.sym = 'R'
        self.seen = set()
        self.walls = set()
        self.ore = set()
        self.blocked = set()        # cannot WALK here: barriers, harvesters, turrets, cores
        self.occupied = set()       # cannot BUILD here: the above plus conveyors and splitters
        self.enemy_barriers = set() # enemy barriers we have seen (cleared when seen gone)
        self.built = 0
        self.placed = []            # ring tiles this attacker has planted
        self.last_place = -10
        self.last_eta = 99
        self.ring_done_once = False # this attacker has completed the ring at least once
        self.placed_round = {}      # ring tile -> round planted
        self.poisoned = set()       # spots where a Sentinel died within QUICK_LOSS_ROUNDS
        self.quick_losses = 0
        self.pause_until = -1
        self.enemy_ids = set()      # distinct enemy Builders seen
        self.econ_seen = False      # a Harvester or belt of theirs
        self.rush_seen = False      # a Builder of theirs on our side of the map
        self.width = 0
        self.height = 0
        self.spots = {}             # tile -> facing that puts the Core on its ray
        self.turrets = {}           # enemy turret id -> (pos, facing, covered tiles)
        self.covered = set()        # tiles to keep out of when walking: lanes, Launchers, Builders
        self.lanes = set()          # tiles a known enemy turret can shoot, refreshed each turn
        self.home_danger = set()    # lanes that shoot a Builder: Gunners, and Sentinels not aimed at our Core
        self.grabs = set()          # tiles beside an enemy Launcher: it picks a Builder up from there
        self.goal = None
        self.path = []
        self._dist = {}
        self._came = {}
        self.ring_target = SENTINEL_TARGET
        self.stand_rounds = 0       # rounds at the anchor without placing
        self.home_slot = None
        self.laid = {}              # conveyor tile -> facing, laid by this miner
        self.my_harvesters = set()
        self.repair_fail = {}
        self.mining_now = False
        self.team_harvesters = 0
        self.chain_staging = True
        self.belts = {}             # conveyor tile -> facing, every belt of ours we have seen
        self.belt_seen = {}         # conveyor tile -> round last in sight
        self.my_barriers = set()    # lane barriers this Builder laid
        self.deny_target = None
        self.denied = set()
        # sentinel
        self.slot = None
        self.guard = None           # True for a home-guard Sentinel (cannot reach the enemy Core)
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
        elif self.kind == EntityType.GUNNER:
            self._gunner(ct)
        elif self.kind == EntityType.LAUNCHER:
            self._launcher(ct)

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
            self._write(ct, SLOT_ENEMY, _pack(self.enemy, self.ring_extra
                                                | (HOLD_REBUILD if self.hold_rebuild else 0)
                                                | (RING_HOLD if self.ring_hold else 0)))

        built_word = self._read(ct, SLOT_BUILT)
        built = built_word & 0xFF
        ring_paused = bool(built_word & SLOT_BUILT_PAUSED)
        if built > self.prev_built:
            self.place_rounds.append(self.round)
        self.prev_built = built
        alive = self._sentinels_alive(ct)
        their_dps, their_near, loiterers, shooters = self._scan_home(ct)
        menders = self._menders_home(ct)
        homes = self._home_reports(ct)
        self.home_turrets = self._own_turrets_home(ct)
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
        if drop > 0:
            self.last_damage = self.round
        # The ledger shows the NET drop: what landed minus what the menders put back.  Two
        # menders restoring 8 against a Sentinel's 9 read as 1 HP/round and sized the squad
        # at two for 230 rounds while the Core bled out with 115 Ti in the bank.
        if observed > 0 and hp < 500 and menders:
            observed += 4 * min(menders, MENDERS_MAX)
        potential = their_dps                      # turrets in sight whose line reaches us
        their_dps = max(their_dps, observed)
        threatened = their_dps > 0
        # A turret that covers the Core but has not fired in a while is sized at what lands,
        # not at what it could do: brokkr parked a silent Sentinel on icefloe and the Core
        # bought three menders against it at 60 Ti each while the miner starved.
        landing = their_dps if self.round - self.last_damage <= SILENT_TURRET_ROUNDS else observed
        if threatened:
            if self.round - self.last_hit > 5:
                self.threat_start = self.round
            self.last_hit = self.round
        siege_len = (self.round - self.threat_start) if (threatened and self.threat_start is not None) else 0
        quiet = self.round - self.last_hit > 12
        self.loiter = min(self.loiter + 1, 30) if loiterers else max(0, self.loiter - 1)

        # ---- the books
        ehp = self._read(ct, SLOT_EHP) or 500
        menders_seen = self._read(ct, SLOT_EHEAL)
        spent = max(0, self.prev_ammo + self.converted - ammo) if self.prev_ammo is not None else 0
        if self.prev_ehp is not None:
            self.heals.append(max(0.0, (ehp - self.prev_ehp) + 1.8 * spent))
            self.shots.append(spent)
            del self.heals[:-6]
            del self.shots[:-6]
        self.prev_ehp = ehp
        self.prev_ammo = ammo
        self.converted = 0
        eheal = 4 * menders_seen
        if sum(self.shots) >= 20 and len(self.heals) >= 3:
            realized = sum(self.heals) / len(self.heals)
            eheal = realized if menders_seen == 0 else min(eheal, realized)
            if ehp >= 500 and menders_seen:
                eheal = 4 * menders_seen           # a full Core shows no mending; trust the count
        our_dps = 9 * alive
        net_us = our_dps - eheal
        scout = _flags(self._read(ct, SLOT_BUILDER))
        self.eta = scout & 0xFF
        if scout & ATK_ECON or (scout >> ATK_BUILDERS_SHIFT) & 7 >= 3:
            self.scout_econ = True
        if scout & ATK_RUSH:
            self.scout_rush = True
        remaining = max(0, SENTINEL_TARGET - built)
        ring_reserve = self._ring_reserve(ct, remaining)
        if self.ring_hold or ring_paused:
            ring_reserve = 0

        # ---- the race, called once (hildr)
        our_eta = 99
        if built >= SENTINEL_TARGET:
            our_eta = 0
        elif self.eta:
            our_eta = (self.eta - 1) + remaining
        their_eta = None
        # Both rings are placed by the same kind of Builder, so our measured interval between
        # placements is the best prior for theirs: two samples of theirs said 4 rounds a turret
        # on auroraveil, ours said 1, and the truth was 1.7 for both -- 'race' on a side that
        # finishes three rounds behind.
        own_rate = 1.8
        if len(self.place_rounds) >= 2:
            own_rate = max(1.0, (self.place_rounds[-1] - self.place_rounds[0]) / (len(self.place_rounds) - 1))
        if their_dps > 0:
            placed = len(self.seen_turrets)
            rounds = sorted(self.seen_turrets.values())
            rate = own_rate
            if len(rounds) >= 3:
                rate = max(1.0, (rounds[-1] - rounds[0]) / (len(rounds) - 1))
            their_eta = max(0, SENTINEL_TARGET - placed) * rate
        elif their_near is not None:
            their_eta = max(0, their_near - 1) + SENTINEL_TARGET * own_rate
        if built < SENTINEL_TARGET and self.eta:
            our_eta = (self.eta - 1) + remaining * own_rate
        if self.plan is None and their_eta is not None:
            # Ring timing alone.  The HP projection saw their menders and called a race we won
            # by ten rounds unwinnable: a rusher that mends is a rusher that went broke.
            self.plan = 'race' if our_eta + RACE_MARGIN <= their_eta else 'mend'
            self.plan_round = self.round
        if self.plan == 'race' and self.round - self.plan_round > 8 and their_eta is not None:
            if our_eta > their_eta + 4 and hp < 400:
                self.plan = 'mend'
        # The mend plan holds the ring.  Their ring stands first, so the titanium the rest of
        # ours would cost is three menders instead -- 12 HP a round against a ring that has
        # 29 shots in it leaves us standing when it runs dry.  Released once home is quiet.
        if (self.plan == 'mend' and built < SENTINEL_TARGET and not self.ring_hold
                and self.sentinels_on_us >= 2):
            self.ring_hold = True                  # a ring; Gunners get barriers and diggers instead
        if self.ring_hold:
            # Released once their ring has shot itself dry: quiet for a while at 400+ HP, or
            # landing no more than the squad heals for a titanium a round.  Never before it
            # has fired at all -- "quiet since round -1000" released the hold the round it
            # was set, and skald-B was a four-round-late race instead of a held Core.
            fired = self.last_damage > 0
            trickle = fired and hp >= 400 and landing <= 4.5
            quiet_now = fired and self.round - self.last_damage > RING_RESUME_QUIET and hp >= 400
            no_show = (not fired and self.round - self.plan_round > 30 and their_near is None
                       and potential == 0)
            gunners_only = self.sentinels_on_us == 0 and fired
            released = quiet_now or trickle or no_show or gunners_only or built >= SENTINEL_TARGET
            if released:
                self.ring_hold = False
                self.plan = 'race' if built < SENTINEL_TARGET else self.plan
                self.plan_round = self.round
        full = 9 * max(SENTINEL_TARGET, alive)
        kill_ammo = (10.0 * ehp / 18.0) * (full / max(1, full - eheal)) if net_us > 0 or alive == 0 else 0
        # Finish a Core this low -- when the finish can be paid for, or ours is not the one
        # in danger.  On holmgang the Core waited thirty rounds on an unfunded finish, mending
        # nothing, while three Gunners took it from 353 to 24.
        finish_bank = ammo + max(0, ti - TIE_FLOOR)
        finishing = (ehp <= GO_LOW_HP and alive > 0 and net_us > 0
                     and (finish_bank >= kill_ammo or hp >= 250))
        # A lost Sentinel is not replaced while the kill is funded by what we hold: on
        # fimbulwinter the 66 Ti replacement was 6.6 shots and gefn's Core stood at 18 HP
        # when the ammunition ran out.  Two Sentinels out-damage any mending we can beat.
        standing = 9 * alive
        net_standing = standing - eheal
        kill_standing = (10.0 * ehp / 18.0) * (standing / net_standing) if net_standing > 0 else None
        target = SENTINEL_TARGET + self.ring_extra
        if alive >= target:
            self.ring_was_full = True
        self.hold_rebuild = (self.ring_was_full and 2 <= alive < target and kill_standing is not None
                             and ammo + max(0, ti - TIE_FLOOR) >= kill_standing)
        if self.hold_rebuild:
            remaining = 0
            ring_reserve = 0
        can_finish = alive > 0 and net_us > 0 and ammo + max(0, ti - ring_reserve) >= BURST_SLACK * kill_ammo
        # hildr's stall needed a complete ring; with ours dug to three, the Core neither
        # raced nor mended and two Gunners took it from 500 to 24 while it held 50 Ti.
        stalled = (self.plan == 'race'
                   and self.round - self.plan_round > 10
                   and (eheal > 0 or (hp < 300 and ehp >= 250) or built < SENTINEL_TARGET)
                   and not can_finish)
        mend_first = threatened and not finishing and (self.plan == 'mend' or stalled)
        mend_reserve = min(MEND_RESERVE, 3 * menders) if (threatened and menders and not finishing) else 0
        bank = ammo + max(0, ti - ring_reserve - mend_reserve)

        # ---- menders (hildr)
        sentinel_cost = self._sentinel_cost(ct)
        want_menders = 0
        # A funded kill outranks a mend squad: on fimbulwinter the squad bought against a ring
        # that was LOSING the race left four Sentinels with no ammunition in front of a
        # 176 HP Core.  When the kill is funded only the finish-line rule below adds a mender.
        near_kill = (alive >= 3 and net_us > 0 and bank >= 0.6 * kill_ammo and hp >= 250)
        if (mend_first or (self.plan is None and threatened)) and not can_finish and not near_kill:
            # Sized to what a barrier cannot stop: a Gunner with a lane gets a 3 Ti barrier and
            # a Builder beside it (steward's Gunners hold fire on a tended barrier), a Gunner
            # touching the footprint gets dug out.  Menders are for Sentinels.
            unblockable = 9 * self.sentinels_on_us + 7 * self.gunners_close
            if self.round - self.last_damage > SILENT_TURRET_ROUNDS:
                unblockable = 0
            if unblockable == 0 and landing > 0:
                unblockable = min(landing, 7)
            want_menders = (int(unblockable) + 3) // 4    # 4 HP a round each: out-heal it
            if self.ring_hold:
                want_menders = min(MEND_SQUAD_MAX, max(want_menders, (9 * self.sentinels_on_us + 3) // 4))
            want_menders = max(1, want_menders)
            if self.sentinels_on_us == 0 and self.hold_total <= STALL_ROUNDS:
                # Gunners: one mender and the barriers.  Two bought at the first Gunner on
                # helheim, before the race was even called, were the ring's ammunition.
                want_menders = 1
            if hp < 300 and landing >= 18:
                want_menders += 1
            want_menders = min(MENDERS_MAX, max(1, want_menders))
            # One counter-turret outranks the second mender: it ends a Sentinel for good, and
            # at the cost scale a rush leaves, a mender is 60 Ti plus 1 Ti a round forever.
            if (COUNTER_TURRETS and self.sentinels_on_us > 0 and self.home_turrets == 0
                    and len(self.turret_ids) < HOME_TURRET_LIFETIME
                    and ti + 10 >= sentinel_cost + self._builder_cost(ct)
                    and not self.ring_hold):
                want_menders = min(want_menders, 1 if hp >= 300 else 2)
        if HOME_BUILDER_AT_START:
            want_menders = max(want_menders, 1)
        # The finish line.  Two rushes meeting is a sum: when their ring will kill us no later
        # than ours kills them, one mender (4 HP a round for 1 Ti) moves our death back
        # further than its price moves theirs -- provided the kill is still funded after it.
        # A mirror of hildr was a coin flip: both Cores dead in the same round, 42 of 42 times.
        if (alive and threatened and their_dps > 0 and net_us > 0 and not finishing
                and menders < MENDERS_MAX):
            t_us = ehp / net_us
            heal_now = 4 * menders
            if their_dps > heal_now:
                t_them = hp / (their_dps - heal_now)
                cost = self._builder_cost(ct)
                funded = ammo + max(0, ti - cost - ring_reserve) >= BURST_SLACK * kill_ammo
                if t_them <= t_us + 2 and funded:
                    want_menders = max(want_menders, menders + 1)
        miners_now = sum(1 for _slot, flags in homes if flags & 1)
        harvesters = sum((flags >> 1) & 7 for _slot, flags in homes)
        home_builders = max(menders, len(homes))
        need_menders = max(0, want_menders - home_builders)

        if menders < self.prev_menders and threatened:
            self.home_deaths += self.prev_menders - menders
        self.prev_menders = menders
        if not threatened:
            if self.round - self.last_hit > 25:
                self.home_deaths = 0
        if self.home_deaths >= 2 and threatened:
            need_menders = 0

        # ---- the stall (hildr): the rush is banked behind their menders -- an income race
        stuck = ((built >= SENTINEL_TARGET and self.hold_total > STALL_ROUNDS
                  and self.round - self.last_hit > 12)
                 or (ring_paused and self.round - self.last_hit > 12))
        if (stuck and self.ring_extra < RING_EXTRA_MAX
                and (bank > kill_ammo + self._sentinel_cost(ct) + 120
                     or (net_us <= 12 and bank > 250 + self._sentinel_cost(ct)))):
            self.ring_extra += 1

        # ---- GO / HOLD for the ring (hildr)
        go = 1
        if alive and eheal > 0:
            if net_us <= 0:
                go = 0
            else:
                slack = BURST_SLACK * (0.6 if (self.go and self.go_held) else 1.0)
                go = 1 if bank >= slack * kill_ammo else 0
            self.go_held = True
            if go == 0 and ammo >= SNIPE_BANK:
                go = 2                             # a volley at a mender, then bank again
            if go != 1:
                self.hold_total += 1
        else:
            self.go_held = False
        self.go = go
        self._write(ct, SLOT_GO, go)

        # ---- the economy (steward): a first-class purchase, not a stall reflex
        # The round-1000 tiebreak is titanium collected, and only Harvesters collect.  Every
        # timeout hildr lost was lost here.  Once the ring is up the first miner is bought
        # unless the kill is funded from the bank right now; the second comes when the game
        # has clearly gone long or the rush has stalled; the third when the stall is an
        # income race with belts already down.
        ring_up = built >= SENTINEL_TARGET
        want_miners = 0
        # The opening miner, on evidence.  Bought behind the attacker it costs 1.2x instead of
        # the 2.2x the ring leaves -- and it costs the race against a rusher by exactly its
        # price (v70's Core at 14 HP).  So it is bought when the attacker has seen their
        # Harvesters or belts and nobody has seen their attacker.
        if their_near is not None or potential > 0 or self.seen_turrets:
            self.scout_rush = True
        if (ECON_OPENING and self.spawned and not ring_up and not threatened
                and self.scout_econ and not self.scout_rush):
            want_miners = 1
        if ECON_AFTER_RING and (ring_up or self.round >= ECON_ROUND):
            want_miners = 1
            # The second miner follows the first Harvester, the third the third: on paths the
            # second Builder was bought at round 92 with the first miner still saving for its
            # Harvester, and the game ended with two Builders and no Harvester at all.
            if harvesters >= 1 and (stuck or self.round >= LONG_GAME_ROUND):
                want_miners = 2
            if stuck and harvesters >= 3:
                want_miners = MINERS_MAX
        elif not ECON_AFTER_RING and stuck:
            want_miners = MINERS_MAX
        if harvesters >= HARVESTERS_MAX:
            want_miners = min(want_miners, 1)   # one body keeps the belts mended
        # A miner is a HOLD purchase.  While the ring is shooting (GO) every point of titanium
        # is a shot: 36 Ti held back for a miner on holmgang was the four shots that left
        # steward's Core at 4 HP, and their menders took it back from there.  The kill that
        # cannot be funded now is what the miner's income pays for -- once the Core has said
        # so by holding.
        all_in = (go == 1 and alive > 0) or finishing
        if all_in:
            want_miners = 0
        self.miners_hwm = max(self.miners_hwm, want_miners)
        safe = (not threatened) or (hp >= 400 and menders >= 2)
        want_home = want_menders + (want_miners if safe else 0)
        need_home = max(0, want_home - home_builders)
        if self.home_deaths >= 2 and threatened:
            need_home = need_menders
        need_miner = need_home > need_menders

        # ---- the guard (steward): what the home squad may buy this round
        gunner_cost = self._gunner_cost(ct)
        turret_budget = (self.home_turrets < HOME_TURRET_MAX
                         and len(self.turret_ids) < HOME_TURRET_LIFETIME
                         and self.round - self.turret_lost > HOME_TURRET_COOLDOWN)
        # A counter-turret answers a Sentinel, which cannot re-aim.  Against Gunners it is a
        # money pit: steward re-seated a Gunner seven times off our turret's ray on helheim and
        # killed six 70 Ti Sentinels with 30 Ti Gunners.  Gunners get barriers and diggers.
        turret_ok = (COUNTER_TURRETS and threatened and self.sentinels_on_us > 0
                     and turret_budget
                     and need_menders == 0
                     and (siege_len >= DEFEND_AFTER_ROUNDS or hp < 300 or self.plan == 'mend')
                     and self.round - self.last_damage <= SILENT_TURRET_ROUNDS
                     and ti >= sentinel_cost + mend_reserve + 10)
        gunner_ok = (ANTI_BUILDER_GUNNER and self.loiter >= LOITER_ROUNDS
                     and turret_budget
                     and need_menders == 0
                     and ti >= gunner_cost + mend_reserve + 10)
        # Saving for a counter-turret is a HOLD purchase, like the miner: while the kill is
        # funded and the ring is shooting, every point is a shot (reserving 66 Ti here during
        # the race lost 24 of 30 mirrors).
        # ...and a kill that is nearly funded counts as racing: on longhouse the burst was
        # 8 Ti short of the threshold, the Core bought a 78 Ti turret instead, and steward's
        # Core went from 260 back to 416 while ours bled out.  Only real danger overrides.
        racing = (go == 1 and alive > 0 and can_finish) or near_kill
        turret_wanted = (COUNTER_TURRETS and threatened and self.sentinels_on_us > 0 and turret_budget
                         and landing > 0 and need_menders == 0 and not racing)
        turret_ok = turret_ok and not racing
        defence_reserve = sentinel_cost if (turret_ok or turret_wanted) else (gunner_cost if gunner_ok else 0)

        # ---- the attack Builder, then menders, then the miner, then ammunition
        spawned_now = self._keep_attacker(ct, built)
        if not spawned_now and need_home:
            cost = self._builder_cost(ct)
            if need_menders:
                if (self.plan == 'mend' or mend_first) and not racing:
                    spare = ti - (ring_reserve if alive == 0 and built == 0 else 0)
                elif stuck:
                    spare = ti - SNIPE_BANK
                else:
                    spare = ti - ring_reserve - mend_reserve - max(0, kill_ammo - ammo)
            else:
                # The miner.  The ring and the mend float come first; the kill does not --
                # a kill that is not affordable now is what the miner's income pays for.
                spare = ti - ring_reserve - mend_reserve - defence_reserve - ECON_MARGIN
            if self.spawn_total >= REPLACEMENT_DAMP_AFTER:
                spare -= 150
            if ti >= cost and spare >= cost:
                spawned_now = self._spawn_home(ct)
                if spawned_now:
                    self.spawn_total += 1

        # ---- orders to the home squad
        econ_ok = (safe and need_menders == 0 and self.miners_hwm > 0
                   and (harvesters < HARVESTERS_MAX or REPAIR_BELTS))
        flags = 0
        if threatened:
            flags |= ORD_THREAT
        if econ_ok:
            flags |= ORD_ECON
        if turret_ok:
            flags |= ORD_TURRET
        if gunner_ok:
            flags |= ORD_GUNNER
        if quiet:
            flags |= ORD_QUIET
        if turret_wanted and not turret_ok and hp >= 250 and self.sentinels_on_us > 0:
            flags |= ORD_SAVE                      # Big O's one Sentinel cost 500 rounds of heals
        if racing:
            flags |= ORD_RACE
        flags |= min(3, self.miners_hwm if econ_ok else 0) << ORD_MINERS_SHIFT
        flags |= min(7, harvesters) << ORD_HARVEST_SHIFT
        self._write(ct, SLOT_ORDERS, (self.round + 1) + 65536 * flags)
        self._publish_shooter(ct)
        econ_first = econ_ok and harvesters == 0 and home_builders > 0 and (go != 1 or (kill_ammo - bank) > 100)

        # ---- ammunition, lazily
        reserve_extra = mend_reserve + defence_reserve + (ECON_RESERVE if econ_first else 0)
        hold_for_builders = need_home if not (go == 1 and alive > 0 and can_finish) else 0
        self._feed_ammo(ct, alive, go, 0 if finishing else ring_reserve, hold_for_builders,
                        threatened, mend_first, reserve_extra, finishing, stuck, their_dps)

    def _publish_shooter(self, ct):
        """Name one turret for the home squad: a Sentinel if any reaches us (the counter-turret's
        target), else the nearest Gunner whose lane onto the Core has nothing soaking it yet --
        the squad sees r^2 20 and the Gunners shooting the Core sit at r^2 13 from the far
        footprint tile, routinely out of their sight."""
        try:
            mine = ct.get_team()
            own = set(self.own_tiles)
            best = None
            for uid, known in self.cover.items():
                if not known[2]:
                    continue
                try:
                    kind = ct.get_entity_type(uid)
                    p = ct.get_position(uid)
                except Exception:
                    continue                       # gone, or out of sight this round
                if (p.x, p.y) != known[0]:
                    continue
                if kind == EntityType.SENTINEL:
                    rank = (0, 0)
                    word = 1
                elif kind == EntityType.GUNNER:
                    dx, dy = known[1].delta()
                    tile = (p.x + dx, p.y + dy)
                    soaked = False
                    lane_free = 0
                    while (tile not in own and (tile[0] - p.x) ** 2 + (tile[1] - p.y) ** 2 <= GUNNER_RANGE_SQ):
                        try:
                            if ct.is_in_vision(Position(tile[0], tile[1])) and ct.get_tile_building_id(Position(tile[0], tile[1])) is not None:
                                soaked = True
                                break
                        except Exception:
                            break
                        lane_free += 1
                        tile = (tile[0] + dx, tile[1] + dy)
                    if soaked or lane_free == 0:
                        continue                   # already blocked, or touching the footprint: dig it
                    gap = min(_cheb((p.x, p.y), t) for t in own)
                    rank = (1, gap)
                    word = 2 + 4 * RAYS.index(next(r for r in RAYS if r[0] == known[1]))
                else:
                    continue
                if best is None or rank < best[0]:
                    best = (rank, p, word)
            if best is None:
                self._write(ct, SLOT_SHOOTER, 0)
            else:
                self._write(ct, SLOT_SHOOTER, _pack(best[1], best[2]))
        except Exception:
            self._write(ct, SLOT_SHOOTER, 0)

    def _builder_cost(self, ct):
        try:
            return ct.get_builder_bot_cost()
        except Exception:
            return 60

    def _sentinel_cost(self, ct):
        try:
            return ct.get_sentinel_cost()
        except Exception:
            return 70

    def _gunner_cost(self, ct):
        try:
            return ct.get_gunner_cost()
        except Exception:
            return 50

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

    def _home_reports(self, ct):
        out = []
        for i in range(SLOT_HOMES):
            word = self._read(ct, SLOT_HOME0 + i)
            if _fresh(_beat(word), self.round, 2):
                out.append((i, _flags(word)))
        return out

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

    def _own_turrets_home(self, ct):
        """Turrets of ours in Core vision that are guards -- a ring Sentinel on a small map
        is within sight of our own Core too, and it is not a guard."""
        n = 0
        seen = set()
        try:
            mine = ct.get_team()
            enemy_tiles = _footprint(self.enemy) if self.enemy is not None else ()
            for uid in ct.get_nearby_buildings():
                if ct.get_team(uid) != mine:
                    continue
                kind = ct.get_entity_type(uid)
                if kind == EntityType.GUNNER:
                    n += 1
                    seen.add(uid)
                elif kind == EntityType.SENTINEL:
                    p = ct.get_position(uid)
                    dx, dy = ct.get_direction(uid).delta()
                    if not _on_ray((p.x, p.y), (dx, dy), enemy_tiles, MAX_RANGE_SQ):
                        n += 1
                        seen.add(uid)
        except Exception:
            pass
        if self.turret_ids - seen:
            self.turret_lost = self.round          # one we knew is gone
        self.turret_ids |= seen
        return n

    def _scan_home(self, ct):
        """Enemy damage per round that can reach our Core, the nearest enemy Builder's distance
        (Chebyshev, to the footprint) or None, the enemy Builders loitering at the footprint,
        and the enemy turrets whose line reaches the Core."""
        dps = 0
        near = None
        loiterers = 0
        shooters = 0
        self.shooter = None
        self.gunners_close = 0      # Gunners touching the footprint: no lane tile, dig them
        self.gunners_far = 0        # Gunners with a lane: a barrier and a Builder beside it
        self.sentinels_on_us = 0
        try:
            mine = ct.get_team()
            own = set(self.own_tiles)
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) == mine:
                    continue
                kind = ct.get_entity_type(uid)
                if kind == EntityType.BUILDER_BOT:
                    p = ct.get_position(uid)
                    d = min(_cheb((p.x, p.y), t) for t in own)
                    if near is None or d < near:
                        near = d
                    if d <= LOITER_REACH:
                        loiterers += 1
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
                    shooters += 1
                    gap = min(_cheb((p.x, p.y), t) for t in own)
                    if kind == EntityType.SENTINEL:
                        self.sentinels_on_us += 1
                    elif gap <= 1:
                        self.gunners_close += 1
                    else:
                        self.gunners_far += 1
                    rank = (0 if kind == EntityType.SENTINEL else 1, gap)
                    if self.shooter is None or rank < self.shooter[0]:
                        self.shooter = (rank, (p.x, p.y), kind == EntityType.SENTINEL)
                    if uid not in self.seen_turrets:
                        self.seen_turrets[uid] = self.round
        except Exception:
            pass
        return dps, near, loiterers, shooters

    def _keep_attacker(self, ct, built):
        if built >= SENTINEL_TARGET + self.ring_extra:
            # The ring is up -- or was.  No heartbeat from any Sentinel for a while means the
            # ring is gone: start over, whether or not the attacker survived it.  hildr only
            # restarted when the attacker was dead, and a live attacker tended nothing for
            # 700 rounds on holmgang with 1,845 Ti in the bank.
            alive = self._sentinels_alive(ct)
            if alive:
                self.ring_seen = self.round
            if self.round - self.ring_seen < RING_LOST_ROUNDS or self.round - self.plan_round < 30:
                return False
            self._write(ct, SLOT_BUILT, 0)
            self.ring_seen = self.round
            if _fresh(_beat(self._read(ct, SLOT_BUILDER)), self.round, 2):
                return False                       # the live attacker rebuilds
            self.spawned = 0
            return False
        if self.spawned and not REPLACE_BUILDER:
            return False
        if self.spawned:
            beat = _beat(self._read(ct, SLOT_BUILDER))
            if _fresh(beat, self.round, 2):
                return False
            if self.round < 4:
                return False
        self.spawn_role = 0
        return self._spawn_one(ct, toward_enemy=True)

    def _spawn_home(self, ct):
        self.spawn_role = 1
        return self._spawn_one(ct, toward_enemy=False)

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

    def _feed_ammo(self, ct, alive, go, ring_reserve, need_home, threatened, mend_first,
                   mend_reserve, finishing, stuck=False, threatened_dps=0):
        """Keep two shots per living Sentinel banked, and nothing more: titanium is flexible,
        ammunition is not.  The burst is paid for the round the Core says GO, and a Core within
        reach of the finish gets every point we have.  A Builder the Core wants -- mender or
        miner -- is paid for before the float is refilled: the float re-fired every round on
        paths and the miner was never affordable."""
        try:
            ammo = ct.get_global_ammo()
            ti = ct.get_global_resources()
            reserve = ring_reserve + mend_reserve
            if need_home and not finishing:
                reserve += self._builder_cost(ct)
            if alive == 0:
                want = 20 if ammo < 20 else 0
            elif finishing:
                # Only what the finish needs, plus two spare shots: everything else stays
                # titanium, because both Cores dying in one round is settled on titanium
                # stored, and hildr78 held 12 to our 8 on jotunheim by converting in tens.
                ehp = self._read(ct, SLOT_EHP) or 500
                want = 10 * (ehp // 18 + 1) - ammo
            elif stuck and go != 1:
                want = SNIPE_BANK - ammo
                if (threatened and ti < reserve + 60) or (need_home and ti < reserve + 20):
                    want = 0                       # the float burned the titanium the guard needed
            elif go == 1:
                # Two shots a Sentinel, but never more than the kill still needs plus two
                # spare: on jotunheim the float left 20 ammunition unfired and the dead heat
                # went to the side holding 12 Ti against our 8.
                ehp = self._read(ct, SLOT_EHP) or 500
                want = min(AMMO_PER_SENTINEL * alive, 10 * (ehp // 18 + 1)) - ammo
            elif go == 2:
                want = 0
            else:
                want = SNIPE_BANK - ammo           # bank a volley, then let it go
                if (threatened and ti < reserve + 60) or (need_home and ti < reserve + 20):
                    want = 0
            if want <= 0:
                return
            floor = TIE_FLOOR
            if finishing and alive > 0:
                # The floor settles a round in which both Cores die.  If ours will outlive
                # theirs by the one shot the floor is holding, the floor is the shot: gefn's
                # Core stood at 16 HP on holmgang with 8 Ti unconverted.
                try:
                    own_hp = ct.get_hp()
                except Exception:
                    own_hp = 500
                if own_hp > 2 * max(threatened_dps, 1) * 2:
                    floor = 0
            spare = ti - reserve - floor
            amount = min(max(want, 10), spare)
            if amount >= 10 and ct.can_convert_ammo(amount):
                ct.convert_ammo(amount)
                self.converted = amount
        except Exception:
            return

    # ---------------------------------------------------------------- builder
    def _builder(self, ct):
        here = ct.get_position()
        if self.home is None:
            self._orient(ct, here)
        if self.role is None:
            ring_done = (self._read(ct, SLOT_BUILT) & 0xFF) >= SENTINEL_TARGET + (_extra(self._read(ct, SLOT_ENEMY)) & 3)
            attacker_alive = _fresh(_beat(self._read(ct, SLOT_BUILDER)), self.round, 2)
            self.role = 'home' if (ring_done or attacker_alive) else 'attack'

        if self.role == 'home':
            self._home(ct, here)
            return

        self._write(ct, SLOT_BUILDER, (self.round + 1) + 65536 * (self.last_eta | self._scout_word()))
        self._observe(ct, here)
        self.covered = self._threats(ct)
        self._dist, self._came = self._flood(here, self.covered)
        extra = _extra(self._read(ct, SLOT_ENEMY))
        self.ring_target = SENTINEL_TARGET + (extra & 3)
        hold_rebuild = bool(extra & HOLD_REBUILD)
        ring_hold = bool(extra & RING_HOLD)

        # The Core restarts the ring when every heartbeat is gone; the attacker notices any
        # single Sentinel it can see destroyed.  Either way the count drops and the walk resumes.
        if REBUILD_RING:
            if ((self._read(ct, SLOT_BUILT) & 0xFF) == 0 and self.built > 0
                    and self.round > self.last_place + 1):
                self.built = 0
                self.placed = []
                self.goal = None
                self.path = []
            else:
                self._recount_ring(ct)

        if self.built >= self.ring_target:
            self.ring_done_once = True
        paused = self.round < self.pause_until and self.ring_done_once
        if paused and self.round % 10 == 0:
            self._write(ct, SLOT_BUILT, self.built | SLOT_BUILT_PAUSED)
        if self.built < self.ring_target and not (hold_rebuild and self.ring_done_once) and not ring_hold and not paused:
            self.goal = self._next_stand(here)
            walk = self._dist.get(self.goal, 99) if self.goal is not None else 99
            if self._anchor_value((here.x, here.y)):
                walk = 0                           # a spot beside us: we build this round
            self.last_eta = min(98, walk) + 1
            self._write(ct, SLOT_BUILDER, (self.round + 1) + 65536 * (self.last_eta | self._scout_word()))
            if self._place(ct, here):
                return
            if self._advance(ct, here):
                return
            self._break_through(ct, here)
            return
        self.last_eta = 1
        self._write(ct, SLOT_BUILDER, (self.round + 1) + 65536 * (1 | self._scout_word()))
        self._report_enemy(ct)
        if ATTACKER_DIG_REACH and self._dig(ct, here, ATTACKER_DIG_REACH):
            return
        if SHIELD_RING and self._shield_ring(ct, here):
            return
        if self._tend(ct, here):
            return
        quiet_home = bool(_flags(self._read(ct, SLOT_ORDERS)) & ORD_QUIET)
        if DENY_ORE and (quiet_home or ring_hold) and self._deny_ore(ct, here):
            return
        self._return_to_ring(ct, here)

    def _shield_ring(self, ct, here):
        """A barrier in a Gunner's lane onto one of our Sentinels.  steward's guard seats a
        Gunner on a ray to each Sentinel of the ring and digs it out in six shots; we rebuilt
        into the same lane 26 times on paths.  A Gunner's ray stops at the first building, our
        Sentinel's does not, and a steward Gunner holds its fire on a barrier with a Builder
        beside it -- so the 7 Ti barrier, tended from the anchor, ends the exchange."""
        if not self.placed:
            return False
        try:
            if ct.get_global_resources() < ct.get_barrier_cost() + 12:
                return False
        except Exception:
            return False
        mine_sent = set(self.placed)
        best = None
        for uid, known in self.turrets.items():
            if known[3] != EntityType.GUNNER or not (known[2] & mine_sent):
                continue
            origin = known[0]
            dx, dy = known[1].delta()
            if dx == 0 and dy == 0:
                continue
            tile = (origin[0] + dx, origin[1] + dy)
            lane = []
            while (0 <= tile[0] < self.width and 0 <= tile[1] < self.height
                   and tile not in self.walls
                   and (tile[0] - origin[0]) ** 2 + (tile[1] - origin[1]) ** 2 <= GUNNER_RANGE_SQ):
                if tile in mine_sent:
                    for spot in lane:
                        cost = self._dist.get(spot)
                        if cost is None:
                            cost = min((self._dist.get((spot[0] + ax, spot[1] + ay), 99)
                                        for _d, ax, ay in CARDINALS), default=99) + 1
                        rank = (cost, -abs(spot[0] - tile[0]) - abs(spot[1] - tile[1]), spot)
                        if best is None or rank < best:
                            best = rank
                    break
                if tile in self.occupied:
                    break                          # something already soaks this lane
                if not self._tile_has_builder(ct, tile):
                    lane.append(tile)
                tile = (tile[0] + dx, tile[1] + dy)
        if best is None or best[0] > 6:
            return False
        spot = best[2]
        if abs(spot[0] - here.x) + abs(spot[1] - here.y) == 1:
            pos = Position(spot[0], spot[1])
            try:
                if ct.can_build_barrier(pos):
                    ct.build_barrier(pos)
                    self.occupied.add(spot)
                    self.blocked.add(spot)
                    return True
            except Exception:
                pass
            return False
        if (here.x, here.y) == spot:
            return self._step_any(ct, here)
        self._walk_beside(ct, here, spot)
        return True

    def _return_to_ring(self, ct, here):
        """Idle: stand beside the ring, out of every known lane, so a hurt Sentinel is in
        sight and a dug-out one is seen gone."""
        if not self.placed:
            return
        anchor = self.placed[0]
        if _cheb((here.x, here.y), anchor) <= 2 and (here.x, here.y) not in self.covered:
            return
        best = None
        chosen = None
        for key in self.placed:
            for _d, dx, dy in CARDINALS:
                step = (key[0] + dx, key[1] + dy)
                cost = self._dist.get(step)
                if cost is None or step in self.covered:
                    continue
                if best is None or cost < best:
                    best, chosen = cost, step
        if chosen is None or chosen == (here.x, here.y):
            return
        path = self._trace(self._came, here, chosen)
        if path:
            self._step_to(ct, here, path[0])

    def _scout_word(self):
        word = (ATK_ECON if self.econ_seen else 0) | (ATK_RUSH if self.rush_seen else 0)
        return word | (min(7, len(self.enemy_ids)) << ATK_BUILDERS_SHIFT)

    def _recount_ring(self, ct):
        """A planted Sentinel seen gone comes off the count, so the walk plants another."""
        gone = []
        for key in self.placed:
            try:
                spot = Position(key[0], key[1])
                if ct.is_in_vision(spot) and ct.get_tile_building_id(spot) is None:
                    gone.append(key)
            except Exception:
                continue
        if not gone:
            return
        for key in gone:
            self.placed.remove(key)
            self.blocked.discard(key)
            self.occupied.discard(key)
            if self.round - self.placed_round.get(key, -1000) <= QUICK_LOSS_ROUNDS:
                self.poisoned.add(key)
                self.quick_losses += 1
        if self.quick_losses >= RING_PAUSE_LOSSES:
            # Torsko's guard dug 22 rebuilt Sentinels out of the same two spots: 880 Ti,
            # every point of income for 300 rounds.  Hold, and let the Core spend instead.
            self.pause_until = self.round + RING_PAUSE_ROUNDS
            self.quick_losses = 0
        self.built = max(0, self.built - len(gone))
        self._write(ct, SLOT_BUILT, self.built | (SLOT_BUILT_PAUSED if self.round < self.pause_until else 0))
        self.goal = None
        self.path = []

    def _dig(self, ct, here, reach):
        """Dig out the nearest enemy turret: 2 Ti a hit, thirteen hits for a Gunner that would
        otherwise take 40-60 Ti of Sentinel with it. Stand beside it on a tile no turret covers."""
        try:
            mine = ct.get_team()
            target = None
            best = None
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) == mine:
                    continue
                if ct.get_entity_type(uid) not in (EntityType.GUNNER, EntityType.SENTINEL):
                    continue
                p = ct.get_position(uid)
                d = abs(p.x - here.x) + abs(p.y - here.y)
                if best is None or d < best:
                    best, target = d, p
            if target is None:
                self.digging = False
                return False
            if best == 1:
                if ct.can_fire(target):
                    ct.fire(target)
                    return True
                return False
            if not self.digging and best > reach:
                return False
            covered = self.covered
            goal = None
            gbest = None
            for _d, dx, dy in CARDINALS:
                step = (target.x + dx, target.y + dy)
                cost = self._dist.get(step)
                if cost is None or step in covered:
                    continue
                if gbest is None or cost < gbest:
                    gbest, goal = cost, step
            if goal is None:
                return False
            self.digging = True
            path = self._trace(self._came, here, goal)
            if path:
                self._step_to(ct, here, path[0])
                return True
        except Exception:
            pass
        return False

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
            if n > 0 or all(ct.is_in_vision(Position(k[0], k[1])) for k in ring):
                self._write(ct, SLOT_EHEAL, n)
            bid = ct.get_tile_building_id(Position(self.enemy.x, self.enemy.y))
            if bid is not None:
                self._write(ct, SLOT_EHP, ct.get_hp(bid))
        except Exception:
            pass

    # -- home: mend, guard, and mine -------------------------------------------
    def _home(self, ct, here):
        self._observe(ct, here)
        orders = self._read(ct, SLOT_ORDERS)
        if not _fresh(_beat(orders), self.round, 1):
            orders = 0
        flags = _flags(orders)
        threatened = bool(flags & ORD_THREAT)
        self._home_heartbeat(ct)
        miners_allowed = (flags >> ORD_MINERS_SHIFT) & 3
        self.team_harvesters = (flags >> ORD_HARVEST_SHIFT) & 7
        core_tiles = self.mine_tiles
        self.mining_now = False
        self.covered = self._threats(ct)
        # Threat-aware routing, like the attacker's: a mender walked its belt route straight
        # down a Gunner's lane on auroraveil and stood beside the Gunner, on its ray, to die.
        # Only lanes that shoot Builders count -- a ring Sentinel's ray through our Core is
        # where the menders have to stand.
        self._dist, self._came = self._flood(here, self.home_danger)
        # 0. a 3 Ti barrier in a live Gunner lane, when it is a step away: it absorbs that
        #    Gunner's whole output for less than a round of mending costs (steward: "the 3 Ti
        #    answer before the 30 Ti one").  Four Gunners on fimbulwinter got four barriers
        #    on round 64, after the Core had spent forty rounds being healed against them.
        if threatened and LANE_BARRIERS and self._lane_barrier(ct, here, max_walk=3):
            return
        # 0a. ...and if a lane barrier is wanted but not yet affordable, save for it instead of
        #     healing: four Gunners at 28 HP a round ate the whole income in 1 Ti heals on
        #     longhouse and the 8 Ti barrier that ends a lane for good was never bought.
        saving = bool(flags & ORD_SAVE) and self._core_hp(ct) >= 250
        if threatened and LANE_BARRIERS and self._core_hp(ct) > 120:
            spot = self._lane_barrier(ct, here, max_walk=3, dry=True)
            if spot is not None:
                saving = True
                if abs(spot[0] - here.x) + abs(spot[1] - here.y) != 1 and (here.x, here.y) != spot:
                    self._walk_beside(ct, here, spot)
                    return
        # 0b. the counter-turret before a heal while the Core can spare the round: the
        #     Builder that healed 4 HP a round against 36 seated its turret on round 25.
        if flags & ORD_TURRET and self._core_hp(ct) >= 200 and self._counter_turret(ct, here):
            return
        # 1. heal the Core if it is hurt and we are beside it -- unless an enemy turret is
        #    beside us too and the Core can spare the round: 2 Ti a hit digs a 25 HP Gunner out
        #    in thirteen hits, for good, while mending its 7 a round costs 1.75 Ti a round for
        #    ever.  gefn parked a Gunner diagonal to our Core on skald, where no barrier fits,
        #    and two menders stood next to it for sixty rounds healing what it did.
        #    And never with the last titanium while their Core is in its final 120 HP: both
        #    Cores dying in one round is settled on titanium stored, a heal is 1 Ti for 4 HP
        #    that cannot matter then, and the mirror on icefloe was lost 2 Ti to 2 on a coin.
        try:
            ehp = self._read(ct, SLOT_EHP) or 500
            if ct.get_global_resources() <= TIE_FLOOR and ehp <= GO_LOW_HP:
                raise ValueError
            if saving:
                raise ValueError                   # the barrier first
            core_hp = None
            for _d, dx, dy in CARDINALS:
                key = (here.x + dx, here.y + dy)
                if key not in core_tiles:
                    continue
                bid = ct.get_tile_building_id(Position(key[0], key[1]))
                if bid is not None:
                    core_hp = ct.get_hp(bid)
                    break
            dig = self._adjacent_enemy_turret(ct, here)
            if dig is not None and (core_hp is None or core_hp >= 100) and ct.can_fire(dig):
                ct.fire(dig)
                return
            if (dig is None and threatened and (core_hp is None or core_hp >= 150)
                    and not (flags & ORD_RACE) and self._dig_near_core(ct, here)):
                return
            for _d, dx, dy in CARDINALS:
                key = (here.x + dx, here.y + dy)
                if key not in core_tiles:
                    continue
                bid = ct.get_tile_building_id(Position(key[0], key[1]))
                if bid is not None and ct.get_hp(bid) < ct.get_max_hp(bid) and ct.can_heal(Position(key[0], key[1])):
                    ct.heal(Position(key[0], key[1]))
                    return
            if dig is not None and ct.can_fire(dig):
                ct.fire(dig)
                return
        except Exception:
            pass
        # 2. the guard: a barrier in a Gunner lane, a turret on the shooter, a Gunner on the
        #    loiterer -- each only when the Core says the bank allows it
        if threatened and LANE_BARRIERS and self._lane_barrier(ct, here):
            return
        if flags & ORD_TURRET and self._counter_turret(ct, here):
            return
        if flags & ORD_GUNNER and self._anti_builder_gunner(ct, here):
            return
        # 3. mining, if the Core is paying and this Builder is one of the miners it pays for
        if flags & ORD_ECON and self.home_slot is not None and self.home_slot < miners_allowed:
            if REPAIR_BELTS and self._repair_belt(ct, here):
                self.mining_now = True
                return
            if self._mine(ct, here):
                self.mining_now = True
                return
            if REPAIR_BELTS and self._patrol_belt(ct, here):
                self.mining_now = True
                return
        # 4. mend anything of ours beside us
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
        # 5. stand on the ring -- shooting our way there if they have walled it
        self._to_post(ct, here)

    def _core_hp(self, ct):
        try:
            bid = ct.get_tile_building_id(Position(self.mine_tiles[0][0], self.mine_tiles[0][1]))
            return ct.get_hp(bid) if bid is not None else 500
        except Exception:
            return 500

    def _dig_near_core(self, ct, here):
        """Walk to an enemy turret touching our Core and stand beside it, out of every lane."""
        try:
            mine = ct.get_team()
            target = None
            tbest = None
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) == mine or ct.get_entity_type(uid) not in (EntityType.GUNNER, EntityType.SENTINEL):
                    continue
                p = ct.get_position(uid)
                gap = min(_cheb((p.x, p.y), t) for t in self.mine_tiles)
                if ct.get_entity_type(uid) == EntityType.SENTINEL:
                    # 20 hits, 40 Ti, off a ray it cannot turn: cheaper than the 2.25 Ti a
                    # round its 9 HP cost in heals for 500 rounds on stavkirke
                    if gap > 5 or self._core_hp(ct) < 150 or self._tended(ct, p, mine):
                        continue
                elif gap > 3:
                    continue                       # Gunner reach is r^2 13: 3.6 tiles
                for _d, dx, dy in CARDINALS:
                    step = (p.x + dx, p.y + dy)
                    if not self._passable(step) or step in self.lanes:
                        continue
                    cost = self._dist.get(step)
                    if cost is None or cost > 4:
                        continue
                    if tbest is None or cost < tbest:
                        tbest, target = cost, step
            if target is None or target == (here.x, here.y):
                return False
            path = self._trace(self._came, here, target)
            if path:
                return self._step_to(ct, here, path[0])
        except Exception:
            pass
        return False

    def _adjacent_enemy_turret(self, ct, here):
        """An enemy Gunner or Sentinel on a tile orthogonally beside us, weakest first."""
        try:
            mine = ct.get_team()
            best = None
            best_hp = None
            for _d, dx, dy in CARDINALS:
                spot = Position(here.x + dx, here.y + dy)
                bid = ct.get_tile_building_id(spot)
                if bid is None or ct.get_team(bid) == mine:
                    continue
                kind = ct.get_entity_type(bid)
                if kind not in (EntityType.GUNNER, EntityType.SENTINEL):
                    continue
                if kind == EntityType.SENTINEL and self._tended(ct, spot, mine):
                    continue
                hp = ct.get_hp(bid)
                if best_hp is None or hp < best_hp:
                    best, best_hp = spot, hp
            return best
        except Exception:
            return None

    def _home_heartbeat(self, ct):
        if self.home_slot is None:
            for i in range(SLOT_HOMES):
                if not _fresh(_beat(self._read(ct, SLOT_HOME0 + i)), self.round, 2):
                    self.home_slot = i
                    break
            if self.home_slot is None:
                self.home_slot = SLOT_HOMES - 1
        flags = (1 if self.mining_now else 0) | (min(7, len(self.my_harvesters)) << 1)
        self._write(ct, SLOT_HOME0 + self.home_slot, (self.round + 1) + 65536 * flags)

    def _lane_barrier(self, ct, here, max_walk=99, dry=False):
        """steward's rebuild-tank: a 3 Ti barrier in a live enemy Gunner lane onto our Core
        absorbs that Gunner's whole clock.  Sentinel lanes cannot be blocked and fall through
        to mending."""
        try:
            affordable = ct.get_global_resources() >= ct.get_barrier_cost() + 2
            if not affordable and not dry:
                return False
            mine = ct.get_team()
            own = set(self.mine_tiles)
            best = None
            sources = []
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) == mine or ct.get_entity_type(uid) != EntityType.GUNNER:
                    continue
                origin = ct.get_position(uid)
                sources.append(((origin.x, origin.y), ct.get_direction(uid).delta()))
            told = self._read(ct, SLOT_SHOOTER)
            if _extra(told) >= 2:
                tpos = _unpack(told)
                facing = RAYS[(_extra(told) - 2) // 4 % 8]
                if tpos is not None:
                    sources.append((tpos, (facing[1], facing[2])))
            for origin_key, (dx, dy) in sources:
                origin = Position(origin_key[0], origin_key[1])
                if dx == 0 and dy == 0:
                    continue
                tile = (origin.x + dx, origin.y + dy)
                lane = []
                while (0 <= tile[0] < self.width and 0 <= tile[1] < self.height
                       and tile not in self.walls
                       and (tile[0] - origin.x) ** 2 + (tile[1] - origin.y) ** 2 <= GUNNER_RANGE_SQ):
                    if tile in own:
                        for spot in lane:
                            # stand beside it on a tile nothing shoots: the Builder that laid
                            # (14,10) from (13,10) stood on the Gunner's ray for seven rounds
                            stand = None
                            for _d, ax, ay in CARDINALS:
                                step = (spot[0] + ax, spot[1] + ay)
                                if step in self.home_danger or not self._passable(step):
                                    continue
                                cost = self._dist.get(step)
                                if cost is not None and (stand is None or cost < stand):
                                    stand = cost
                            if stand is None:
                                continue
                            rank = (stand, spot)
                            if best is None or rank < best:
                                best = rank
                        break
                    if tile in self.occupied:
                        break                      # a building already soaks this lane
                    if not self._tile_has_builder(ct, tile):
                        lane.append(tile)          # a Builder of ours standing here is 40 HP, not a wall
                    tile = (tile[0] + dx, tile[1] + dy)
            if best is None or _cheb(best[1], (here.x, here.y)) > max_walk:
                return None if dry else False      # reach is distance, not the danger-weighted cost
            spot = best[1]
            if dry:
                return spot
            if abs(spot[0] - here.x) + abs(spot[1] - here.y) == 1:
                pos = Position(spot[0], spot[1])
                if ct.can_build_barrier(pos):
                    ct.build_barrier(pos)
                    self.occupied.add(spot)
                    self.blocked.add(spot)
                    self.my_barriers.add(spot)
                    return True
                return False
            if (here.x, here.y) == spot:
                return self._step_any(ct, here)
            self._walk_beside(ct, here, spot, safe=True)
            return True
        except Exception:
            return None if dry else False

    def _counter_turret(self, ct, here):
        """One turret seated on a ray to the turret shooting our Core.  A Sentinel cannot rotate,
        so a seat off its line is never shot back at, and three shots end it for good."""
        targets = []
        own = set(self.mine_tiles)
        for uid, known in self.turrets.items():
            if known[2] & own and known[3] == EntityType.SENTINEL:
                targets.append(known[0])
        told = self._read(ct, SLOT_SHOOTER)
        if _extra(told) == 1:                      # the Core names a Sentinel
            told = _unpack(told)
            if told is not None and told not in targets:
                targets.append(told)
        if not targets:
            return False
        try:
            sentinel_ok = (ct.get_global_resources() >= ct.get_sentinel_cost()
                           and ct.get_global_ammo() + ct.get_global_resources() >= 40)
        except Exception:
            sentinel_ok = False
        kind = EntityType.SENTINEL if sentinel_ok else EntityType.GUNNER
        return self._seat_turret(ct, here, targets, kind)

    def _anti_builder_gunner(self, ct, here):
        """A rotatable Gunner against Builders working at our Core: it shoots the first thing on
        its line, which is the wall they are laying as much as the Builder laying it."""
        targets = []
        try:
            mine = ct.get_team()
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) == mine or ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                    continue
                p = ct.get_position(uid)
                if min(_cheb((p.x, p.y), t) for t in self.mine_tiles) <= LOITER_REACH + 1:
                    targets.append((p.x, p.y))
        except Exception:
            return False
        if not targets:
            return False
        return self._seat_turret(ct, here, targets, EntityType.GUNNER)

    def _boxes_a_builder(self, ct, spot):
        """Would a building on spot leave a Builder of ours beside it with no exit?"""
        try:
            mine = ct.get_team()
            for _d, dx, dy in CARDINALS:
                key = (spot[0] + dx, spot[1] + dy)
                bid = ct.get_tile_builder_bot_id(Position(key[0], key[1]))
                if bid is None or ct.get_team(bid) != mine:
                    continue
                exits = 0
                for _e, ex, ey in CARDINALS:
                    step = (key[0] + ex, key[1] + ey)
                    if step != spot and self._passable(step):
                        exits += 1
                if exits == 0:
                    return True
        except Exception:
            return True
        return False

    def _seat_turret(self, ct, here, targets, kind):
        reach = MAX_RANGE_SQ if kind == EntityType.SENTINEL else GUNNER_RANGE_SQ
        ring_tiles = set(_ring(self.mine_tiles))
        seats = []
        for tpos in targets:
            for facing, dx, dy in RAYS:
                span = 1 if (dx == 0 or dy == 0) else 2
                k = 1
                while k * k * span <= reach:
                    spot = (tpos[0] - dx * k, tpos[1] - dy * k)
                    k += 1
                    if not (0 <= spot[0] < self.width and 0 <= spot[1] < self.height):
                        continue
                    if spot in self.walls or spot in self.occupied or spot in self.mine_tiles or spot in self.ore:
                        continue
                    if spot in self.lanes:
                        continue                   # never seat a turret where it gets shot
                    if _cheb(spot, self.mine_tiles[0]) > 6:
                        continue                   # the guard stays at home
                    if spot in ring_tiles:
                        continue                   # the ring is where the menders stand
                    if self._boxes_a_builder(ct, spot):
                        continue                   # two Gunners and a Sentinel boxed a mender in for 280 rounds
                    near = None
                    for _d, ax, ay in CARDINALS:
                        step = (spot[0] + ax, spot[1] + ay)
                        cost = self._dist.get(step)
                        if cost is not None and (near is None or cost < near):
                            near = cost
                    if near is None:
                        continue
                    seats.append((near, 0, spot, facing, tpos))
        if not seats:
            return False
        seats.sort(key=lambda s: (s[0], s[1], s[2]))
        for near, _r, spot, facing, tpos in seats[:6]:
            pos = Position(spot[0], spot[1])
            try:
                if kind == EntityType.GUNNER and not ct.is_in_vision(Position(tpos[0], tpos[1])):
                    continue
                if not ct.can_fire_from(pos, facing, kind, Position(tpos[0], tpos[1])):
                    continue
            except Exception:
                continue
            if abs(spot[0] - here.x) + abs(spot[1] - here.y) == 1:
                try:
                    if kind == EntityType.SENTINEL and ct.can_build_sentinel(pos, facing):
                        ct.build_sentinel(pos, facing)
                    elif kind == EntityType.GUNNER and ct.can_build_gunner(pos, facing):
                        ct.build_gunner(pos, facing)
                    else:
                        continue
                    self.occupied.add(spot)
                    self.blocked.add(spot)
                    return True
                except Exception:
                    continue
            if (here.x, here.y) == spot:
                return self._step_any(ct, here)
            self._walk_beside(ct, here, spot)
            return True
        return False

    def _step_any(self, ct, here):
        for direction, dx, dy in CARDINALS:
            step = (here.x + dx, here.y + dy)
            if self._passable(step) and step not in self.home_danger:
                try:
                    if ct.can_move(direction):
                        ct.move(direction)
                        return True
                except Exception:
                    continue
        return False

    def _to_post(self, ct, here):
        """Stand on a ring tile -- one no enemy turret covers, if there is one.  A Gunner shoots
        the first Builder on its line, and a mender standing in it is dead in six rounds.  If
        the ring is walled off, shoot the wall: TRRR boxed hildr's Core in eight barriers and
        three Builders stood still for 850 rounds."""
        covered = self.home_danger
        if self.post is not None and (here.x, here.y) == self.post and self.post not in covered:
            return
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
            score = cost + (20 if key in covered else 0)
            for _d, dx, dy in CARDINALS:
                if (key[0] + dx, key[1] + dy) in self.my_barriers:
                    score -= 5                     # beside our barrier: their Gunner holds its fire
                    break
            if best is None or score < best:
                best, chosen = score, key
        self.post = chosen
        if chosen is None:
            if BREAK_OUT:
                self._break_out(ct, here)
            return
        if chosen == (here.x, here.y):
            return
        path = self._trace(self._came, here, chosen)
        if path:
            self._step_to(ct, here, path[0])

    def _break_out(self, ct, here):
        """Fire at an enemy barrier beside us, ring tiles first.  2 Ti a hit, fifteen hits."""
        try:
            if ct.get_global_resources() < 4:
                return False
            ring = set(_ring(self.mine_tiles))
            best = None
            chosen = None
            for _d, dx, dy in CARDINALS:
                key = (here.x + dx, here.y + dy)
                if key not in self.enemy_barriers:
                    continue
                spot = Position(key[0], key[1])
                if not ct.can_fire(spot):
                    continue
                if self._tended(ct, spot, ct.get_team()):
                    continue                       # they heal it for 1 Ti what we dig for 2
                score = 0 if key in ring else 1
                if best is None or score < best:
                    best, chosen = score, spot
            if chosen is not None:
                ct.fire(chosen)
                return True
            # nothing beside us: walk to the nearest enemy barrier on our ring
            target = None
            tbest = None
            for key in ring:
                if key not in self.enemy_barriers:
                    continue
                for _d, dx, dy in CARDINALS:
                    step = (key[0] + dx, key[1] + dy)
                    cost = self._dist.get(step)
                    if cost is not None and (tbest is None or cost < tbest):
                        tbest, target = cost, key
            if target is not None:
                self._walk_beside(ct, here, target)
                return True
        except Exception:
            pass
        return False

    def _tile_has_builder(self, ct, key):
        try:
            bid = ct.get_tile_builder_bot_id(Position(key[0], key[1]))
            return bid is not None
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------ economy
    def _repair_belt(self, ct, here):
        """A hole in the line outranks laying more of it: every Harvester upstream of a gap is
        mining into a dead end, and one 3 Ti tile restores the whole line's income."""
        gone = []
        for key in list(self.my_harvesters):
            try:
                spot = Position(key[0], key[1])
                if ct.is_in_vision(spot) and ct.get_tile_building_id(spot) is None:
                    gone.append(key)
            except Exception:
                continue
        for key in gone:
            self.my_harvesters.discard(key)
        broken = None
        bbest = None
        for key, facing in self.belts.items():
            if self.repair_fail.get(key, 0) >= REPAIR_ATTEMPT_LIMIT:
                continue
            try:
                spot = Position(key[0], key[1])
                if not ct.is_in_vision(spot) or ct.get_tile_building_id(spot) is not None:
                    continue
            except Exception:
                continue
            if key in self.walls:
                continue
            cost = self._dist.get(key, 99)
            if bbest is None or cost < bbest:
                bbest, broken = cost, key
        if broken is None:
            return False
        try:
            if ct.get_global_resources() < ct.get_conveyor_cost() + 5:
                return True
            if abs(broken[0] - here.x) + abs(broken[1] - here.y) == 1:
                spot = Position(broken[0], broken[1])
                facing = self.belts[broken]
                if ct.can_build_conveyor(spot, facing):
                    ct.build_conveyor(spot, facing)
                    self.occupied.add(broken)
                    return True
                self.repair_fail[broken] = self.repair_fail.get(broken, 0) + 1
                return False
            if (here.x, here.y) == broken:
                return self._step_any(ct, here)
            self._walk_beside(ct, here, broken)
            return True
        except Exception:
            return False

    def _patrol_belt(self, ct, here):
        """Walk to the belt tile longest out of sight.  A hole is only ever repaired when seen,
        and on helheim the miner extended a trunk whose two tiles nearest the Core had been
        shot out sixty rounds earlier -- income frozen at 110 for the rest of the game."""
        if not self.belts:
            return False
        stale = None
        sbest = None
        for key in self.belts:
            age = self.round - self.belt_seen.get(key, -1000)
            if age < 40:
                continue
            cost = min((self._dist.get((key[0] + dx, key[1] + dy), 99) for _d, dx, dy in CARDINALS), default=99)
            if cost > 14:
                continue
            rank = (-age, cost)
            if sbest is None or rank < sbest:
                sbest, stale = rank, key
        if stale is None:
            return False
        self._walk_beside(ct, here, stale)
        return True

    def _mine(self, ct, here):
        """One Harvester and a belt home -- to the Core, or into a belt of ours that already
        reaches it.  Returns True while there is a job in hand."""
        if self.chain is None or (not self.chain and self.round >= self.replan_at):
            if self.team_harvesters >= HARVESTERS_MAX:
                self.chain = []
                self.replan_at = self.round + 10
                return False
            planned = self._plan_chain(ct)
            if planned is None:
                self.chain = []
                self.replan_at = self.round + 20
            else:
                self.chain, self.chain_end = planned
        if not self.chain:
            return False
        try:
            ti = ct.get_global_resources()
        except Exception:
            return False
        # Lay the belt from the home end outward; every tile points at the next one toward
        # home, and the last one points into the Core (or the belt it joins).
        for idx in range(len(self.chain) - 1, 0, -1):
            key = self.chain[idx]
            if key in self.occupied:
                continue
            onward = self.chain[idx + 1] if idx + 1 < len(self.chain) else self.chain_end
            facing = _facing_to(key, onward)
            if facing is None:
                self.chain = []
                return False
            try:
                if ti < ct.get_conveyor_cost() + BELT_MARGIN:
                    return True
            except Exception:
                pass
            if abs(key[0] - here.x) + abs(key[1] - here.y) == 1:
                try:
                    if ct.can_build_conveyor(Position(key[0], key[1]), facing):
                        ct.build_conveyor(Position(key[0], key[1]), facing)
                        self.occupied.add(key)
                        self.laid[key] = facing
                        self.belts[key] = facing
                        return True
                    self.chain = []            # somebody built here first; plan again
                    self.replan_at = self.round + 2
                    return True
                except Exception:
                    self.chain = []
                    self.replan_at = self.round + 2
                    return True
            if (here.x, here.y) == key:
                return self._step_inward(ct, here, onward)
            preferred = (onward if onward not in self.mine_tiles
                         else self.chain[idx - 1] if idx > 1 else None)
            if (not self.chain_staging or preferred is None
                    or not self._walk_to_tile(ct, here, preferred)):
                self._walk_beside(ct, here, key)
            return True
        ore = self.chain[0]
        if ore not in self.occupied:
            try:
                if ti < ct.get_harvester_cost() + (5 if self.team_harvesters == 0 else ECON_MARGIN):
                    return True
            except Exception:
                pass
            if abs(ore[0] - here.x) + abs(ore[1] - here.y) == 1:
                try:
                    if ct.can_build_harvester(Position(ore[0], ore[1])):
                        ct.build_harvester(Position(ore[0], ore[1]))
                        self.occupied.add(ore)
                        self.blocked.add(ore)
                        self.my_harvesters.add(ore)
                        self.chain = []
                        self.replan_at = self.round + 1
                        return True
                    self.chain = []
                    self.replan_at = self.round + 2
                    return True
                except Exception:
                    self.chain = []
                    self.replan_at = self.round + 2
                    return True
            if (here.x, here.y) == ore:
                inward = self.chain[1] if len(self.chain) > 1 else self.chain_end
                return self._step_inward(ct, here, inward)
            inward = self.chain[1] if len(self.chain) > 1 else self.chain_end
            if not self.chain_staging or not self._walk_to_tile(ct, here, inward):
                self._walk_beside(ct, here, ore)
            return True
        self.chain = []
        return False

    def _plan_chain(self, ct):
        """Pick an ore tile and the belt that carries it home.  Returns ([ore, c1, ..., ck], end)
        with ck beside `end`, which is a Core tile or a conveyor of ours; or None."""
        dist = {}
        came = {}
        end_of = {}
        frontier = []
        for key in self.mine_tiles:
            for _d, dx, dy in CARDINALS:
                step = (key[0] + dx, key[1] + dy)
                if step in self.mine_tiles or step in dist:
                    continue
                if step in self.walls or (step in self.occupied and step not in self.ore):
                    continue
                if not (0 <= step[0] < self.width and 0 <= step[1] < self.height):
                    continue
                dist[step] = 0
                came[step] = None
                end_of[step] = key
                frontier.append(step)
        if JOIN_BELTS:
            for belt, facing in self.belts.items():
                if belt not in self.occupied:
                    continue                       # shot out: a repair job, not a seed
                out = (belt[0] + facing.delta()[0], belt[1] + facing.delta()[1])
                for _d, dx, dy in CARDINALS:
                    step = (belt[0] + dx, belt[1] + dy)
                    if step == out or step in dist or step in self.mine_tiles:
                        continue
                    if step in self.walls or (step in self.occupied and step not in self.ore):
                        continue
                    if not (0 <= step[0] < self.width and 0 <= step[1] < self.height):
                        continue
                    dist[step] = 1                 # a join is worth a tile of walking less than the Core
                    came[step] = None
                    end_of[step] = belt
                    frontier.append(step)
        if not frontier:
            return None
        goal = None
        while frontier and goal is None:
            nxt = []
            for key in frontier:
                if key in self.ore and key not in self.occupied and not self._enemy_beside(ct, key):
                    goal = key
                    break
                if dist[key] > 18 or key in self.ore:
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
        seed = None
        while walk is not None:
            chain.append(walk)
            seed = walk
            walk = came[walk]
        return chain, end_of[seed]

    def _enemy_beside(self, ct, key):
        """A Harvester outputs to ANY adjacent building: an ore beside their belt feeds them."""
        try:
            mine = ct.get_team()
            for _d, dx, dy in CARDINALS:
                spot = Position(key[0] + dx, key[1] + dy)
                if not ct.is_in_vision(spot):
                    continue
                bid = ct.get_tile_building_id(spot)
                if bid is not None and ct.get_team(bid) != mine:
                    return True
        except Exception:
            pass
        return False

    def _walk_beside(self, ct, here, key, safe=False):
        """One step toward standing NEXT TO a tile -- building never happens from on top of it."""
        best = None
        chosen = None
        for _d, dx, dy in CARDINALS:
            step = (key[0] + dx, key[1] + dy)
            if safe and step in self.home_danger:
                continue
            cost = self._dist.get(step)
            if cost is not None and (best is None or cost < best):
                best, chosen = cost, step
        if chosen is None or chosen == (here.x, here.y):
            return
        path = self._trace(self._came, here, chosen)
        if path:
            self._step_to(ct, here, path[0])

    def _step_inward(self, ct, here, inward):
        """Vacate a build tile through the finished network, not a random side-step."""
        if not self.chain_staging:
            return self._step_any(ct, here)
        if inward not in self.mine_tiles and self._step_to(ct, here, inward):
            return True
        return self._step_any(ct, here)

    def _walk_to_tile(self, ct, here, target):
        if target == (here.x, here.y):
            return False
        path = self._trace(self._came, here, target)
        return bool(path and self._step_to(ct, here, path[0]))

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
        self.chain_staging = (
            ((self.width, self.height), (core.x, core.y)) not in CHAIN_STAGING_EXCLUDED
        )
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

    def _observe(self, ct, here):
        try:
            tiles = ct.get_nearby_tiles()
        except Exception:
            return
        mine = None
        try:
            mine = ct.get_team()
        except Exception:
            pass
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
                self.enemy_barriers.discard(key)
                if key in self.belts:
                    self.belt_seen[key] = self.round   # seen, and seen gone: a repair job
            else:
                self.occupied.add(key)
                blocks = True
                try:
                    kind = ct.get_entity_type(bid)
                    blocks = kind not in (EntityType.CONVEYOR, EntityType.SPLITTER)
                    if kind == EntityType.BARRIER and mine is not None and ct.get_team(bid) != mine:
                        self.enemy_barriers.add(key)
                    else:
                        self.enemy_barriers.discard(key)
                    if kind == EntityType.CONVEYOR and mine is not None and ct.get_team(bid) == mine:
                        self.belts[key] = ct.get_direction(bid)
                        self.belt_seen[key] = self.round
                    if (kind in (EntityType.HARVESTER, EntityType.CONVEYOR, EntityType.SPLITTER)
                            and mine is not None and ct.get_team(bid) != mine):
                        self.econ_seen = True
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

    def _free_spot(self, key, strict=False):
        if not (key in self.spots and key not in self.walls
                and key not in self.occupied and key not in self.poisoned
                and 0 <= key[0] < self.width and 0 <= key[1] < self.height):
            return False
        if strict and AVOID_COVERED_SPOTS and key in self.lanes:
            return False
        return True

    def _place(self, ct, here):
        """Build on an adjacent firing spot -- unless that spot is on our own route to the anchor,
        or a known enemy turret covers it and an uncovered one is within reach."""
        at_goal = self.goal is None or (here.x, here.y) == self.goal
        if not at_goal and not self._path_usable(here, self.goal):
            self.path = self._trace(self._came, here, self.goal)
        route = set(self.path) if not at_goal else set()
        # Covered spots are taken only once we have stood at the anchor for a while with
        # nothing better: a Sentinel planted into a Gunner's line is 40 HP for their 12 ammo.
        strict = AVOID_COVERED_SPOTS and self.stand_rounds < 3
        for _d, dx, dy in CARDINALS:
            key = (here.x + dx, here.y + dy)
            if not self._free_spot(key, strict):
                continue
            if key in route:
                continue
            if not at_goal and self.goal is not None and not self._still_reachable(here, key):
                continue
            if self.built + 1 < self.ring_target and not self._exit_besides(here, key):
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
            self.placed.append(key)
            self.placed_round[key] = self.round
            self.last_place = self.round
            self.stand_rounds = 0
            self.blocked.add(key)
            self.occupied.add(key)
            self.path = []
            self._write(ct, SLOT_BUILT, self.built)
            return True
        if at_goal:
            self.stand_rounds += 1
        return False

    def _exit_besides(self, here, key):
        for _d, dx, dy in CARDINALS:
            step = (here.x + dx, here.y + dy)
            if step != key and self._passable(step):
                return True
        return False

    def _still_reachable(self, here, key):
        """Would the anchor still be as close with a turret on `key`?"""
        before = self._dist.get(self.goal)
        if before is None:
            return True
        self.blocked.add(key)
        dist, _came = self._flood(here, None)
        self.blocked.discard(key)
        after = dist.get(self.goal)
        return after is not None and after <= before + 1

    def _next_stand(self, here):
        want = self.ring_target - self.built
        best = None
        chosen = None
        for key, cost in self._dist.items():
            if key in self.grabs:
                continue                           # steward's pad flung the attacker from here twice
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
        will not be finished here.  Uncovered spots count double."""
        usable = 0
        exits = 0
        for _d, dx, dy in CARDINALS:
            step = (key[0] + dx, key[1] + dy)
            if self._passable(step):
                exits += 1
            if self._free_spot(step):
                usable += 1
        want = self.ring_target - self.built
        if usable < want:
            usable = min(usable, exits - 1)
        return max(0, usable)

    def _threats(self, ct):
        soft = set()
        grabs = set()
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
                    self.enemy_ids.add(uid)
                    if self.mine_tiles and self.enemy is not None:
                        to_ours = _cheb((spot.x, spot.y), self.mine_tiles[0])
                        to_theirs = _cheb((spot.x, spot.y), (self.enemy.x, self.enemy.y))
                        if to_ours <= to_theirs + 2 and to_theirs > 2:
                            self.rush_seen = True
                elif kind == EntityType.LAUNCHER:
                    # It grabs any Builder that walks adjacent and flings it across the map.
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            soft.add((spot.x + dx, spot.y + dy))
                            grabs.add((spot.x + dx, spot.y + dy))
                elif kind in (EntityType.GUNNER, EntityType.SENTINEL):
                    facing = ct.get_direction(uid)
                    known = self.turrets.get(uid)
                    if known is None or known[0] != (spot.x, spot.y) or known[1] != facing:
                        covered = ct.get_attackable_tiles_from(spot, facing, kind)
                        self.turrets[uid] = ((spot.x, spot.y), facing,
                                             frozenset((t.x, t.y) for t in covered), kind)
        except Exception:
            pass

        stale = []
        lanes = set()
        danger = set()
        own = set(self.mine_tiles)
        for uid, known in self.turrets.items():
            spot = Position(known[0][0], known[0][1])
            try:
                if ct.is_in_vision(spot) and ct.get_tile_building_id(spot) is None:
                    stale.append(uid)
                    continue
            except Exception:
                pass
            lanes |= known[2]
            # A Sentinel aimed at our Core shoots the Core, through anything; a mender on its
            # ray is safe there.  A Gunner shoots the first thing on its ray, and a Sentinel
            # aimed elsewhere is a guard that shoots Builders.
            if known[3] == EntityType.GUNNER or not (known[2] & own):
                danger |= known[2]
        for uid in stale:
            del self.turrets[uid]
        self.lanes = lanes
        self.home_danger = danger | soft
        self.grabs = grabs
        return soft | lanes

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
        """Ring is up.  Mend it -- from a tile nothing is shooting at.  Returns True when the
        turn was used (a step out of a lane, or a heal)."""
        try:
            covered = self.covered
            if (here.x, here.y) in covered:
                best = None
                chosen = None
                for direction, dx, dy in CARDINALS:
                    step = (here.x + dx, here.y + dy)
                    if not self._passable(step) or step in covered:
                        continue
                    ring_adj = sum(1 for _d, ax, ay in CARDINALS
                                   if (step[0] + ax, step[1] + ay) in self.occupied)
                    if best is None or ring_adj > best:
                        best, chosen = ring_adj, step
                if chosen is not None:
                    self._step_to(ct, here, chosen)
                    return True
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
                    return True
            # anything of ours hurt within sight: walk to it
            mine = ct.get_team()
            target = None
            tbest = None
            for bid in ct.get_nearby_buildings():
                if ct.get_team(bid) != mine:
                    continue
                if ct.get_entity_type(bid) != EntityType.SENTINEL:
                    continue
                if ct.get_hp(bid) >= ct.get_max_hp(bid):
                    continue
                p = ct.get_position(bid)
                d = abs(p.x - here.x) + abs(p.y - here.y)
                if tbest is None or d < tbest:
                    tbest, target = d, (p.x, p.y)
            if target is not None:
                self._walk_beside(ct, here, target)
                return True
        except Exception:
            return False
        return False

    def _deny_ore(self, ct, here):
        """steward's ore denial: a 3 Ti barrier on an enemy-half ore tile keeps a Harvester off
        it for the match.  The attacker does it between tending jobs, within a short leash of
        the ring, and never from a covered tile."""
        try:
            if ct.get_global_resources() < ct.get_barrier_cost() + 40:
                return False
            if self.deny_target is not None and (self.deny_target in self.occupied
                                                 or self.deny_target in self.denied):
                self.deny_target = None
            if self.deny_target is None:
                best = None
                for key in self.ore:
                    if key in self.occupied or key in self.denied:
                        continue
                    if _cheb(key, (self.enemy.x, self.enemy.y)) > _cheb(key, self.mine_tiles[0]):
                        continue                   # their half only
                    near = None
                    for _d, dx, dy in CARDINALS:
                        step = (key[0] + dx, key[1] + dy)
                        cost = self._dist.get(step)
                        if cost is not None and step not in self.covered and (near is None or cost < near):
                            near = cost
                    if near is None or near > DENY_REACH:
                        continue
                    if best is None or near < best[0]:
                        best = (near, key)
                if best is None:
                    return False
                self.deny_target = best[1]
            key = self.deny_target
            if abs(key[0] - here.x) + abs(key[1] - here.y) == 1:
                spot = Position(key[0], key[1])
                if ct.can_build_barrier(spot):
                    ct.build_barrier(spot)
                    self.occupied.add(key)
                    self.blocked.add(key)
                    self.denied.add(key)
                    self.deny_target = None
                    return True
                self.denied.add(key)
                self.deny_target = None
                return False
            if (here.x, here.y) == key:
                return self._step_any(ct, here)
            self._walk_beside(ct, here, key)
            return True
        except Exception:
            return False

    # --------------------------------------------------------------- sentinel
    def _counter_battery(self, ct):
        """An enemy turret on our ray is digging the ring out: a Gunner dies to two shots."""
        try:
            mine = ct.get_team()
            best = None
            best_hp = None
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) == mine:
                    continue
                kind = ct.get_entity_type(uid)
                if kind not in (EntityType.GUNNER, EntityType.SENTINEL):
                    continue
                p = ct.get_position(uid)
                if not ct.can_fire(p):
                    continue
                hp = ct.get_hp(uid) + (0 if kind == EntityType.GUNNER else 100)
                if best_hp is None or hp < best_hp:
                    best, best_hp = p, hp
            if best is not None:
                ct.fire(best)
                return True
        except Exception:
            pass
        return False

    def _sentinel(self, ct):
        if self.enemy is None:
            found = _unpack(self._read(ct, SLOT_ENEMY))
            if found is None:
                return
            self.enemy = Position(found[0], found[1])
            self.enemy_tiles = _footprint(self.enemy)
        if self.guard is None:
            self.guard = not self._ring_sentinel(ct)
        if self.guard:
            self._guard(ct)
            return
        if self.slot is None:
            for i in range(SLOT_BEATS):
                if not _fresh(self._read(ct, SLOT_BEAT0 + i), self.round, 2):
                    self.slot = i
                    break
            if self.slot is None:
                self.slot = SLOT_BEATS - 1
        self._write(ct, SLOT_BEAT0 + self.slot, self.round + 1)
        self._act(ct)
        self._report_enemy(ct)

    def _ring_sentinel(self, ct):
        """Can this Sentinel's line reach the enemy Core?  Geometry, not can_fire: that folds
        ammunition and cooldown into its answer."""
        try:
            here = ct.get_position()
            return _on_ray((here.x, here.y), ct.get_direction().delta(), self.enemy_tiles, MAX_RANGE_SQ)
        except Exception:
            return True

    def _guard(self, ct):
        """Home guard: the turret shooting us, the Builder working at our Core, their economy,
        then an untended barrier on our ring."""
        try:
            mine = ct.get_team()
            here = ct.get_position()
            best = None
            best_rank = None
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) == mine:
                    continue
                kind = ct.get_entity_type(uid)
                p = ct.get_position(uid)
                if not ct.can_fire(p):
                    continue
                if kind in (EntityType.GUNNER, EntityType.SENTINEL):
                    rank = (0, ct.get_hp(uid))
                elif kind == EntityType.BUILDER_BOT:
                    rank = (1, p.distance_squared(here))
                else:
                    continue
                if best_rank is None or rank < best_rank:
                    best, best_rank = p, rank
            if best is None:
                for bid in ct.get_nearby_buildings():
                    if ct.get_team(bid) == mine:
                        continue
                    kind = ct.get_entity_type(bid)
                    order = {EntityType.HARVESTER: 2, EntityType.SPLITTER: 3,
                             EntityType.CONVEYOR: 4, EntityType.BARRIER: 5}.get(kind)
                    if order is None:
                        continue
                    p = ct.get_position(bid)
                    if not ct.can_fire(p):
                        continue
                    if kind == EntityType.BARRIER and self._tended(ct, p, mine):
                        continue
                    rank = (order, ct.get_hp(bid))
                    if best_rank is None or rank < best_rank:
                        best, best_rank = p, rank
            if best is not None:
                ct.fire(best)
        except Exception:
            return

    def _tended(self, ct, spot, mine):
        """A barrier with an enemy Builder beside it (any of the eight) is rebuilt for 3 Ti the
        round we break it, and a turret with one beside it is mended as we dig."""
        try:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    bid = ct.get_tile_builder_bot_id(Position(spot.x + dx, spot.y + dy))
                    if bid is not None and ct.get_team(bid) != mine:
                        return True
        except Exception:
            pass
        return False

    def _tenders(self, ct, spot, mine):
        """Enemy Builders orthogonally beside a tile -- the ones that can heal it."""
        n = 0
        try:
            for _d, dx, dy in CARDINALS:
                bid = ct.get_tile_builder_bot_id(Position(spot.x + dx, spot.y + dy))
                if bid is not None and ct.get_team(bid) != mine:
                    n += 1
        except Exception:
            pass
        return n

    def _act(self, ct):
        if self._counter_battery(ct):
            return
        go = self._read(ct, SLOT_GO, 1)
        if go == 1:
            for key in self.enemy_tiles:
                spot = Position(key[0], key[1])
                try:
                    if ct.can_fire(spot):
                        ct.fire(spot)
                        return
                except Exception:
                    continue
            return
        if go != 2:
            return
        # A volley: Harvester first, then a mender on the ring, then a belt -- never a building
        # with their Builder beside it: 0033 healed one conveyor with three Builders for 600
        # rounds while our last Sentinel spent exactly the passive income on it.
        try:
            mine = ct.get_team()
            ring = set(_ring(self.enemy_tiles))
            best = None
            best_rank = None
            for uid in ct.get_nearby_buildings():
                if ct.get_team(uid) == mine:
                    continue
                kind = ct.get_entity_type(uid)
                rank = {EntityType.HARVESTER: 0, EntityType.CONVEYOR: 2, EntityType.SPLITTER: 2}.get(kind)
                if rank is None:
                    continue
                p = ct.get_position(uid)
                if self._tenders(ct, p, mine) >= 2:
                    continue                       # 18 a shot every 4 rounds loses to 8 HP a round of mending
                if (best_rank is None or rank < best_rank) and ct.can_fire(p):
                    best, best_rank = p, rank
            if best_rank != 0:
                for uid in ct.get_nearby_units():
                    if ct.get_team(uid) == mine or ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                        continue
                    p = ct.get_position(uid)
                    if ct.can_fire(p):
                        rank = 1 if (p.x, p.y) in ring else 3
                        if best_rank is None or rank < best_rank:
                            best, best_rank = p, rank
            if best is None and ct.get_global_ammo() >= 150:
                for key in self.enemy_tiles:
                    spot = Position(key[0], key[1])
                    if ct.can_fire(spot):
                        best = spot
                        break
            if best is not None:
                ct.fire(best)
        except Exception:
            return

    # ----------------------------------------------------------------- gunner
    def _gunner(self, ct):
        """steward's Gunner: fire down the ray if an enemy is first on it, else turn onto the
        nearest enemy it could actually hit (10 Ti, only with a bank behind it)."""
        try:
            mine = ct.get_team()
            target = ct.get_gunner_target()
            if target is not None:
                tid = ct.get_tile_builder_bot_id(target)
                if tid is None:
                    tid = ct.get_tile_building_id(target)
                if tid is not None and ct.get_team(tid) != mine:
                    blocked = (ct.get_entity_type(tid) == EntityType.BARRIER
                               and self._tended(ct, target, mine))
                    if not blocked and ct.can_fire(target):
                        ct.fire(target)
                        return
                    if not blocked:
                        return                     # reloading or dry: the line is live, hold it
            if ct.get_global_resources() < ROTATE_RESERVE:
                return
            here = ct.get_position()
            enemies = []
            for uid in ct.get_nearby_units():
                if ct.get_team(uid) == mine:
                    continue
                kind = ct.get_entity_type(uid)
                order = {EntityType.BUILDER_BOT: 0, EntityType.GUNNER: 1, EntityType.SENTINEL: 1}.get(kind, 3)
                p = ct.get_position(uid)
                enemies.append((order, p.distance_squared(here), uid, p))
            for bid in ct.get_nearby_buildings():
                if ct.get_team(bid) == mine:
                    continue
                if ct.get_entity_type(bid) != EntityType.BARRIER:
                    continue
                p = ct.get_position(bid)
                if self._tended(ct, p, mine):
                    continue
                enemies.append((2, p.distance_squared(here), bid, p))
            enemies.sort(key=lambda e: (e[0], e[1], e[2]))
            for _o, _d, _uid, p in enemies:
                if p.distance_squared(here) > GUNNER_RANGE_SQ:
                    continue
                for direction, dx, dy in RAYS:
                    if not ct.can_fire_from(here, direction, EntityType.GUNNER, p):
                        continue
                    if not ct.can_rotate(direction):
                        continue
                    ct.rotate(direction)
                    return
        except Exception:
            return

    # --------------------------------------------------------------- launcher
    def _launcher(self, ct):
        """We never build one, but if a Launcher of ours exists it flings an adjacent enemy
        Builder to the legal tile farthest from our Core."""
        try:
            mine = ct.get_team()
            home = Position(self.mine_tiles[0][0], self.mine_tiles[0][1]) if self.mine_tiles else None
            if home is None:
                for bid in ct.get_nearby_buildings():
                    if ct.get_team(bid) == mine and ct.get_entity_type(bid) == EntityType.CORE:
                        home = ct.get_position(bid)
                        self.mine_tiles = _footprint(home)
                        break
            best = None
            for uid in ct.get_nearby_units(2):
                if ct.get_team(uid) == mine or ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                    continue
                origin = ct.get_position(uid)
                for tile in ct.get_nearby_tiles(26):
                    if not ct.can_launch(origin, tile):
                        continue
                    score = tile.distance_squared(home) if home is not None else tile.distance_squared(origin)
                    if best is None or score > best[0]:
                        best = (score, origin, tile)
            if best is not None:
                ct.launch(best[1], best[2])
        except Exception:
            return
