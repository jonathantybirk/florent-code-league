"""AutistimusPrime -- Florent Code League 2026.

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
travelled -- no guessing, no broken bends:

    build harvester on ore  ->  walk one step coreward  ->  build belt on the tile just vacated,
    facing the way we walked  ->  repeat  ->  on reaching the Core, step aside once so the final tile
    is buildable, and cap it with a belt facing into the Core footprint.

THE SIEGE IS COMPUTED, NOT LOOKED UP

Everything about the forward-gunner kill -- where the enemy Core is, which tile bears on it, which
deposit feeds the turret, what to build in what order -- is derived at match time from observed
terrain by `siege`. The bot carried a precomputed table for the fifteen published maps instead, and
on any map outside that table `atlas.identify()` returned None and the entire attack silently
switched itself off: measured ZERO core kills on every unseen map. The runtime path is now the only
path, so it is exercised on every map and cannot rot. The atlas is a pure accelerator -- it seeds
the enemy Core anchor and the static wall set when it recognises the map, and nothing depends on it.

Bot name is deliberate; the team knows.
"""

from fcode import Controller, Direction, EntityType, Environment, Position, Team

try:
    import atlas
except Exception:      # unknown-map fallback must always exist -- never stall like a pure-atlas bot
    atlas = None

try:
    import siege
except Exception:
    siege = None

CARDINALS = (Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST)
ALL_DIRS = tuple(d for d in Direction if d != Direction.CENTRE)
DIR_BY_NAME = {
    "NORTH": Direction.NORTH, "EAST": Direction.EAST,
    "SOUTH": Direction.SOUTH, "WEST": Direction.WEST,
    "NORTHEAST": Direction.NORTHEAST, "SOUTHEAST": Direction.SOUTHEAST,
    "SOUTHWEST": Direction.SOUTHWEST, "NORTHWEST": Direction.NORTHWEST,
}
# Index into siege.DELTA8 / siege.DIR_NAMES8, so a facing survives a trip through a store slot.
# Cardinals keep indices 0-3, so the packing in S_RUSH_RAY is unchanged for them; the diagonals
# need a third bit, and the ray they describe is two tiles long rather than three.
DIR_BY_NAME_INDEX = {"NORTH": 0, "EAST": 1, "SOUTH": 2, "WEST": 3,
                     "NORTHEAST": 4, "SOUTHEAST": 5, "SOUTHWEST": 6, "NORTHWEST": 7}
DIR_DELTAS = ((0, -1), (1, 0), (0, 1), (-1, 0), (1, -1), (1, 1), (-1, 1), (-1, -1))

# --- Communication store (16 slots, writes visible next round) ----------------
S_CORE_X = 0
S_CORE_Y = 1
S_SPAWN_ORD = 2
# Slot 3 used to be a count of completed chains that nothing ever read, then the home alarm.
# It is now the Core's published STATE WORD, of which the alarm is bit 0 with exactly its old
# meaning: 1 once our own Core has been hit hard enough that mining more titanium into it is
# worth less than keeping it standing (G01 -- titanium only scores while there is a Core
# footprint for the stacks to land on).
#
# There was no sixteenth slot to take. Every one of the 16 is spoken for -- N_CLAIMS was already
# cut to 5 to free slot 9 for the second attacker -- so the posture had to go somewhere that
# already existed. Slot 3 is the right somewhere: it is the ONLY slot with a single writer that
# is the Core, and the Core is the natural arbiter (it acts first every round and never moves).
# Folding the posture in beside the alarm also avoids the failure the brief warned about, of two
# independent mechanisms both deciding the base is in trouble and disagreeing.
S_STATE = 3
S_ALARM = S_STATE          # legacy name: the alarm is bit 0 of the same word
ALARM_BIT = 1
POSTURE_SHIFT = 1          # bits 1-2 carry the posture
S_CLAIM_0 = 4
# One slot fewer than before: slot 9 now carries the SECOND attacker's claim. With two of the six
# Builders on the siege there are only four economy Builders left to claim ore with, so five claim
# slots is one more than the economy can use.
N_CLAIMS = 5
S_RUSHER2 = 9         # id+1 of the second attacker; 0 = unclaimed
# Packed enemy Core anchor. Bit 16 set = SIGHTED, not merely inferred -- a sighting is authoritative
# and no inference may ever overwrite it.
S_ENEMY_CORE = 10
SIGHTED = 1 << 16
# Rejected-symmetry mask (3 bits). Every unit ORs what it has personally refuted into this, so one
# builder walking past a wall settles the map for the whole team. Rejections are monotone, so a
# lost write only costs a round.
S_SYMMETRY = 11
# ...and the same slot carries the ARCHETYPE EVIDENCE in the bits above it. The symmetry mask is
# three bits wide (siege.ALL_REJECTED == 0b111) and every reader of it already masks, so the top
# 29 bits of slot 11 were dead space. The two fields share a slot because they share a protocol
# exactly: both are MONOTONE -- a rejected symmetry is never un-rejected and an archetype never
# un-happens -- so the read-or-write merge that makes the symmetry mask safe against a lost write
# makes the evidence safe for free. Same writers (Builder Bots only), same rounds, same merge.
#
# The Core READS this slot and never writes it. That matters: a writer that does not maintain the
# symmetry mask would clobber three bits of it back to their previous round's value every time it
# published, which is a real regression for one line of convenience.
S_FLAGS = S_SYMMETRY
EV_MASK = 0xFFFFFFF8

EV_HURT = 1 << 3           # a unit of ours has lost hit points -- PROVES a fed enemy turret
EV_ECON_HIT = 1 << 4       # a belt of ours has been destroyed where we could see it
EV_INTRUDER = 1 << 5       # an enemy Builder Bot seen at or inside the midline
EV_DEEP = 1 << 6           # ...and seen in the near third of the core-to-core axis
EV_FOE_TURRET = 1 << 7     # at least one enemy turret seen standing
EV_FOE_TURRET2 = 1 << 8    # at least FOE_TURRETS_MANY of them
EV_FOE_ECON = 1 << 9       # at least FOE_HARVESTERS_MANY enemy producers seen standing
EV_BITS = (EV_HURT, EV_ECON_HIT, EV_INTRUDER, EV_DEEP,
           EV_FOE_TURRET, EV_FOE_TURRET2, EV_FOE_ECON)
S_RUSHER = 12         # id+1 of the builder that owns the rush; 0 = unclaimed
S_RUSH_DONE = 13      # 1 once the rusher has built its whole route; 0 while it still needs money
# Packed Gunner tile | facing index << 17. Publishes the firing lane so no economy builder ever
# lays a belt across it -- a friendly in the ray becomes the target and jams the turret for good
# (G11). Offline this came out of the atlas; there is no atlas on an unseen map.
S_RUSH_RAY = 14
S_RUSH_ACTIVE = 15    # 1 once the rusher owns an executable plan and the reserve is worth holding

# Each builder is +20 percentage points of GLOBAL cost scale, permanently -- but a builder that is actively
# completing a chain repays ~2470 titanium, and we were losing to the starter by a deficit of exactly one
# harvester, repeatedly. Scale the count to the work actually available rather than a flat constant.
# Swept with BFS navigation in place (mirrored 30-game sweeps, starter_fixed | luc1):
#   4 -> 19-11 | 4-26     5 -> 22-8 | 7-23     6 -> 23-7 | 8-22     7 -> 27-3 | 5-25
# Six is the pick: seven is stronger against the starter but falls off against the opponent that
# actually resembles the ladder. Before the nav fix this curve was flat and peaked at 4 -- extra
# builders paid their cost scale but could not navigate well enough to deliver.
BUILDERS = 6
# Under sustained fire the cap lifts. A heal restores 4 HP for a flat 1 Ti and is NOT touched by
# the global cost scale, while their Gunner spends 2 Ti to deal 10 damage and averages 5 damage a
# round -- so one extra Builder standing on the Core very nearly cancels one extra turret, and
# their titanium is spent for good while ours keeps the Core alive. Measured: every one of the 30
# losses to `vanguard` is core_destroyed at a median turn of 62, and their five turrets put 76
# hits a game into a 500 HP Core. Losing on a full treasury is the worst way to lose.
SIEGE_BUILDERS = 10
# Core HP below which the alarm is raised. A scratch is not a siege; one stray shot must not
# recall the whole economy.
ALARM_PERCENT = 88
# Titanium the Core keeps back before buying an emergency builder, so a chain in flight still
# completes (G02).
ALARM_RESERVE = 60
# Seeding map memory from the precomputed pool MEASURED WORSE: 17-13 with, 20-10 without, against the
# deterministic starter_fixed. Theory (untested): with the atlas every builder immediately claims the
# globally-nearest-to-Core ore and they walk past each other to distant tiles, whereas vision-discovery
# yields short chains completed early -- and every round of delay costs ~2.5 collected, so early short
# chains dominate late long ones. Left off until ore is ranked by CHAIN LENGTH rather than by distance
# from the builder. The atlas import is still wanted for turret denial and the rush plan.
USE_ATLAS_ORE = False

# Keep enough banked to finish a chain in flight -- a half-built chain delivers exactly zero.
CHAIN_RESERVE = 45
# Titanium the economy must leave unspent until the rush route is finished. Traced against an inert
# opponent, the rusher reached its firing tile on aurora/a at round 39 -- the exact round the plan
# predicts -- and then sat there for SEVENTEEN rounds because five economy builders had ground the
# bank down to 0-16 Ti and it could not afford a 22 Ti Gunner. The match is a race decided in single
# turns, so a turret that cannot be paid for is the most expensive thing on the board. Worth roughly
# 30 turns of kill time across the 30 oriented games; worth +1 win against lockin and 0 elsewhere.
RUSH_RESERVE = 80
# If the rusher dies the store slot never flips, so stop holding the reserve once the race is over.
RUSH_RESERVE_UNTIL = 200
# Budget 3ms locally against the ladder's 10ms. Reads 0 on Windows (G21), where this is advisory only.
CPU_BUDGET_US = 6000

# Replanning the siege costs one full-map BFS plus the geometry search: ~1.3 ms worst case measured
# over both map pools, against a 10 ms budget. It is cheap ONCE, ruinous every round for every unit,
# so it is gated on observation actually having changed. Before anything is built the plan is free
# to move; after the Gunner is up we are committed and only an explicit failure re-opens it.
REPLAN_TILES = 24     # newly observed tiles that make the geometry worth recomputing
REPLAN_ROUNDS = 10    # ...and a floor under it, so a stalled rusher still re-examines the board

# Titanium left in the bank after buying a battery turret. The first Gunner is the one the race
# turns on and the economy holds RUSH_RESERVE for it; the extras are opportunistic, so they only
# ever come out of genuine surplus and never out of a chain in flight.
BATTERY_RESERVE = 40

# Home fortification. A Gunner's ray stops at the first building, so a 3 Ti Barrier on a Core ring
# tile turns a point-blank snipe into a demolition job first: they spend 6 Ti of shooting to clear
# 3 Ti of wall, and we can put it back. That exchange, and nothing else, is why `vanguard`'s Core
# takes 40% of our shots while ours takes 88% of theirs.
#
# It only ever starts once our Core has actually been hit. Twelve Barriers are +12 percentage
# points of permanent global cost scale (G07) and an economy matchup cannot afford that, so against
# an opponent that never shoots the Core this is dead code that costs exactly nothing.
FORTIFY_FROM = 8          # never before the Core has finished spawning onto its own ring
# Ring tiles left unbricked. A conveyor chain SCORES ONLY by terminating on a tile orthogonally
# adjacent to the footprint (G02), and a builder that cannot reach one delivers zero all match --
# so the ring is never closed, only narrowed on the side they come from.
FORTIFY_KEEP_OPEN = 5
# Rounds between battery searches. The route is finished by then, so this is the rusher's only
# remaining cost: one flood plus a handful of ray walks.
BATTERY_EVERY = 3

# --- forward deposits (D5) ---------------------------------------------------
# THROUGHPUT IS BOUNDED BY FEEDERS, NOT BY GUNS. A Harvester delivers 10 Ti every four rounds
# (2.5/round) and round-robins it to every orthogonally adjacent building; a Gunner spends 2 Ti a
# shot and may fire every round. So ONE deposit saturates at ~1.25 shots a round = ~12.5 damage a
# round, and a 500 HP Core needs ~40 rounds of it -- however many turrets are packed around that
# one deposit, because they split the same 2.5 Ti. `battery()` above is bought for ANGLES and
# cannot raise that ceiling; only a SECOND PRODUCER can. Measured over 30 mirrored games against
# `vanguard`, that ceiling is exactly what we were paying: 1.07 Gunners a game and 43.5 shots
# landed on their Core, against their 3.2 Gunners on several deposits and 111.2 landed on ours.
#
# Total forward harvester+Gunner pairs the rusher will open, the first one included. Each extra
# pair is a Gunner and a Harvester of permanent global cost scale (+10 and +5 points -- G07), so
# this is swept, not guessed.
FORWARD_DEPOSITS = 2
# Builders that run the siege instead of the economy. NOT an extra Builder: BUILDERS is unchanged,
# so this buys a second forward deposit for zero cost scale and one economy chain. `vanguard`,
# which fields ~4.9 turrets a game against our ~1.3, runs exactly this split -- 4 Builders, of
# which 2 are attackers, each claiming its own forward deposit.
ATTACKERS = 2
# Titanium left in the bank ON TOP of a deposit's own cost. Zero on purpose, and the number was
# measured rather than chosen: the economy is already holding RUSH_RESERVE (80 Ti) back for
# exactly this purchase while a deposit is pending, and a Gunner plus a Harvester come to ~76 Ti
# once six Builders have driven the global scale to 2.5x. Any positive reserve here is therefore
# DOUBLE-reserving -- it asks for 80 + n Ti out of a bank the economy only ever lets reach 80.
# Measured at 20: the second deposit was planned in 24 of 30 games against `vanguard` and bought
# in 2, with the bank sitting at 86, 96, 102, 112 and 121 Ti against a 96 Ti requirement.
DEPOSIT_RESERVE = 0
# Rounds between attempts to open one. Same cost as a battery search plus one full-map flood.
DEPOSIT_EVERY = 4
# Round after which the rusher gives up on another deposit and hands the economy its reserve
# back. Well past the median turn 62 at which `vanguard` kills us, and well inside the point at
# which a game that is still running is a titanium race rather than a fight.
DEPOSIT_UNTIL = 120
# Consecutive failed searches after which the rusher stops holding out for another deposit and
# spends its surplus on extra angles around the deposits it already has. Not latched: on a map
# whose forward half holds exactly one reachable deposit, hoarding for a second one forever would
# be strictly worse than the battery we already know works.
DEPOSIT_DRY = 2

# --- Launcher relay (G41, measured on a purpose-built arena) -------------------------------
# A Launcher throws an ADJACENT friendly Builder Bot to any bot-passable tile inside r^2 <= 26
# MEASURED FROM THE LAUNCHER -- five tiles on a cardinal. What the probe established:
#   * the bot lands on move_cooldown 0, action_cooldown 0 and FULL hit points, and if its turn
#     falls after the Launcher's in the entity order it moves OR builds on the landing round;
#   * two Launchers six apart throw the same bot twice in ONE round, (5,5)->(11,5)->(17,5);
#   * the throw is not a line of sight. It arcs over a solid seven-tile wall column and over a
#     2x2 Core footprint: the legal set is exactly the Euclidean disc r^2 <= 26 minus whatever
#     is not bot-passable;
#   * a building does not act on the round it is built, so a self-ferry cycle is two rounds.
# So the rusher POLE-VAULTS: round R it builds a Launcher on the tile ahead of it, round R+1 that
# Launcher throws it five tiles past itself. Two rounds for six tiles against two rounds for two,
# at ~28 Ti and +10 points of permanent global cost scale a hop. Nothing else is ever thrown --
# an economy builder thrown at the enemy Core abandons its chain, and an abandoned chain scores
# exactly zero (G02).
VAULT_MAX = 3
# Manhattan gap below which a hop is not worth 28 Ti -- and, just as important, the radius inside
# which no Launcher of ours may be planted: a friendly building anywhere in a Gunner's lane becomes
# its target and jams it for the rest of the match (G11).
VAULT_MIN_GAP = 9
# Titanium the vault leaves behind. The Gunner and its Harvester are the whole point; arriving
# early with nothing to build is the most expensive way to lose the race.
VAULT_FLOOR = 70
# Rounds the rusher will stand still waiting to be thrown before it gives up and walks. The
# Launcher can fail to find a target (everything forward blocked), and a rusher that waits on one
# forever has simply deleted itself.
VAULT_PATIENCE = 3
# Manhattan tiles a hop must actually gain. A throw costs the rusher nothing directly, but a short
# one leaves it inside the same Launcher's pickup radius, which is exactly how the treadmill starts.
VAULT_GAIN = 4

# --- Ammunition (fcode 2.3.x) ------------------------------------------------
# 2.3.x REPLACED per-turret ammo with a TEAM-WIDE POOL. `get_ammo_amount` / `get_ammo_type` are gone;
# `get_global_ammo` / `can_convert_ammo` / `convert_ammo` replace them. Nothing converts implicitly, so
# a bot that never calls convert_ammo has turrets that can never fire -- which is exactly what happened
# to us: ZERO core kills across 42 games on 2.3.3 while every gunner we built sat loaded with nothing.
AMMO_TARGET = 120     # stop converting once the pool holds this much
AMMO_FLOOR = 60       # titanium held back so converting never starves a chain in progress (G02)


# --- Posture ------------------------------------------------------------------
# One enum, owned by the Core, published through the store, read by every unit. Store writes are
# visible next round (G20), so this is a TEN-ROUND-TIMESCALE decision and never a same-round
# tactical one -- which is exactly what it should be. A posture is a claim about the opponent's
# archetype, and archetypes do not change mid-match.
#
# RUSH is the default and RUSH is today's whole behaviour, verbatim. That is deliberate: the
# refactor has to be provably free before any of it is allowed to be clever, so the shipped build
# gives all three rows identical values and the switch is exercised without changing an action.
POSTURE_RUSH = 0
POSTURE_DEFENCE = 1
POSTURE_ECONOMY = 2
POSTURE_NAMES = ("RUSH", "DEFENCE", "ECONOMY")

# Rungs of the builder's priority ladder, as data. The ORDER is a posture parameter; the rungs
# themselves are the same code in every posture, which is the point -- three specialists can
# disagree about what to try first without any of them forking a step.
STEP_OWED = 0
STEP_SABOTAGE = 1
STEP_HOLD = 2
STEP_PHASE = 3
STEP_REPAIR = 4
STEP_SEEK = 5
STEP_HEAL = 6
ORDER_TODAY = (STEP_OWED, STEP_SABOTAGE, STEP_HOLD, STEP_PHASE,
               STEP_REPAIR, STEP_SEEK, STEP_HEAL)

# Evidence weights. EV_HURT is worth double because it is the only bit here with ZERO false
# positives -- see Player._sense.
EV_WEIGHTS = ((EV_HURT, 2), (EV_ECON_HIT, 1), (EV_INTRUDER, 1),
              (EV_DEEP, 2), (EV_FOE_TURRET2, 1))
ALARM_WEIGHT = 3
# Points needed to leave the default at all, and the level it has to fall back below before the
# default is resumed. A Schmitt trigger: the gap is what stops a single flickering bit flapping
# the whole team's economy. In practice evidence is latched, so DEFENCE is a one-way door -- the
# release path exists for a future specialist that fields decaying evidence, not for today.
POSTURE_CONFIDENCE = 3
POSTURE_RELEASE = 1
# Minimum rounds between two CHANGES of posture. The first change is deliberately not gated:
# there is nothing yet to oscillate against, and the one bit worth acting on early is the
# zero-false-positive one. Every change after that waits.
POSTURE_DWELL = 60
POSTURE_FIRST_DWELL = 0
# Round by which a total absence of evidence means the opponent is not contesting the middle at
# all and a greedy economy is simply correct. Late on purpose: silence before this is much more
# likely to mean we have not looked than that there is nothing to see.
ECONOMY_FROM = 150
# Census thresholds, as fractions of what a real opponent fields: `vanguard` runs ~4.9 turrets a
# game against our ~1.3, and an economy bot runs neither.
FOE_TURRETS_MANY = 2
FOE_HARVESTERS_MANY = 3
# Where "our half" ends, as hundredths of the core-to-core axis (0 = our Core, 100 = theirs).
# A fraction rather than a tile count because the pool runs from 8x15 to 30x30.
INTRUDER_HALF = 50
INTRUDER_DEEP = 30

# THE SEAM. Every constant a posture specialist might want to disagree about is looked up here
# instead of read off the module. `None` means "whatever the subsystem's own default is", so a
# row never has to duplicate a number that lives in `siege`.
_BASE_ROW = {
    "builders": BUILDERS,
    "siege_builders": SIEGE_BUILDERS,
    "attackers": ATTACKERS,
    "forward_deposits": FORWARD_DEPOSITS,
    "chain_reserve": CHAIN_RESERVE,
    "alarm_reserve": ALARM_RESERVE,
    "rush_reserve": RUSH_RESERVE,
    "battery_reserve": BATTERY_RESERVE,
    "max_battery": None,            # None -> siege.MAX_BATTERY
    "fortify_from": FORTIFY_FROM,
    "fortify_keep_open": FORTIFY_KEEP_OPEN,
    "hold_on_posture": False,       # come home on the posture, not only on the Core alarm
    "fire_only": None,              # None -> a turret shoots whatever the engine offers it
    "order": ORDER_TODAY,
}

# Filled in by a specialist. Empty here, and that emptiness is the acceptance criterion: with
# nothing in these two dicts the refactored bot must measure identically to the unrefactored one,
# game for game, which is what proves the seams cost nothing.
DEFENCE_OVERRIDES = {}
ECONOMY_OVERRIDES = {}


def _row(over):
    row = dict(_BASE_ROW)
    row.update(over)
    return row


POSTURE_PARAMS = (_row({}), _row(DEFENCE_OVERRIDES), _row(ECONOMY_OVERRIDES))


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
        self.spawn_order = None        # ring tiles ranked by walk to the rusher's first build site

        # Builder
        self.ordinal = None
        self.phase = "seek"            # seek -> harvest -> belt -> seek
        self.target_ore = None
        self.owed = None               # (Position, Direction) belt we must build on a vacated tile
        self.owed_is_final = False
        self.stuck = 0
        self.last_pos = None

        # Shared per-unit knowledge (self persists the whole match -- G20)
        self.core_pos = None
        self.core_tiles = set()
        self.known_ore = set()
        self.known_walls = set()
        self.seen = set()
        self.atlas_done = False
        self.map_name = None
        self.team_tag = "a"
        self.failed_ore = set()

        # Runtime map inference. `terrain` is the tile -> EMPTY/WALL/ORE memory the symmetry
        # refutation reads; `sym_mask` is the set of symmetries this unit has personally ruled out;
        # the pred_* sets are our own half reflected onto the enemy half once one survives.
        self.terrain = {}
        self.sym_mask = None
        self.enemy_anchor = None
        self.enemy_sighted = False
        self.pred_walls = set()
        self.pred_ore = set()
        self.pred_seen = set()
        self.pred_index = None
        self.pred_n = -1
        self.ray_raw = 0

        # Every belt this builder has laid, so it can notice one going missing and put it back.
        self.built_belts = []
        self.repair_target = None

        # Navigation. Buildings block movement and are NOT walls, so they need their own set --
        # and it must be refreshed in BOTH directions, or a destroyed building poisons every
        # future route forever.
        self.known_blocked = set()
        self._nav = None
        self._nav_key = None
        self._nav_n = -1

        # Rush state
        self.rush_role = None          # None = undecided, True = this builder owns the rush
        self.rush_stuck = 0
        self.rush_i = 0
        self.rush_route = None
        self.rush_dist = None
        self.rush_dist_key = None
        self.enemy_core_tiles = set()
        self.occupied = set()
        self.occ_ver = 0
        self.rush_ray = frozenset()
        self.rush_target = None        # enemy anchor the current route was planned against
        self.rush_black = set()        # firing tiles we walked at and could not take
        self.plan_anchor = None        # enemy anchor the last plan ATTEMPT was made against
        self.plan_round = -999
        self.plan_tiles = -1

        # Battery: extra turrets packed around the producer the first one is already fed by.
        self.rush_feeder = None        # deposit the route's Harvester sits on
        self.rush_base_len = 0         # length of the planned route, before any battery step
        self.battery_n = 0
        self.battery_round = -999

        # Forward deposits: every producer feeding a forward turret, and the index at which the
        # most recently appended one starts in the route -- a half-built deposit is truncated back
        # to that, never into the middle of a segment that has already been paid for.
        self.feeders = ()
        self.deposit_n = 0
        self.deposit_round = -999
        self.deposit_dry = 0
        self.rush_seg = 0

        # Launcher relay
        self.vaults = 0
        self.vault_wait = 0
        self.thrown = set()            # ids this Launcher has already ferried -- see _run_launcher

        # Posture. Every unit carries the team posture; only the Core decides it.
        self.posture = POSTURE_RUSH
        self.alarm = False
        self.state = 0                 # the Core's own copy of what it last published
        self.posture_round = 0
        self.switches = 0
        self.score = 0

        # Archetype evidence. Monotone and latched forever -- an archetype does not un-happen.
        self.evidence = 0
        self.core_ev = 0               # evidence only the Core can see (its own hit points)
        self.ev_round = {}             # bit -> round the TEAM first held it (Core only)
        self.foe_turrets = set()       # enemy turret tiles this unit has seen
        self.foe_harvesters = set()    # enemy producer tiles this unit has seen

        self.errors = 0

    # ------------------------------------------------------------------
    # Entry point -- an escaping exception permanently deletes this unit (G23)
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
            elif etype == EntityType.LAUNCHER:
                self._run_launcher(ct)
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
    # Posture -- the switch, the detector, and the seam every subsystem reads
    # ------------------------------------------------------------------

    def _pv(self, key):
        """This posture's value for a tuned parameter. THE seam.

        Every subsystem that used to read a module constant reads this instead: the spawn budget,
        the economy/attacker split, the turret policy, the builder's priority ordering. In the
        shipped build all three rows hold identical values, so the indirection is provably free --
        and the moment a specialist is written, exactly one number moves and nothing else does.
        """
        return POSTURE_PARAMS[self.posture][key]

    def _sync_state(self, ct):
        """Read the Core's published state word. One slot, one writer, everybody reads it.

        The alarm is bit 0 with exactly its old meaning, so `self.alarm` here is bit-for-bit the
        `read_store(S_ALARM) != 1` test it replaces, including on a failed read.
        """
        self.alarm = False
        try:
            raw = ct.read_store(S_STATE)
        except Exception:
            return
        self.alarm = (raw & ALARM_BIT) == ALARM_BIT
        p = (raw >> POSTURE_SHIFT) & 3
        self.posture = p if p < len(POSTURE_PARAMS) else POSTURE_RUSH

    def _sense(self, ct):
        """Fold this round's observations into the latched evidence word.

        EV_HURT is the bit that matters and it has ZERO false positives, which is why it is the
        only one weighted double. A Builder Bot cannot attack any adjacent tile at all -- can_fire
        is False and fire() raises against an adjacent Core, Barrier, Conveyor, Harvester and
        Builder Bot, verified byte-identically on two platforms (G13) -- and the only attack a
        builder has is the range-0 shot at its OWN tile, which damages the building under it and
        nothing else (G14). Our own turrets check the occupant's team before every shot, so no
        friendly fire either. Therefore: one hit point of damage anywhere on our side PROVES the
        enemy has a turret and is feeding it. Nothing else in this detector is that clean, and it
        is latched forever the moment it fires.

        The other bits are TELLS, not proofs, and are priced accordingly.
        """
        try:
            self.evidence = self.evidence | (ct.read_store(S_FLAGS) & EV_MASK)
        except Exception:
            pass
        if not (self.evidence & EV_HURT):
            try:
                if ct.get_hp() < ct.get_max_hp():
                    self.evidence = self.evidence | EV_HURT
            except Exception:
                pass
        n = len(self.foe_turrets)
        if n >= 1:
            self.evidence = self.evidence | EV_FOE_TURRET
        if n >= FOE_TURRETS_MANY:
            self.evidence = self.evidence | EV_FOE_TURRET2
        if len(self.foe_harvesters) >= FOE_HARVESTERS_MANY:
            self.evidence = self.evidence | EV_FOE_ECON

    def _scan_intruder(self, ct, tile, key):
        """Latch how deep into OUR half an enemy Builder Bot has been seen.

        Measured as a fraction of the core-to-core axis (0 = our Core, 100 = theirs), because a
        tile count means nothing across a pool that runs from 8x15 to 30x30. The axis comes free:
        `siege` already infers the enemy Core anchor from symmetry and every builder already
        holds it.

        A tell, not a proof -- an economy bot's builder can wander -- so it is worth one point,
        and only the near third is worth two.
        """
        bid = self._bot_at(ct, tile)
        if bid is None or not self._is_enemy(ct, bid):
            return
        ax = self.enemy_anchor[0] - self.core_pos.x
        ay = self.enemy_anchor[1] - self.core_pos.y
        norm = ax * ax + ay * ay
        if norm <= 0:
            return
        f = ((key[0] - self.core_pos.x) * ax + (key[1] - self.core_pos.y) * ay) * 100 // norm
        if f <= INTRUDER_HALF:
            self.evidence = self.evidence | EV_INTRUDER
        if f <= INTRUDER_DEEP:
            self.evidence = self.evidence | EV_DEEP

    def _arbitrate(self, ct, rnd):
        """Decide the team posture. Core only.

        A ratchet with a Schmitt trigger on top, not a controller: the evidence it reads is
        monotone, so this can only climb until something releases it, and the release exists for a
        future specialist rather than for today.

        BE HONEST ABOUT THE CLOCK. A posture decided at round R is published at R+1, read by a
        builder at R+2, and whatever it buys is standing perhaps twenty rounds after that. So the
        postures may differ in SCALE and must never differ in EXISTENCE: the minimum viable
        version of every subsystem is built unconditionally, and the posture only ever says how
        much more of it to buy. A defence that only exists once the detector has fired is a
        defence that arrives after the Core has.
        """
        try:
            self.evidence = self.evidence | (ct.read_store(S_FLAGS) & EV_MASK)
        except Exception:
            pass
        self.evidence = self.evidence | self.core_ev
        for bit in EV_BITS:
            if (self.evidence & bit) and bit not in self.ev_round:
                self.ev_round[bit] = rnd

        score = 0
        for bit, weight in EV_WEIGHTS:
            if self.evidence & bit:
                score += weight
        if self.alarm:
            score += ALARM_WEIGHT
        self.score = score

        want = self.posture
        if score >= POSTURE_CONFIDENCE:
            want = POSTURE_DEFENCE
        elif rnd >= ECONOMY_FROM and self.evidence == 0:
            # Nobody has touched us, nobody has been seen, nothing of ours has been shot. The
            # only remaining question is who banks more, and that is a tiebreak we win by
            # building chains rather than turrets (G01/G03).
            want = POSTURE_ECONOMY
        elif score <= POSTURE_RELEASE:
            want = POSTURE_RUSH
        if want == self.posture:
            return self.posture
        dwell = POSTURE_DWELL if self.switches else POSTURE_FIRST_DWELL
        if rnd - self.posture_round < dwell:
            return self.posture
        self.posture = want
        self.posture_round = rnd
        self.switches += 1
        return self.posture

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def _run_core(self, ct):
        pos = ct.get_position()
        self.core_pos = pos
        ct.write_store(S_CORE_X, pos.x)
        ct.write_store(S_CORE_Y, pos.y)
        self._top_up_ammo(ct)

        # The Core is the one unit that can read its own hit points, so it is the one unit that
        # can tell the team the base is being ground down. Once raised the alarm stays raised: an
        # opponent that has walked a turret up to our footprint is not going to change its mind,
        # and a flapping alarm would send the economy back and forth doing neither job.
        hurt = False
        try:
            hp, mx = ct.get_hp(), ct.get_max_hp()
            # ANY damage at all on the Core proves a fed enemy turret exists, tens of rounds
            # before the 88% alarm below is willing to say so. Same argument as _sense: a Builder
            # Bot cannot attack an adjacent tile (G13) and our own turrets never fire on our own
            # team, so nothing else on the board can have done it.
            if hp < mx:
                self.core_ev = self.core_ev | EV_HURT
            hurt = hp * 100 < mx * ALARM_PERCENT
            if hurt or (self.state & ALARM_BIT):
                hurt = True
        except Exception:
            hurt = False
        if hurt:
            self.alarm = True

        # Arbitrate, then publish. The Core is the only writer of this slot, so the value it
        # reads back next round is the value it wrote -- which is why the alarm latch above can
        # be read out of `self.state` instead of out of the store.
        rnd = 0
        try:
            rnd = ct.get_current_round()
        except Exception:
            rnd = 0
        self._arbitrate(ct, rnd)
        self.state = (ALARM_BIT if self.alarm else 0) | (self.posture << POSTURE_SHIFT)
        try:
            ct.write_store(S_STATE, self.state)
        except Exception:
            pass

        cap = self._pv("builders")
        reserve = self._pv("chain_reserve")
        if hurt:
            cap = self._pv("siege_builders")
            reserve = self._pv("alarm_reserve")
        if self.spawned >= cap or not self._can_act(ct):
            return
        try:
            balance = ct.get_global_resources()
            cost = ct.get_builder_bot_cost()
        except Exception:
            return
        # Finishing a chain in flight always beats starting another builder (G02).
        if balance < cost + reserve:
            return
        for target in self._spawn_tiles(ct, pos):
            try:
                if ct.can_spawn(target):
                    ct.spawn_builder(target)
                    self.spawned += 1
                    ct.write_store(S_SPAWN_ORD, ct.read_store(S_SPAWN_ORD) + 1)
                    return
            except Exception:
                continue

    def _top_up_ammo(self, ct):
        """Turn banked titanium into team ammunition.

        Kept on the Core because it acts first every round, so the pool is filled before any turret
        takes its turn. Wrapped so a pre-2.3 engine (where these methods do not exist) degrades
        silently rather than deleting the Core with an uncaught exception (G23).
        """
        try:
            held = ct.get_global_ammo()
            if held >= AMMO_TARGET:
                return
            amount = min(AMMO_TARGET - held, ct.get_global_resources() - AMMO_FLOOR)
            if amount > 0 and ct.can_convert_ammo(amount):
                ct.convert_ammo(amount)
        except Exception:
            return

    def _spawn_tiles(self, ct, pos):
        """Candidate spawn tiles, best first.

        The FIRST builder spawned is always the rusher: the claim-then-confirm in `_is_rusher` can
        only ever resolve to it, because a builder does not act on the round it is spawned (G31),
        so builder 1 is alone on the board the round it finds the claim slot empty. Give that one
        builder the ring tile with the shortest walk to its first build site; every later builder
        keeps the legacy order, so the economy is untouched.
        """
        if self.spawned < self._pv("attackers"):
            order = self._rush_spawn_order(ct, pos)
            if order:
                return order
        return tuple(pos.add(d) for d in ALL_DIRS)

    def _rush_spawn_order(self, ct, pos):
        """The 12 legal ring tiles, ranked toward wherever the enemy Core can be.

        The old code iterated ALL_DIRS off `pos`, and `pos` is the TOP-LEFT anchor of the 2x2
        footprint (G33) -- so EAST, SOUTHEAST and SOUTH land ON the Core and `can_spawn` is False.
        Only NORTH, NORTHEAST, SOUTHWEST, WEST and NORTHWEST were ever reachable: five of the
        twelve legal ring tiles, every one of them on the north/west face of the Core. The enemy
        lies north-west of us on half the pool and south-east on the other half, so that fixed
        bias started the rusher on the wrong side of its own Core and made it walk around the
        footprint. Recomputed offline over all 30 oriented games: 685 tiles walked to the first
        build site against 598 for the best ring tile -- 87 wasted tiles, every one a turn.

        The ranking used to come out of the precomputed route, which is exactly the dependency
        being removed. The Core cannot infer the symmetry -- it never moves, so it never observes
        the terrain that would refute one -- but it does not have to: it aims at the CENTROID of
        the surviving candidates, which on every legal map lies on the enemy side of our own Core.
        That recovers the wasted tiles on any map at all, instead of only on the fifteen.
        """
        if self.spawn_order is not None:
            return self.spawn_order
        self.spawn_order = ()
        if siege is None:
            return self.spawn_order
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
            anchor = (pos.x, pos.y)
            live = siege.alive(w, h, anchor, siege.seed_mask(w, h, anchor))
            if not live:
                return self.spawn_order
            gx = sum(c[0] for c in live) / float(len(live))
            gy = sum(c[1] for c in live) / float(len(live))
            core = set(siege.footprint(anchor))
            ring = []
            for x in range(pos.x - 1, pos.x + 3):
                for y in range(pos.y - 1, pos.y + 3):
                    if (x, y) in core or not (0 <= x < w and 0 <= y < h):
                        continue
                    ring.append(((x - gx) ** 2 + (y - gy) ** 2, x, y))
            ring.sort()
            self.spawn_order = tuple(Position(t[1], t[2]) for t in ring)
        except Exception:
            self.spawn_order = ()
        return self.spawn_order

    def _builder_target(self, ct):
        """One builder per ore tile we could still chain, clamped -- never a flat constant.

        Each builder is +20 percentage points of permanent global cost scale, so an idle one is pure tax;
        but each builder that completes a chain returns ~2470 collected. The binding resource is ore, so
        size the workforce to the ore actually available on our half of the map.
        """
        ore_count = None
        if atlas is not None:
            try:
                tag = "a" if ct.get_team() == Team.A else "b"
                rec = atlas.identify(ct.get_map_width(), ct.get_map_height(),
                                     (self.core_pos.x, self.core_pos.y), tag)
                if rec is not None:
                    own = rec["own_core"]
                    ore_count = sum(
                        1 for o in rec["ore"]
                        if (o[0] - own[0]) ** 2 + (o[1] - own[1]) ** 2
                        <= (o[0] - rec["enemy_core"][0]) ** 2 + (o[1] - rec["enemy_core"][1]) ** 2
                    )
            except Exception:
                ore_count = None
        if ore_count is None:
            return MIN_BUILDERS + 1
        target = (ore_count + 1) // 2
        if target < MIN_BUILDERS:
            return MIN_BUILDERS
        if target > MAX_BUILDERS:
            return MAX_BUILDERS
        return target

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
        self._load_atlas(ct)

        self._sync_state(ct)
        self._observe(ct, pos)
        self._sense(ct)
        self._infer_enemy_core(ct)
        self._read_ray(ct)

        if self.last_pos is not None and self.last_pos == pos:
            self.stuck += 1
        else:
            self.stuck = 0
        self.last_pos = pos

        # 0. The rusher runs a precomputed kill instead of an economy. On 13 of the 15 pool maps a
        #    Gunner firing position exists with an ore tile orthogonally adjacent, so the harvester
        #    feeds it directly with ZERO conveyors -- a Core kill around turn 60-80 for well under
        #    100 Ti. Rival bots kill us around round 150-300, so executing this wins the race.
        if self._is_rusher(ct) and self._run_rush(ct, pos):
            return

        # 1-7. The priority ladder, in the order THIS POSTURE wants it. `ORDER_TODAY` is the
        #      ladder that used to be written out inline here, rung for rung and in the same
        #      order, and it is what all three postures currently use. Making the order data is
        #      the second seam: a DEFENCE specialist that wants healing ahead of prospecting, or
        #      an ECONOMY one that never bricks, changes a tuple instead of this function.
        for step in self._pv("order"):
            if self._step(ct, pos, step):
                return
        # 8. Otherwise walk.
        self._walk(ct, pos)

    def _step(self, ct, pos, step):
        """One rung of the builder's priority ladder. True if the round was spent.

        Every rung is the code that used to sit inline in `_run_builder`, moved verbatim.
        """
        if step == STEP_OWED:
            # Settle the belt we owe. Highest-value action in the game: nothing scores until the
            # chain reaches the Core, so finishing always outranks starting (G02).
            return self._settle_owed(ct, pos)
        if step == STEP_SABOTAGE:
            # Range-0 sabotage -- the only attack a builder has (G14). Cuts every harvester
            # upstream.
            return self._sabotage(ct, pos)
        if step == STEP_HOLD:
            # The base is under fire. Titanium only scores while there is a Core footprint for the
            # stacks to land on (G01), so once the Core is being ground down, holding it outranks
            # mining into it. Never interrupts a chain in flight -- an abandoned chain scores zero
            # (G02) -- so a builder finishes what it started first.
            return self._hold_home(ct, pos)
        if step == STEP_PHASE:
            if self.phase == "harvest" and self._try_harvester(ct, pos):
                return True
            if self.phase == "belt" and self._belt_step(ct, pos):
                return True
            return False
        if step == STEP_REPAIR:
            # A cut belt makes the ENTIRE chain upstream of it score zero (G02), and an enemy
            # builder can destroy a 20 HP conveyor for 20 Ti using the range-0 attack. Repairing
            # one link costs ~3 Ti and restores ~2.5 collected per round, so it outranks starting
            # anything new.
            if self.phase == "seek":
                return self._repair_chain(ct, pos)
            return False
        if step == STEP_SEEK:
            if self.phase == "seek":
                self._seek(ct, pos)
                if self.phase == "harvest" and self._try_harvester(ct, pos):
                    return True
            return False
        if step == STEP_HEAL:
            # Repair anything friendly and damaged beside us.
            return self._heal(ct, pos)
        return False

    def _load_atlas(self, ct):
        """Pure accelerator: seed the enemy Core and the static wall set when the map is known.

        Nothing downstream depends on this. The runtime planner is the default path and runs on
        every map, recognised or not -- the atlas only lets it skip the inference on the fifteen
        published ones. A bot that DEPENDS on its atlas plays an unseen map with the whole attack
        silently switched off, which is precisely the failure being removed.
        """
        if self.atlas_done or atlas is None or self.core_pos is None:
            return
        self.atlas_done = True
        try:
            # Our real team, not a guess. Asking for the wrong team returns a record oriented to the
            # OPPONENT, so own_core_tiles would be the enemy's Core and every chain would terminate
            # on the wrong tiles -- scoring zero.
            tag = "a" if ct.get_team() == Team.A else "b"
            rec = atlas.identify(ct.get_map_width(), ct.get_map_height(),
                                 (self.core_pos.x, self.core_pos.y), tag)
            if rec is None:
                return
            self.map_name = rec["name"]
            self.team_tag = tag
            self.core_tiles.update(tuple(t) for t in rec["own_core_tiles"])
            # Walls are ALWAYS wanted: the rush BFS needs the full static wall set, and the greedy
            # stepper 2-cycles forever without it.
            self.known_walls.update(tuple(w) for w in rec["walls"])
            self.enemy_core_tiles = set(tuple(t) for t in rec["enemy_core_tiles"])
            self.enemy_anchor = tuple(rec["enemy_core"])
            self.enemy_sighted = True
            if not USE_ATLAS_ORE:
                return
            # Only OUR half. Seeding every ore tile sends builders across the map to ore they would
            # never have discovered, and a long chain costs far more than it returns.
            own, foe = rec["own_core"], rec["enemy_core"]
            for o in rec["ore"]:
                d_own = (o[0] - own[0]) ** 2 + (o[1] - own[1]) ** 2
                d_foe = (o[0] - foe[0]) ** 2 + (o[1] - foe[1]) ** 2
                if d_own <= d_foe:
                    self.known_ore.add(tuple(o))
            self.known_walls.update(tuple(w) for w in rec["walls"])
        except Exception:
            return

    # --- the rush ------------------------------------------------------

    def _is_rusher(self, ct):
        """The first ATTACKERS builders run the kill; everyone else keeps building economy.

        A second attacker rather than a second trip. One rusher opening two forward deposits does
        it SERIALLY: measured, the first battery is up at median round 14, the second is planned
        around round 25-40, and by the time the same builder has walked back across the map and
        paid for both halves the game is usually over -- the deposit was bought in 21 of 30 games
        against `vanguard` and only 5 of them ever had two producers standing. Two attackers open
        two deposits in PARALLEL, off the same round-14 tempo.

        It costs no cost scale at all, which is the point: BUILDERS is unchanged, so this is a
        role reassignment, not a purchase. What it costs is one economy chain -- about 2470
        collected over a full match (G04) -- which is the entire trade, and why it is measured on
        `jonbot` (an economy opponent) as carefully as on `vanguard`.

        Claimed through the store rather than by spawn ordinal. A builder does not act on the round it
        is spawned, so by its first turn the Core has already incremented the ordinal counter and NO
        builder ever reads 0 -- gating on `ordinal == 0` silently disabled the whole rush.
        Claim-then-confirm: write our id, and next round the single writer that sees its own id wins.

        Nothing about this is gated on the map being recognised any more. It used to be, and the
        cost of that was total: on an unrecognised map `atlas.identify()` returned None, the name
        never matched the hard-coded list, `_is_rusher` answered False for every builder, and the
        offence did not exist -- zero core kills across every unseen map measured.
        """
        if siege is None or self.core_pos is None:
            return False
        if self.rush_role is None:
            try:
                mine = ct.get_id() + 1
                claim = ct.read_store(S_RUSHER)
                if claim == 0:
                    ct.write_store(S_RUSHER, mine)
                    return False
                if claim == mine:
                    self.rush_role = True
                elif self._pv("attackers") < 2:
                    self.rush_role = False
                else:
                    # Seat two is claimed the same way, one round later. Two builders can write
                    # it in the same round -- writes are only visible next round (G20) -- so the
                    # confirm still admits exactly one, and the loser falls back to the economy.
                    second = ct.read_store(S_RUSHER2)
                    if second == 0:
                        ct.write_store(S_RUSHER2, mine)
                        return False
                    self.rush_role = (second == mine)
            except Exception:
                self.rush_role = False
        return self.rush_role is True

    def _run_rush(self, ct, pos):
        """Execute the runtime build route in order, walking with a wall-aware BFS.

        The route is (kind, tile, facing, _) triples in build order -- gunner, then any belt from
        the turret end back, then the harvester that feeds it. Identical execution to the table
        version; only its source changed. Three measured failures it already handles:
          1. The old greedy `_step_toward` has no wall avoidance -- `Direction.rotate_left()` returns a
             DIAGONAL, which the CARDINALS filter then discards, so its sidestep branch was dead code
             and the walk degenerated to "first passable of N,E,S,W". That 2-cycles forever in any
             concave corner: measured on atoll/a, atoll/b, fjord/a, fjord/b, pinch/a, vault/a, vault/b.
             `rush_stuck` stayed 0 in all seven, so the 12-round give-up never fired either.
          2. Building only the gunner and the harvester. On quarry and runestone the plan needs 1-2
             CONVEYORS between them, so the gunner sat on ammo=0 for the whole match with the enemy
             Core in its sights.
          3. Parking in the finished turret's own firing lane, which jams it permanently (G11). The
             offline table dodged that by choosing the final stand; a BFS that walks to ANY adjacent
             tile does not, so the rusher now steps out of the ray the moment the route is done.
        """
        try:
            # Claim the economy's reserve the moment a rusher exists, not when its plan firms up.
            # The race is decided in single turns and a Gunner that cannot be paid for is the most
            # expensive thing on the board; waiting for the geometry to resolve on a big map means
            # five economy builders have already spent the bank by the time it does.
            if ct.read_store(S_RUSH_DONE) != 1:
                ct.write_store(S_RUSH_ACTIVE, 1)
        except Exception:
            pass
        self._plan_rush(ct, pos)
        route = self.rush_route
        if route is None:
            return self._rush_approach(ct, pos)

        if self.rush_i >= len(route):
            # Throughput first, angles second. Another PRODUCER raises the ceiling on delivered
            # damage; another turret on a producer we already have only splits its 2.5 Ti/round.
            # The battery therefore waits until no further deposit can be opened, so its 12 Ti
            # never gets spent out from under a 30 Ti deposit we were seven rounds from affording.
            pending = self._extend_deposit(ct, pos)
            try:
                # Release the economy's titanium reserve -- but not while a second deposit is
                # still coming, because that reserve is the only thing that ever pays for it.
                if not self._deposit_pending(ct):
                    ct.write_store(S_RUSH_DONE, 1)
            except Exception:
                pass
            if pending:
                route = self.rush_route             # a whole new battery to build -- fall through
            elif (not self._deposit_pending(ct)) and self._extend_battery(ct, pos):
                route = self.rush_route             # a new turret to build -- fall through
            else:
                if (pos.x, pos.y) in self.rush_ray and self._clear_ray(ct, pos):
                    return True
                if self._heal(ct, pos):
                    return True
                return True

        kind, bxy, facing, _stand = route[self.rush_i]
        bpos = Position(bxy[0], bxy[1])

        # Already occupied -- by our own earlier step, or by somebody who got there first.
        occupant = self._building_at(ct, bpos)
        if occupant is not None:
            if self.rush_i == 0 and not self._is_our_gunner(ct, occupant):
                # The firing tile is taken by something that is not our turret: an enemy squatting
                # it, or one of our own belts wandering into it. Advancing would leave us building
                # a harvester to feed a Gunner that does not exist -- give the tile up and
                # re-derive. Walking at it forever is how a siege spends 900 rounds on nothing.
                self.rush_black.add(bxy)
                self._drop_plan()
                return True
            if kind == "harvester" and not self._feeds_us(ct, bxy, occupant):
                # Their producer on the deposit that was going to feed our turret, and not close
                # enough to ours to feed it by accident. Stepping past it -- what this used to do
                # -- leaves a Gunner that fires exactly zero times: measured on twins/a, the
                # turret went up on round 28, the deposit was already vanguard's, and it sat
                # unfed beside a full magazine of nothing until our Core fell on round 45.
                self._abort_segment(bxy)
                return True
            self.rush_i += 1
            self.rush_dist = None
            return True

        # A Builder Bot's action radius is r^2 <= 2, which INCLUDES the four diagonals -- probed
        # live: `can_build_barrier` is True at d2=1 and d2=2, False at 4 and 5, and the diagonal
        # build actually lands. The executor gated every build on d2 == 1 and so threw away half
        # the ring it could have built from. Measured cost on crossfire/a: the rusher finished a
        # belt at (8,6), needed (8,7) next, and walked TWENTY-FIVE rounds around a wall block to
        # reach a cardinal neighbour of it.
        if pos.distance_squared(bpos) <= 2:
            if not self._can_act(ct):
                return True
            ok = False
            try:
                if kind == "gunner":
                    d = DIR_BY_NAME.get(facing)
                    if d is not None and ct.can_build_gunner(bpos, d):
                        ct.build_gunner(bpos, d)
                        ok = True
                elif kind == "conveyor":
                    d = DIR_BY_NAME.get(facing)
                    if d is not None and ct.can_build_conveyor(bpos, d):
                        ct.build_conveyor(bpos, d)
                        ok = True
                elif kind == "harvester":
                    if ct.can_build_harvester(bpos):
                        ct.build_harvester(bpos)
                        ok = True
            except Exception:
                ok = False
            if ok:
                self.rush_i += 1
                self.rush_dist = None
                self.rush_stuck = 0
            return True

        # Still in transit to the firing tile: a Launcher hop buys six tiles for two rounds.
        # Only before anything has been paid for -- once the turret is up we are committed and a
        # 28 Ti hop toward a position we already occupy is pure loss.
        if self.rush_i == 0 and self._vault(ct, pos, bxy):
            return True
        return self._rush_walk(ct, pos, bpos)

    def _is_our_gunner(self, ct, entity_id):
        if entity_id is None:
            return False
        try:
            return (ct.get_entity_type(entity_id) == EntityType.GUNNER
                    and ct.get_team(entity_id) == ct.get_team())
        except Exception:
            return False

    def _feeds_us(self, ct, tile, entity_id):
        """Does the building already on our deposit still supply the turret we built?

        Ours does, obviously. So does THEIRS: a Harvester round-robins its stacks into every
        orthogonally adjacent building regardless of team, so an enemy Harvester on the tile we
        wanted is free ammunition rather than a lost plan -- provided our Gunner is actually
        beside it. Anything else (a Barrier, a belt, a turret) delivers nothing and the plan is
        dead.

        Checked against EVERY turret in the route, not just the route's first: with more than one
        forward deposit the Harvester at step k feeds the Gunner that opened ITS segment, and
        measuring adjacency to the first battery's Gunner would reject a perfectly good second one.
        """
        if entity_id is None:
            return False
        try:
            if ct.get_team(entity_id) == ct.get_team():
                return True
            if ct.get_entity_type(entity_id) != EntityType.HARVESTER:
                return False
        except Exception:
            return False
        if not self.rush_route:
            return False
        for step in self.rush_route:
            if step[0] != "gunner":
                continue
            g = step[1]
            if abs(g[0] - tile[0]) + abs(g[1] - tile[1]) == 1:
                return True
        return False

    def _abort_segment(self, bxy):
        """Give up on the appended segment we are standing in, keeping the siege already paid for.

        Only the FIRST battery is load-bearing: dropping the whole plan because an optional second
        deposit turned out to be occupied would trade a turret that is firing for one that is not.
        Anything appended is truncated back to the index the segment started at and the producer
        list is re-derived from what survives, so nothing downstream can be left pointing at a
        deposit the route no longer contains.
        """
        self.rush_black.add(bxy)
        if self.rush_route and self.rush_base_len and self.rush_seg >= self.rush_base_len > 0:
            self.rush_route = tuple(self.rush_route)[:self.rush_seg]
            if self.rush_i > self.rush_seg:
                self.rush_i = self.rush_seg
            self.feeders = tuple(s[1] for s in self.rush_route if s[0] == "harvester")
            self.deposit_n = len(self.feeders)
            self.rush_dist = None
            return
        self._drop_plan()

    def _deposit_pending(self, ct):
        """Is the rusher still trying to open another forward deposit?

        This is also what decides whether the economy keeps holding RUSH_RESERVE. The reserve is
        the whole funding model: a Gunner and a Harvester cost ~73 Ti together once six Builders
        have driven the global scale to ~2.5x (G07), and measured over 30 games the bank after the
        first battery went up sat between 1 and 55 Ti in every game we lost -- so without a
        reserve the second deposit is not merely late, it never happens at all.

        Bounded three ways, because a reserve nobody spends is pure loss and this is exactly the
        trade a previous variant lost six games to `jonbot` on: the deposit count, two consecutive
        failed searches, and a hard round cap well past the median turn (62) at which `vanguard`
        kills us. After any of the three the store is told the rush is done and the economy buys
        chains again.
        """
        if self.deposit_n >= self._pv("forward_deposits") or self.deposit_dry >= DEPOSIT_DRY:
            return False
        try:
            return ct.get_current_round() <= DEPOSIT_UNTIL
        except Exception:
            return False

    def _live_feeders(self, ct):
        """The forward producers that are still standing.

        A producer shot off its deposit feeds nothing, and a turret beside a hole in the ground is
        12 Ti of permanent cost scale for zero damage. A tile we cannot currently see is assumed
        intact -- occupancy memory only clears in vision, and refusing to spend while the rusher
        is walking somewhere else would stall the whole extension.
        """
        out = []
        for f in self.feeders:
            tile = Position(f[0], f[1])
            if self._building_at(ct, tile) is not None:
                out.append(f)
                continue
            try:
                if not ct.is_in_vision(tile):
                    out.append(f)
            except Exception:
                continue
        return out

    def _extend_deposit(self, ct, pos):
        """Open ANOTHER forward deposit -- a second Harvester, on a second ore tile, with its own
        Gunner.

        This is the only lever that raises delivered damage per round. One producer puts out
        2.5 Ti a round and a Gunner burns 2 a shot, so a single deposit is capped at ~12.5 damage
        a round and a 500 HP Core takes ~40 rounds of it. `_extend_battery` cannot lift that cap
        -- turrets sharing one producer split its output -- it buys firing angles against a
        Barrier. Two producers is two caps: measured against `vanguard`, we delivered 43.5 shots
        onto their Core a game against the 111.2 they delivered onto ours, on 1.07 turrets against
        3.2. Their advantage is arithmetic, not aim.

        Sited by the same planner that found the first battery, with three differences:
          * every deposit we already own is blacklisted, so the two never share a producer -- two
            turrets on one Harvester is the `battery()` case, not this one;
          * every lane we already own is excluded from the turret tile, the belt and the deposit.
            A building of ours in a friendly Gunner's ray becomes its target and jams it for the
            rest of the match (G11); a second battery built across the first one's lane does not
            add throughput, it deletes throughput. This is the single easiest way to make the
            change actively harmful, so it is enforced in the planner rather than checked after;
          * the buildings we have already paid for are in `buildings`, so they are `stoppers` --
            the new ray can no more shoot through our own turret than through a wall.
        """
        if siege is None or self.enemy_anchor is None or not self.rush_route:
            return False
        if not self._deposit_pending(ct):
            return False
        try:
            rnd = ct.get_current_round()
        except Exception:
            return False
        if rnd - self.deposit_round < DEPOSIT_EVERY:
            return False
        self.deposit_round = rnd
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return False
        if not self._cpu_left(ct):
            return False
        walls = self.known_walls | self.pred_walls
        ore = (self.known_ore | self.pred_ore) - self.known_walls
        foot = set(siege.footprint(self.enemy_anchor))
        blocked = walls | self.core_tiles | foot | self.enemy_core_tiles
        buildings = (self.occupied - self.core_tiles) - self.enemy_core_tiles - foot
        dist = self._flood(ct, (pos.x, pos.y), blocked | (buildings - {(pos.x, pos.y)}), w, h)
        known = (self.seen | self.pred_seen) or None
        black = set(self.rush_black) | set(self.feeders)
        try:
            found = siege.plan(w, h, self.enemy_anchor, self.core_tiles, walls, ore, buildings,
                               dist, blacklist=black, known=known, lanes=self.rush_ray)
            if found is None:
                # Second pass with buildings ignored, exactly as the first plan does. Occupancy
                # memory never expires while a tile is out of vision, and by the time the first
                # battery is up the ring around the enemy Core is the most heavily remembered
                # ground on the board -- `vanguard` bricks it. A remembered Barrier is a reason to
                # prefer another tile, never a reason to have no plan: the executor re-checks
                # legality on arrival, and a Barrier is 30 HP against a Gunner's 10 a shot.
                found = siege.plan(w, h, self.enemy_anchor, self.core_tiles, walls, ore,
                                   frozenset(), self._flood(ct, (pos.x, pos.y), blocked, w, h),
                                   blacklist=black, known=known, lanes=self.rush_ray)
        except Exception:
            found = None
        if found is None:
            # Nowhere left to put one. Counted, not latched: the search is cheap and the map is
            # still being discovered, so two consecutive failures -- eight rounds -- is the point
            # at which the rusher stops holding the economy's titanium for a battery that does
            # not exist and lets it buy chains again.
            self.deposit_dry += 1
            return False
        self.deposit_dry = 0
        # The plan exists; only the money is missing. Say nothing to the store yet -- the economy
        # goes on holding RUSH_RESERVE, which is the ONLY way this ever gets paid for. Measured
        # without it: the bank sat at 1-55 Ti for the whole of every game we lost, against the
        # ~73 Ti a Gunner and a Harvester cost by then, and the second deposit was opened in
        # 2 games out of 30.
        try:
            if (ct.get_global_resources()
                    < ct.get_gunner_cost() + ct.get_harvester_cost() + DEPOSIT_RESERVE):
                return False
        except Exception:
            return False
        add = [("gunner", found["gunner"], found["facing"], None)]
        for tile, facing in found["conveyors"]:
            add.append(("conveyor", tile, facing, None))
        add.append(("harvester", found["ore"], None, None))
        self.rush_seg = len(self.rush_route)
        self.rush_route = tuple(self.rush_route) + tuple(add)
        self.rush_ray = frozenset(self.rush_ray) | found["ray"]
        self.feeders = tuple(self.feeders) + (found["ore"],)
        self.deposit_n += 1
        # Each producer gets its own angle budget: MAX_BATTERY is a cap per deposit, because that
        # is the unit the sharing argument applies to.
        self.battery_n = 0
        self.battery_round = rnd
        self.rush_dist = None
        return True

    def _extend_battery(self, ct, pos):
        """Pack another Gunner around a producer we already own.

        The route is finished and the rusher is otherwise idle for the rest of the match, so this
        is the cheapest firepower on the board: a turret, no belt, no second walk. Only ever built
        out of surplus, never out of the reserve the first Gunner depends on. It buys ANGLES, not
        throughput -- see `_extend_deposit`, which runs first for exactly that reason.
        """
        if siege is None or self.enemy_anchor is None:
            return False
        # `None` in the row means "whatever siege thinks", so the table never duplicates a
        # constant that already has a home.
        cap = self._pv("max_battery")
        if cap is None:
            cap = siege.MAX_BATTERY
        if self.battery_n >= cap:
            return False
        try:
            rnd = ct.get_current_round()
        except Exception:
            return False
        if rnd - self.battery_round < BATTERY_EVERY:
            return False
        self.battery_round = rnd
        feeders = self._live_feeders(ct)
        if not feeders:
            return False
        try:
            if ct.get_global_resources() < ct.get_gunner_cost() + self._pv("battery_reserve"):
                return False
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return False
        if not self._cpu_left(ct):
            return False
        walls = self.known_walls | self.pred_walls
        ore = (self.known_ore | self.pred_ore) - self.known_walls
        foot = set(siege.footprint(self.enemy_anchor))
        blocked = walls | self.core_tiles | foot | self.enemy_core_tiles
        buildings = (self.occupied - self.core_tiles) - self.enemy_core_tiles - foot
        dist = self._flood(ct, (pos.x, pos.y), blocked | (buildings - {(pos.x, pos.y)}), w, h)
        known = (self.seen | self.pred_seen) or None
        try:
            sites = siege.battery(w, h, self.enemy_anchor, feeders, self.core_tiles,
                                  walls, ore, buildings, self.rush_ray, dist,
                                  known=known, blacklist=self.rush_black)
            if not sites:
                # An ENEMY Barrier in the lane is a TARGET, not a wall. It has 30 HP against a
                # Gunner's 10 a shot, so three shots open the lane and the turret then bears on
                # the Core for the rest of the match -- treating it as permanent throws the
                # position away for good. Measured: over 30 mirrored games against `vanguard`,
                # which bricks its Core ring, this search returned a site ZERO times out of 1129
                # calls, and MAX_BATTERY = 0 against MAX_BATTERY = 3 produced bit-identical
                # results on all 30. Verified in isolation that the function itself is sound: on
                # a clean board it proposes the expected tile, and it returns nothing the moment
                # the ring is bricked.
                sites = siege.battery(w, h, self.enemy_anchor, feeders, self.core_tiles,
                                      walls, ore, frozenset(), self.rush_ray,
                                      self._flood(ct, (pos.x, pos.y), blocked, w, h),
                                      known=known, blacklist=self.rush_black)
        except Exception:
            return False
        if not sites:
            return False
        best = sites[0]
        self.rush_seg = len(self.rush_route)
        self.rush_route = tuple(self.rush_route) + (
            ("gunner", best["gunner"], best["facing"], None),)
        # Reserve the new lane too, so neither the next turret nor the rusher's own body ever
        # ends up standing in it (G11).
        self.rush_ray = frozenset(self.rush_ray) | best["ray"]
        self.battery_n += 1
        self.rush_dist = None
        return True

    # --- launcher relay ------------------------------------------------

    def _vault(self, ct, pos, goal):
        """Spend the round buying six tiles instead of walking one. True if the round was spent.

        Two states, and only two. If one of our Launchers is already adjacent, stand still and let
        it throw us -- moving away would leave the pickup radius for nothing, because the landing
        tile is measured from the LAUNCHER and is the same wherever we stand. Otherwise plant the
        next one on the tile ahead. Never inside VAULT_MIN_GAP of the goal: that is where the
        firing lane will be, and a friendly building in the lane jams the turret for good (G11).
        """
        if self.enemy_anchor is None or goal is None:
            return False
        if abs(pos.x - goal[0]) + abs(pos.y - goal[1]) < VAULT_MIN_GAP:
            return False
        if self._launcher_adjacent(ct, pos):
            self.vault_wait += 1
            # A Launcher that cannot find a forward landing tile would otherwise pin the rusher
            # beside it for the rest of the match -- the one way this lever could be catastrophic.
            return self.vault_wait <= VAULT_PATIENCE
        self.vault_wait = 0
        if self.vaults >= VAULT_MAX or not self._can_act(ct):
            return False
        try:
            if ct.get_global_resources() < ct.get_launcher_cost() + VAULT_FLOOR:
                return False
        except Exception:
            return False
        best, best_d = None, None
        for d in CARDINALS:
            t = pos.add(d)
            key = (t.x, t.y)
            if key in self.rush_ray or key in self.core_tiles or key in self.known_ore:
                continue
            score = (t.x - goal[0]) ** 2 + (t.y - goal[1]) ** 2
            if best_d is not None and score >= best_d:
                continue
            try:
                if not ct.can_build_launcher(t):
                    continue
            except Exception:
                continue
            best, best_d = t, score
        if best is None:
            return False
        try:
            ct.build_launcher(best)
        except Exception:
            return False
        self.vaults += 1
        return True

    def _launcher_adjacent(self, ct, pos):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                bid = self._building_at(ct, Position(pos.x + dx, pos.y + dy))
                if bid is None:
                    continue
                try:
                    if (ct.get_entity_type(bid) == EntityType.LAUNCHER
                            and ct.get_team(bid) == ct.get_team()):
                        return True
                except Exception:
                    continue
        return False

    def _run_launcher(self, ct):
        """Throw the rusher, and nothing else, ever.

        The only builder this will pick up is the one the store names as the rusher (S_RUSHER holds
        its id + 1). An economy builder thrown across the map abandons a chain in flight, and a
        chain that does not reach the Core scores exactly zero (G02) -- that single mistake would
        make the whole lever strongly negative.
        """
        try:
            if ct.get_action_cooldown() != 0:
                return
            pos = ct.get_position()
            w, h = ct.get_map_width(), ct.get_map_height()
            claim = ct.read_store(S_RUSHER)
            done = ct.read_store(S_RUSH_DONE) == 1
            anchor = unpack(ct.read_store(S_ENEMY_CORE) & 0xFFFF)
        except Exception:
            return
        rusher = claim - 1 if claim > 0 else -1
        # G49: the pickup is TEAM-BLIND -- an adjacent ENEMY Builder Bot is throwable, verified
        # with 81 legal target tiles for an enemy standing at r^2 = 1. Our vault Launchers sit on
        # the corridor between the two Cores, which on a symmetric map is the exact ground their
        # rusher walks, so displacement costs us nothing we were not already paying for: the
        # Launcher is idle from the round it has ferried our own builder onward. Throwing their
        # rusher five tiles back is five rounds off their siege for one otherwise-wasted action.
        if self._displace(ct, pos, w, h, rusher):
            return
        # ONE hop per Launcher per bot, permanently. Without this the relay thrashes: measured on
        # random-20260731-007-rot-25x25, the rusher built its Gunner on round 17, walked back past
        # the Launcher it had planted at (11,8), and was thrown (10,9)->(10,3) on rounds 29, 35,
        # 41, 47, 53, 59, 65 and 71 -- eight times, every six rounds, for the rest of the match.
        # Zero shots landed. A relay that can pick a bot up twice is a treadmill, not a relay.
        if done or claim <= 0 or anchor is None or rusher in self.thrown:
            return
        bot = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                t = Position(pos.x + dx, pos.y + dy)
                if not (0 <= t.x < w and 0 <= t.y < h):
                    continue
                try:
                    if ct.get_tile_builder_bot_id(t) == rusher:
                        bot = t
                except Exception:
                    continue
        if bot is None:
            return
        # Already close enough that the next thing to happen is a build, not a walk. Throwing now
        # would only shove the rusher past its own firing tile.
        if abs(bot.x - anchor[0]) + abs(bot.y - anchor[1]) < VAULT_MIN_GAP:
            return
        # A hop has to be worth the round it costs the rusher. Any old improvement is not enough:
        # a one-tile nudge inside the pickup radius is how the treadmill above got started.
        here_man = abs(bot.x - anchor[0]) + abs(bot.y - anchor[1])
        best_d = (bot.x - anchor[0]) ** 2 + (bot.y - anchor[1]) ** 2
        best = None
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                if dx * dx + dy * dy > 26:
                    continue
                t = Position(pos.x + dx, pos.y + dy)
                if not (0 <= t.x < w and 0 <= t.y < h):
                    continue
                d = (t.x - anchor[0]) ** 2 + (t.y - anchor[1]) ** 2
                if d >= best_d:
                    continue
                if here_man - (abs(t.x - anchor[0]) + abs(t.y - anchor[1])) < VAULT_GAIN:
                    continue
                if not self._landable(ct, t, w, h):
                    continue
                try:
                    if not ct.can_launch(bot, t):
                        continue
                except Exception:
                    continue
                best, best_d = t, d
        if best is None:
            return
        try:
            ct.launch(bot, best)
            self.thrown.add(rusher)
        except Exception:
            return

    def _displace(self, ct, pos, w, h, rusher):
        """Throw an adjacent ENEMY Builder Bot back the way it came. True if we spent the action.

        Their siege is a builder walking to a firing tile, exactly as ours is, and its arrival is
        the number beating us -- their first Gunner lands at a median round 14 against our 28. A
        Builder Bot thrown backwards has to walk the whole way again, and unlike a Barrier there is
        nothing to shoot and nothing to heal.

        Our own rusher always outranks this: a Launcher that spends its round shoving an enemy
        around while our builder stands beside it waiting has traded six of our tiles for five of
        theirs, at a loss.
        """
        home = None
        try:
            hx, hy = ct.read_store(S_CORE_X), ct.read_store(S_CORE_Y)
            if hx > 0 or hy > 0:
                home = (hx, hy)
        except Exception:
            home = None
        if home is None:
            return False
        foe = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                t = Position(pos.x + dx, pos.y + dy)
                if not (0 <= t.x < w and 0 <= t.y < h):
                    continue
                try:
                    bid = ct.get_tile_builder_bot_id(t)
                    if bid is None:
                        continue
                    if ct.get_team(bid) == ct.get_team():
                        # One of ours is standing here and it has first claim on the round. The
                        # ferry is the measured lever; displacement is opportunistic, and a
                        # Launcher that shoves an enemy while our own rusher waits beside it has
                        # traded six of our tiles for five of theirs, at a loss.
                        return False
                except Exception:
                    continue
                foe = t
        if foe is None:
            return False
        here = abs(foe.x - home[0]) + abs(foe.y - home[1])
        best, best_d = None, (foe.x - home[0]) ** 2 + (foe.y - home[1]) ** 2
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                if dx * dx + dy * dy > 26:
                    continue
                t = Position(pos.x + dx, pos.y + dy)
                if not (0 <= t.x < w and 0 <= t.y < h):
                    continue
                d = (t.x - home[0]) ** 2 + (t.y - home[1]) ** 2
                if d <= best_d:
                    continue
                if (abs(t.x - home[0]) + abs(t.y - home[1])) - here < VAULT_GAIN:
                    continue
                if not self._landable(ct, t, w, h):
                    continue
                try:
                    if not ct.can_launch(foe, t):
                        continue
                except Exception:
                    continue
                best, best_d = t, d
        if best is None:
            return False
        try:
            ct.launch(foe, best)
            return True
        except Exception:
            return False

    def _landable(self, ct, t, w, h):
        """Reject a sealed pocket. The throw arcs over walls, so it can strand a bot behind one."""
        free = 0
        for d in CARDINALS:
            n = t.add(d)
            if not (0 <= n.x < w and 0 <= n.y < h):
                continue
            try:
                if ct.get_tile_env(n) != Environment.WALL:
                    free += 1
            except Exception:
                free += 1
        return free >= 2

    def _clear_ray(self, ct, pos):
        """Step off the firing lane. One round well spent: standing in it costs the whole match."""
        if not self._can_move_now(ct):
            return True
        for d in CARDINALS:
            n = pos.add(d)
            if (n.x, n.y) in self.rush_ray:
                continue
            try:
                if ct.can_move(d):
                    ct.move(d)
                    return True
            except Exception:
                continue
        return False

    def _rush_approach(self, ct, pos):
        """No executable plan yet: close on the likeliest enemy Core and keep looking.

        Walking is never wasted while the symmetry is still ambiguous -- every tile observed on the
        way refutes hypotheses, and arriving at a candidate footprint refutes it outright. Returns
        False only when there is nothing left to aim at, which hands this builder back to the
        economy rather than leaving it idle.
        """
        anchor = self.enemy_anchor
        if anchor is None:
            return False
        if self._vault(ct, pos, anchor):
            return True
        return self._rush_walk(ct, pos, Position(anchor[0], anchor[1]))

    def _drop_plan(self):
        self.rush_route = None
        self.rush_target = None
        self.rush_i = 0
        self.rush_dist = None
        self.plan_round = -999
        self.rush_feeder = None
        self.rush_base_len = 0
        self.battery_n = 0
        self.battery_round = -999
        self.feeders = ()
        self.deposit_n = 0
        self.deposit_round = -999
        self.deposit_dry = 0
        self.rush_seg = 0

    def _plan_rush(self, ct, pos):
        """Derive the firing geometry from what we have observed, and keep it current.

        Recomputed only when the answer could actually have changed: a different enemy Core, a
        materially larger picture of the terrain, or an outright failure. Before the Gunner exists
        the plan is free to move -- that is the whole point of planning at runtime instead of
        reading a table. Once it exists we are committed: re-siting would abandon paid-for
        titanium, so only an explicit failure re-opens the question.
        """
        if siege is None or self.core_pos is None:
            return
        anchor = self.enemy_anchor
        if anchor is None:
            return
        if self.rush_route is not None and self.rush_target == anchor and self.rush_i > 0:
            return
        try:
            rnd = ct.get_current_round()
        except Exception:
            rnd = 0
        if self.plan_anchor == anchor:
            # Throttled on the last ATTEMPT, not on the last success. Throttling only the success
            # case is the expensive mistake: a rusher that cannot yet see a firing position -- the
            # normal state for the first twenty rounds, and the permanent state if the geometry
            # never resolves -- would pay the full BFS plus geometry search on all 1000 rounds.
            if (rnd - self.plan_round < REPLAN_ROUNDS
                    and len(self.terrain) - self.plan_tiles < REPLAN_TILES):
                return
        if not self._cpu_left(ct):
            return
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return
        self.plan_anchor = anchor
        self.plan_round = rnd
        self.plan_tiles = len(self.terrain)

        walls = self.known_walls | self.pred_walls
        ore = (self.known_ore | self.pred_ore) - self.known_walls
        foot = set(siege.footprint(anchor))
        blocked = walls | self.core_tiles | foot | self.enemy_core_tiles
        buildings = (self.occupied - self.core_tiles) - self.enemy_core_tiles - foot
        dist = self._flood(ct, (pos.x, pos.y), blocked | (buildings - {(pos.x, pos.y)}), w, h)
        known = (self.seen | self.pred_seen) or None
        try:
            found = siege.plan(w, h, anchor, self.core_tiles, walls, ore, buildings, dist,
                               blacklist=self.rush_black, known=known)
            if found is None:
                # Second pass with buildings ignored. Occupancy memory never expires -- a tile is
                # only cleared while it is in vision -- so a single enemy conveyor glimpsed near
                # their Core forty rounds ago permanently deletes every bead through it, and the
                # attack quietly evaporates. Measured against `frontier` on the fifteen published
                # maps: 21-9 with the old table, 13-17 once a strict planner replaced it, with
                # kills falling 13 -> 6. Against an inert opponent the two are indistinguishable,
                # which is exactly why this only shows up against a bot that builds things.
                # A remembered building is a reason to prefer another tile, never a reason to have
                # no plan: the executor re-checks legality on arrival anyway.
                found = siege.plan(w, h, anchor, self.core_tiles, walls, ore, frozenset(),
                                   self._flood(ct, (pos.x, pos.y), blocked, w, h),
                                   blacklist=self.rush_black, known=known)
        except Exception:
            found = None
        if found is None:
            if self.rush_i == 0:
                self.rush_route = None
                self.rush_target = None
            return
        if self.rush_route is not None and found["route"] == self.rush_route:
            return
        self.rush_route = found["route"]
        self.rush_target = anchor
        self.rush_ray = found["ray"]
        self.rush_i = 0
        self.rush_dist = None
        self.rush_feeder = found["ore"]
        self.rush_base_len = len(found["route"])
        self.battery_n = 0
        self.battery_round = -999
        # The route's own deposit is forward deposit number one. Seeding it here is what makes
        # FORWARD_DEPOSITS a count of PRODUCERS rather than a count of extras, and what stops the
        # extension planner proposing the tile we are already standing a Harvester on.
        self.feeders = (found["ore"],)
        self.deposit_n = 1
        self.deposit_dry = 0
        self.deposit_round = -999
        self.rush_seg = 0
        try:
            g = found["gunner"]
            ct.write_store(S_RUSH_RAY,
                           pack(Position(g[0], g[1])) | (DIR_BY_NAME_INDEX[found["facing"]] << 17))
            ct.write_store(S_RUSH_ACTIVE, 1)
        except Exception:
            pass

    def _flood(self, ct, source, blocked, w, h):
        """Walk distance from `source` over everything we believe is impassable. ~270 us."""
        dist = {source: 0}
        frontier = [source]
        step = 0
        while frontier:
            step += 1
            nxt = []
            for cx, cy in frontier:
                for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                    n = (cx + dx, cy + dy)
                    if n in dist or n[0] < 0 or n[1] < 0 or n[0] >= w or n[1] >= h:
                        continue
                    if n in blocked:
                        continue
                    dist[n] = step
                    nxt.append(n)
            frontier = nxt
        return dist

    def _rush_walk(self, ct, pos, target):
        """Walk to any tile orthogonally adjacent to `target`, shortest path around known walls."""
        if not self._can_move_now(ct):
            return True
        step = self._bfs_step(ct, pos, (target.x, target.y))
        if step is None:
            step = self._step_toward(ct, pos, target)
        if step is None:
            self.rush_stuck += 1
            # Unreachable. Blacklist the FIRING TILE -- not whichever step we happen to be on --
            # and re-derive, rather than give up on the whole attack the way the table version did.
            # The firing tile is what the geometry hangs off: banning a harvester tile leaves the
            # planner free to propose the same dead position again.
            if self.rush_stuck >= 12:
                self.rush_stuck = 0
                if self.rush_route and self.rush_i >= self.rush_base_len > 0:
                    # A battery turret we cannot walk to. Drop THAT step and keep the working
                    # siege: throwing away a firing turret because its optional neighbour is
                    # unreachable would be the worst trade on the board. Truncated to the start of
                    # the appended segment rather than to the current index, so a second deposit
                    # never leaves a Gunner behind with the Harvester that was to feed it dropped.
                    self._abort_segment(self.rush_route[self.rush_i][1])
                elif self.rush_route:
                    self.rush_black.add(self.rush_route[0][1])
                    self._drop_plan()
                else:
                    self._drop_plan()
            return True
        try:
            ct.move(step)
            self.rush_stuck = 0
        except Exception:
            self.rush_stuck += 1
        return True

    def _bfs_step(self, ct, pos, goal):
        """First step of a shortest path to any tile in `goal`'s EIGHT-neighbourhood.

        Multi-source BFS from the goal ring outward over the STATIC wall set (which the atlas gives us
        in full), cached per goal. ~w*h cheap integer ops, recomputed only when the goal changes.

        The ring is the full 8 because the build radius is the full 8 (r^2 <= 2, probed): seeding
        only the four cardinals sent the rusher past a diagonal it could already have built from.
        """
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return None
        key = (goal, self.occ_ver)
        if self.rush_dist is None or self.rush_dist_key != key:
            blocked = (self.known_walls | self.core_tiles | self.enemy_core_tiles
                       | self.occupied)
            blocked.discard((pos.x, pos.y))
            dist = {}
            frontier = []
            for dx, dy in DIR_DELTAS:
                n = (goal[0] + dx, goal[1] + dy)
                if 0 <= n[0] < w and 0 <= n[1] < h and n not in blocked:
                    dist[n] = 0
                    frontier.append(n)
            step_n = 1
            while frontier:
                nxt = []
                for cx, cy in frontier:
                    for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                        n = (cx + dx, cy + dy)
                        if n in dist or not (0 <= n[0] < w and 0 <= n[1] < h) or n in blocked:
                            continue
                        dist[n] = step_n
                        nxt.append(n)
                frontier = nxt
                step_n += 1
            self.rush_dist = dist
            self.rush_dist_key = key
        here = self.rush_dist.get((pos.x, pos.y))
        if here is None:
            return None
        best = None
        best_d = here
        for d in CARDINALS:
            n = pos.add(d)
            nd = self.rush_dist.get((n.x, n.y))
            if nd is None or nd >= best_d:
                continue
            try:
                if not ct.can_move(d):
                    continue
            except Exception:
                continue
            best, best_d = d, nd
        if best is not None:
            return best
        # Shortest step blocked by something dynamic -- accept a sideways move to break the block.
        for d in CARDINALS:
            n = pos.add(d)
            nd = self.rush_dist.get((n.x, n.y))
            if nd is None or nd > here:
                continue
            try:
                if ct.can_move(d):
                    return d
            except Exception:
                continue
        return None

    def _observe(self, ct, pos):
        """Fold this round's vision into private map memory (~66us for a full scan)."""
        if not self._cpu_left(ct):
            return
        try:
            tiles = ct.get_nearby_tiles()
        except Exception:
            return
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            w = h = 0
        # Seed the symmetry mask here rather than in the inference pass, which runs after this one:
        # the refutation below is incremental, so a tile observed before the mask exists would
        # never be paired against the tiles observed alongside it. Catch those up once, cheaply.
        if siege is not None and w and self.sym_mask is None and self.core_pos is not None:
            self.sym_mask = siege.seed_mask(w, h, (self.core_pos.x, self.core_pos.y))
            for key, code in self.terrain.items():
                self.sym_mask = siege.reject_by_tile(w, h, self.sym_mask, self.terrain, key, code)
        # An enemy Builder Bot inside our half is the second-cheapest archetype tell there is,
        # and unlike the census it is only worth paying for until it fires: the bit is latched
        # forever, so the scan switches itself off the moment it lands.
        scan_bots = (not (self.evidence & EV_DEEP)
                     and self.core_pos is not None and self.enemy_anchor is not None)
        for tile in tiles:
            key = (tile.x, tile.y)
            # Occupancy memory. The rush BFS must route AROUND buildings, not through them: the
            # gunner we just planted sits in the ring of the next build target, and our own economy
            # harvesters plug the ore tiles that form the only short lane on several maps.
            occ = self._building_at(ct, tile)
            if occ is None:
                if key in self.occupied:
                    self.occupied.discard(key)
                    self.occ_ver += 1
                self.known_blocked.discard(key)
            else:
                if key not in self.occupied:
                    self.occupied.add(key)
                    self.occ_ver += 1
                self.known_blocked.add(key)
                if key not in self.core_tiles and key not in self.enemy_core_tiles:
                    # Learn both Cores' real 2x2 footprints from vision rather than guessing an
                    # anchor. A sighted enemy Core settles the symmetry outright and outranks every
                    # inference -- it is the one observation that cannot be wrong.
                    #
                    # The same entity-type read also runs the ENEMY CENSUS -- how many turrets and
                    # how many producers they have standing. It costs one extra get_team() on a
                    # tile we were already interrogating, and it is the only signal that
                    # distinguishes a greedy economy from an anti-rush before either has touched
                    # us.
                    try:
                        et = ct.get_entity_type(occ)
                        mine = ct.get_team(occ) == ct.get_team()
                        if et == EntityType.CORE:
                            if mine:
                                self.core_tiles.add(key)
                            else:
                                self.enemy_core_tiles.add(key)
                                seen_at = ct.get_position(occ)
                                self.enemy_anchor = (seen_at.x, seen_at.y)
                                self.enemy_sighted = True
                        elif not mine:
                            if et == EntityType.GUNNER or et == EntityType.SENTINEL:
                                self.foe_turrets.add(key)
                            elif et == EntityType.HARVESTER:
                                self.foe_harvesters.add(key)
                    except Exception:
                        pass
            if scan_bots:
                self._scan_intruder(ct, tile, key)
            if key in self.seen:
                continue
            env = self._env(ct, tile)
            if env is None:
                continue
            self.seen.add(key)
            if env == Environment.WALL:
                code = siege.WALL if siege is not None else 1
                self.known_walls.add(key)
            elif env == Environment.ORE_TITANIUM:
                code = siege.ORE if siege is not None else 2
                self.known_ore.add(key)
            else:
                code = siege.EMPTY if siege is not None else 0
            if siege is None or w == 0:
                continue
            self.terrain[key] = code
            if self.sym_mask is not None:
                # One tile at a time, three dict lookups: a hypothesis dies the moment this tile
                # and its image under it disagree. Rescanning the whole memory every round would
                # be the same answer for a hundred times the CPU.
                self.sym_mask = siege.reject_by_tile(w, h, self.sym_mask, self.terrain, key, code)

    # --- runtime map inference -----------------------------------------

    def _infer_enemy_core(self, ct):
        """Decide where the enemy Core is, agree with the rest of the team, and mirror the map.

        Every map in this game is symmetric one of exactly three ways (G32), so our own anchor
        implies at most three enemy anchors and terrain refutes the wrong ones. That is the entire
        replacement for `atlas.identify()`: it works on a map nobody has ever seen, which the atlas
        by construction cannot.

        Precedence is strict. A Core we have actually LOOKED at beats a Core somebody else looked
        at, which beats an inference, which beats a guess. Anything less and one unit's bad guess
        propagates through the store and sends the siege to an empty corner for a thousand rounds.
        """
        if siege is None or self.core_pos is None:
            return
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return
        anchor = (self.core_pos.x, self.core_pos.y)
        if self.sym_mask is None:
            self.sym_mask = siege.seed_mask(w, h, anchor)

        try:
            self.sym_mask |= ct.read_store(S_SYMMETRY) & siege.ALL_REJECTED
        except Exception:
            pass
        self.sym_mask = siege.reject_by_footprint(w, h, anchor, self.sym_mask,
                                                  self.seen, self.enemy_core_tiles)
        if self.enemy_sighted and self.enemy_anchor is not None:
            self.sym_mask |= siege.index_mask(w, h, anchor, self.enemy_anchor)
        if self.sym_mask == siege.ALL_REJECTED:
            # Our own reasoning has eliminated every possibility, so it is the reasoning that is
            # wrong. Start again rather than stand still: a stale hypothesis is recoverable, an
            # empty one is not.
            self.sym_mask = siege.seed_mask(w, h, anchor)

        shared = 0
        try:
            shared = ct.read_store(S_ENEMY_CORE)
        except Exception:
            shared = 0
        told = unpack(shared & 0xFFFF) if shared else None
        if told is not None and not self.enemy_sighted:
            if shared & SIGHTED:
                self.enemy_anchor, self.enemy_sighted = told, True
            elif told in siege.alive(w, h, anchor, self.sym_mask):
                self.enemy_anchor = told      # somebody else's inference, still consistent with ours
        if not self.enemy_sighted:
            live = siege.alive(w, h, anchor, self.sym_mask)
            if live:
                if self.enemy_anchor not in live:
                    # Closest first: if the guess is wrong we find out on arrival, and we find out
                    # after the shortest possible detour.
                    self.enemy_anchor = min(
                        live, key=lambda c: (c[0] - anchor[0]) ** 2 + (c[1] - anchor[1]) ** 2)
            elif self.enemy_anchor is None:
                return

        try:
            # Slot 11 carries two monotone bitfields at once: the symmetry rejection mask in bits
            # 0-2 and the archetype evidence above it. Same writer, same round, same merge -- and
            # every reader of either field masks, so neither can see the other.
            ct.write_store(S_SYMMETRY, self.sym_mask | self.evidence)
            if self.enemy_anchor is not None:
                value = pack(Position(self.enemy_anchor[0], self.enemy_anchor[1]))
                if self.enemy_sighted:
                    value |= SIGHTED
                if self.enemy_sighted or not (shared & SIGHTED):
                    ct.write_store(S_ENEMY_CORE, value)
        except Exception:
            pass

        self._predict(ct, w, h, anchor)

    def _predict(self, ct, w, h, anchor):
        """Reflect our own half onto the enemy half once one symmetry survives.

        The rulebook guarantee is that the map IS its own mirror image, so terrain we have walked
        past on our side is a free, exact description of ground we have never seen. Only terrain --
        buildings are not part of the map and still have to be looked at. Rebuilt on a hypothesis
        change or once the picture has grown materially, never every round: ~90 us at full memory.

        Only the rusher pays for this. Nothing else reads the prediction -- the economy navigates
        on ground it has actually seen -- so mirroring the map in all six builders would be five
        copies of the same 90 us for no behaviour at all.
        """
        if self.rush_role is False:
            return
        index = siege.symmetry_index(w, h, anchor, self.sym_mask)
        if index is None:
            if self.pred_seen:
                self.pred_walls, self.pred_ore, self.pred_seen = set(), set(), set()
                self.pred_index, self.pred_n = None, -1
            return
        if index == self.pred_index and len(self.terrain) - self.pred_n < REPLAN_TILES:
            return
        if not self._cpu_left(ct):
            return
        self.pred_index, self.pred_n = index, len(self.terrain)
        try:
            self.pred_walls, self.pred_ore, self.pred_seen = siege.mirror_terrain(
                w, h, index, self.terrain)
        except Exception:
            self.pred_walls, self.pred_ore, self.pred_seen = set(), set(), set()

    def _read_ray(self, ct):
        """Refresh the reserved firing lane from the store.

        A friendly ANYWHERE in a Gunner's ray becomes its target and jams it for the rest of the
        match (G11). Measured on vault/a with the table version: an economy builder laid a conveyor
        at (20,2) on round 47 and the Gunner sat on the enemy Core for 953 rounds without firing.
        Offline the lane came out of the atlas; on an unseen map the rusher has to publish it.
        """
        if siege is None or self.rush_role is True:
            return
        try:
            raw = ct.read_store(S_RUSH_RAY)
        except Exception:
            return
        if raw == self.ray_raw:
            return
        self.ray_raw = raw
        if raw <= 0:
            self.rush_ray = frozenset()
            return
        g = unpack(raw & 0xFFFF)
        if g is None:
            self.rush_ray = frozenset()
            return
        idx = (raw >> 17) & 7
        dx, dy = DIR_DELTAS[idx]
        self.rush_ray = frozenset(
            (g[0] + k * dx, g[1] + k * dy) for k in range(1, siege.REACH8[idx] + 1))

    # --- chain construction -------------------------------------------

    def _settle_owed(self, ct, pos):
        """Build the belt we owe on the tile we just vacated, facing the way we walked."""
        if self.owed is None:
            return False
        belt_pos, facing = self.owed
        if (belt_pos.x, belt_pos.y) in self.rush_ray:
            self.owed = None
            self._abandon()
            return False
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
                self.built_belts.append(((belt_pos.x, belt_pos.y), facing))
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
        recognise the terminal tile, and the chain would never be capped -- scoring zero (G02).
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
            ct.write_store(S_CLAIM_0 + (self.ordinal % N_CLAIMS), 0)
        except Exception:
            pass

    def _abandon(self):
        # Blacklist the tile we failed on. The atlas knows about ore that vision would never have
        # surfaced -- including tiles walled off from us -- and without this the builder re-picks the
        # same unreachable target forever and delivers nothing all match.
        if self.target_ore is not None:
            self.failed_ore.add(self.target_ore)
        self.phase = "seek"
        self.target_ore = None
        self.owed = None
        self.owed_is_final = False
        self.stuck = 0

    def _repair_chain(self, ct, pos):
        """Put back any belt of ours that has gone missing. Returns True if we acted or moved.

        Only tiles we can actually see are judged missing -- get_tile_building_id is safe out of vision
        but returns None there, which would look identical to a destroyed belt and send us chasing ghosts.
        """
        if not self.built_belts:
            return False

        if self.repair_target is None:
            for belt_pos, facing in self.built_belts:
                tile = Position(belt_pos[0], belt_pos[1])
                try:
                    if not ct.is_in_vision(tile):
                        continue
                except Exception:
                    continue
                if self._building_at(ct, tile) is None:
                    # A belt of ours we can SEE is gone. Nothing friendly removes it -- our own
                    # turrets never fire on our own team -- so this is either their gunner or a
                    # builder standing on it with the range-0 attack (G14). The saboteur tell.
                    self.evidence = self.evidence | EV_ECON_HIT
                    self.repair_target = (tile, facing)
                    break
            if self.repair_target is None:
                return False

        tile, facing = self.repair_target
        if self._building_at(ct, tile) is not None:
            self.repair_target = None       # somebody beat us to it
            return False

        if pos.distance_squared(tile) == 1:
            if not self._can_act(ct):
                return True
            try:
                if ct.can_build_conveyor(tile, facing):
                    ct.build_conveyor(tile, facing)
                    self.repair_target = None
                    return True
            except Exception:
                self.repair_target = None
            return False

        if not self._can_move_now(ct):
            return True
        step = self._step_toward(ct, pos, tile)
        if step is None:
            self.repair_target = None
            return False
        try:
            ct.move(step)
        except Exception:
            self.repair_target = None
        return True

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
        if (ore.x, ore.y) in self.rush_ray:
            self._abandon()
            return False
        if pos.distance_squared(ore) != 1:
            return False
        if self._building_at(ct, ore) is not None:
            self._abandon()
            return False
        if not self._can_act(ct):
            return False
        try:
            need = ct.get_harvester_cost()
            if not self._rush_funded(ct):
                need += self._pv("rush_reserve")
            if ct.get_global_resources() < need:
                return False
            if ct.can_build_harvester(ore):
                ct.build_harvester(ore)
                # A harvester orthogonally adjacent to the Core footprint already delivers straight
                # into it -- the chain is complete with zero conveyors. Building one anyway would add
                # a second output and split the harvester's fixed 10 Ti/4 rounds round-robin.
                if self._core_dir_from(ct, ore) is not None:
                    self._finish_chain(ct)
                else:
                    self.phase = "belt"   # walk home laying the belt behind us
                return True
        except Exception:
            return False
        return False

    def _rush_funded(self, ct):
        """True when the economy may spend freely again.

        A harvester is 20 base titanium against a Gunner's 10, and five economy builders buying
        them in the first forty rounds is what starves the rush. Hold RUSH_RESERVE back until the
        rusher reports its route finished -- or until the race is decided either way, so a dead
        rusher cannot freeze the economy for the rest of the match.

        The gate used to be "is this one of the fifteen maps we precomputed". It is now "does a
        rusher actually own an executable plan", which is the condition that was always meant: an
        economy that hoards for a siege nobody is running is pure loss, and one that spends through
        a siege that IS running loses the race by a single turn.
        """
        try:
            if ct.read_store(S_RUSH_ACTIVE) != 1:
                return True
            if ct.read_store(S_RUSH_DONE) == 1:
                return True
            return ct.get_current_round() > RUSH_RESERVE_UNTIL
        except Exception:
            return True

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
            if key in claimed or key in self.failed_ore:
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
        """Spread out from the Core to find ore. Deterministic -- never the global random module (G26)."""
        core = self._nearest_core_tile(pos)
        if core is None:
            order = CARDINALS
        else:
            away = cardinal_of(pos.x - core.x, pos.y - core.y)
            order = (away,) + tuple(d for d in CARDINALS if d != away)
        offset = (self.ordinal or 0) % len(order)
        for i in range(len(order)):
            d = order[(i + offset) % len(order)]
            if self._passable(ct, pos, d):
                try:
                    ct.move(d)
                except Exception:
                    continue
                return

    def _passable(self, ct, pos, d):
        """can_move, plus: a non-rusher never enters the gunner's firing lane (G11)."""
        try:
            if not ct.can_move(d):
                return False
        except Exception:
            return False
        if self.rush_role is True or not self.rush_ray:
            return True
        n = pos.add(d)
        return (n.x, n.y) not in self.rush_ray

    def _nav_field(self, ct, target):
        """BFS distance field from `target` over everything we know is impassable.

        The greedy stepper below cannot route around a concave obstacle: `Direction.rotate_left()`
        returns a DIAGONAL, which the cardinal filter then discards, so its sidestep branch is dead
        code and the walk degenerates into a two-tile oscillation that never terminates and never
        trips a stuck counter (the moves all succeed). That single defect was costing whole chains.
        Cached on (target, obstacle count); a full 30x30 BFS is ~270 us against a 10 ms budget.
        """
        key = (target.x, target.y)
        n = len(self.known_walls) + len(self.known_blocked)
        if self._nav is not None and self._nav_key == key and self._nav_n == n:
            return self._nav
        try:
            w, h = ct.get_map_width(), ct.get_map_height()
        except Exception:
            return None
        walls, blocked = self.known_walls, self.known_blocked
        dist = {key: 0}
        frontier = [key]
        d = 0
        while frontier:
            d += 1
            nxt = []
            for x, y in frontier:
                for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if nb[0] < 0 or nb[1] < 0 or nb[0] >= w or nb[1] >= h:
                        continue
                    if nb in dist or nb in walls or nb in blocked:
                        continue
                    dist[nb] = d
                    nxt.append(nb)
            frontier = nxt
        self._nav, self._nav_key, self._nav_n = dist, key, n
        return dist

    def _step_toward(self, ct, pos, target):
        field = self._nav_field(ct, target)
        if field is not None:
            here = field.get((pos.x, pos.y))
            best, best_d = None, None
            for d in CARDINALS:
                n = pos.add(d)
                nd = field.get((n.x, n.y))
                if nd is None:
                    continue
                if here is not None and nd >= here:
                    continue
                try:
                    if not ct.can_move(d):
                        continue
                except Exception:
                    continue
                if best_d is None or nd < best_d:
                    best_d, best = nd, d
            if best is not None:
                return best

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
            if self._passable(ct, pos, d):
                return d
        for d in CARDINALS:
            if self._passable(ct, pos, d):
                return d
        return None

    # --- builder combat / upkeep ---------------------------------------

    def _core_ring(self, ct):
        """The twelve tiles that touch our 2x2 Core footprint, in bounds."""
        if self.core_pos is None:
            return ()
        x0, y0 = self.core_pos.x, self.core_pos.y
        foot = set(siege.footprint((x0, y0))) if siege is not None else set()
        foot |= self.core_tiles
        out = []
        for dx in range(-1, 3):
            for dy in range(-1, 3):
                t = (x0 + dx, y0 + dy)
                if t in foot or t in self.known_walls:
                    continue
                if not self._in_bounds(ct, Position(t[0], t[1])):
                    continue
                out.append(t)
        return tuple(out)

    def _hold_home(self, ct, pos):
        """Heal and brick while the Core is under sustained fire. True if the round was spent.

        Two things, in that order. Healing first because it is the cheapest damage-per-titanium
        in the game and needs no build site: 4 HP for a flat 1 Ti, against a Gunner's 2 Ti for 10
        damage on a turret that averages 5 damage a round. Bricking second because a Barrier on
        the tile their turret needs costs 3 Ti and takes 6 Ti of shooting to clear -- and a
        Gunner's ray stops at the FIRST building, so one wall shuts a whole lane.

        The ring is deliberately never closed. A chain scores only by terminating on a tile
        orthogonally adjacent to the footprint (G02); walling ourselves in would convert every
        later harvester into a dead 20 Ti liability.
        """
        if self.rush_role is True or self.owed is not None or self.phase == "belt":
            return False
        # Two ways in. The alarm is the measured one -- our own Core below ALARM_PERCENT, and
        # `self.alarm` is bit-for-bit the store read it replaces. The posture gate is the seam: a
        # DEFENCE specialist comes home on the fed-turret bit, which latches tens of rounds before
        # the Core has lost 12% of itself. RUSH leaves it off, so this is exactly today's
        # condition in the shipped build.
        if not (self.alarm or (self._pv("hold_on_posture")
                               and self.posture == POSTURE_DEFENCE)):
            return False
        if self._heal(ct, pos):
            return True
        try:
            if ct.get_current_round() < self._pv("fortify_from"):
                return False
            cost = ct.get_barrier_cost()
            if ct.get_global_resources() < cost + self._pv("chain_reserve"):
                return False
        except Exception:
            return False

        keep_open = self._pv("fortify_keep_open")
        ring = self._core_ring(ct)
        free = [t for t in ring if self._building_at(ct, Position(t[0], t[1])) is None]
        if len(free) <= keep_open:
            return False
        if self.enemy_anchor is not None:
            ax, ay = self.enemy_anchor
            free.sort(key=lambda t: ((t[0] - ax) ** 2 + (t[1] - ay) ** 2,
                                     (t[0] - pos.x) ** 2 + (t[1] - pos.y) ** 2, t))
        else:
            free.sort(key=lambda t: ((t[0] - pos.x) ** 2 + (t[1] - pos.y) ** 2, t))
        # Only the tiles on the side they actually walk in from are worth 3 Ti and a point of
        # cost scale; the far half of the ring is where our own chains have to terminate.
        for t in free[:len(free) - keep_open]:
            target = Position(t[0], t[1])
            if pos.distance_squared(target) == 1:
                if not self._can_act(ct):
                    return True
                try:
                    if ct.can_build_barrier(target):
                        ct.build_barrier(target)
                        return True
                except Exception:
                    pass
                continue
            if not self._can_move_now(ct):
                return True
            step = self._step_toward(ct, pos, target)
            if step is None:
                continue
            try:
                ct.move(step)
                return True
            except Exception:
                continue
        return False

    def _sabotage(self, ct, pos):
        """Fire at our own tile while standing on an enemy belt (G14) -- the only builder attack."""
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
    # Turrets -- every API here is team-blind (G10). Verify before firing.
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
            # offering this same target forever (G11) -- hold fire rather than shoot through it.
            return
        if not self._may_fire(ct, occupant):
            return
        try:
            if ct.can_fire(target):
                ct.fire(target)
        except Exception:
            return

    def _may_fire(self, ct, occupant):
        """Posture hook on turret policy. True in every posture today.

        The seam is here because this is precisely where a DEFENCE specialist differs: a Gunner
        refills its 10 Ti magazine only from an adjacent producer, so a magazine spent on the
        enemy conveyor that happens to be nearer in the lane is a magazine that is not there when
        their Builder Bot arrives.
        """
        self._sync_state(ct)
        want = self._pv("fire_only")
        if want is None:
            return True
        try:
            return ct.get_entity_type(occupant) in want
        except Exception:
            return True

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
