"""The global communication store, as a typed schema instead of loose ints.

Engine facts this schema is built on, all verified against fcode 2.3.6 rather
than read off the docs:

  * STORE_SIZE is 16 slots of u32. read_store returns the snapshot from the
    start of the round; write_store lands at the start of the NEXT round.

  * "Next turn" in the API docs means next ROUND. A write by the Core (id 1,
    which always acts first) is NOT visible to a Builder acting later in the
    same round -- measured: Core wrote 1003 at r=3, the Builder read 0 at
    r=3 and 1003 at r=4.

  * Therefore ONE WRITER PER SLOT IS FORCED. Two units sharing a slot both
    read the same start-of-round snapshot, both OR in their bits, and the
    second write silently destroys the first. There is no atomic accumulate,
    so 16 Builders cannot share one word two bits apiece.

That last point is why SLOTS, not bits, are the scarce resource here. Inside
a word we spend bits freely -- nothing competes for them. Across words we are
hard-capped at 16, which is what caps the number of broadcasting Builders.

Layout
------
    0   CORE_ECON     titanium arriving over the next few rounds
    1   CORE_THREAT   core hp, trend, and worst-case incoming damage
    2   CORE_TURRET0  two enemy turrets near the core
    3   CORE_TURRET1  two more
    4.. BUILDER       one per broadcasting Builder (12 available)

Every word carries a 4-bit heartbeat holding `get_current_round() & 0xF`.
Readers use it to spot a slot whose owner died: a Builder never releases its
slot, and its last write would otherwise sit there looking live forever.
"""

from __future__ import annotations

SLOT_CORE_ECON = 0
SLOT_CORE_THREAT = 1
SLOT_CORE_TURRET0 = 2
SLOT_CORE_TURRET1 = 3
BUILDER_SLOT_FIRST = 4
BUILDER_SLOT_LAST = 15
BUILDER_SLOTS = tuple(range(BUILDER_SLOT_FIRST, BUILDER_SLOT_LAST + 1))

HEARTBEAT_OFFSET = 28
HEARTBEAT_BITS = 4
HEARTBEAT_MASK = (1 << HEARTBEAT_BITS) - 1

# A slot is treated as abandoned once its heartbeat is this many rounds
# behind. The heartbeat wraps every 16 rounds, so the window has to stay
# well inside that or a live slot reads as stale.
STALE_AFTER = 6


class Field:
    """One packed bit-field inside a u32 store word.

    `scale` lets a field carry a coarser unit than 1 (core hp is stored in
    2-hp bins). `signed` uses two's complement inside the field width, which
    is what lets the hp trend express "we are healing faster than they hit".
    Values are clamped, never wrapped -- a wrapped field reads as a plausible
    wrong answer, and a clamped one reads as "at least this much", which is
    the failure mode you can reason about.
    """

    __slots__ = ("offset", "bits", "signed", "scale", "_mask")

    def __init__(self, offset: int, bits: int, signed: bool = False, scale: int = 1):
        self.offset = offset
        self.bits = bits
        self.signed = signed
        self.scale = scale
        self._mask = (1 << bits) - 1

    @property
    def lo(self) -> int:
        return (-(1 << (self.bits - 1)) if self.signed else 0) * self.scale

    @property
    def hi(self) -> int:
        top = (1 << (self.bits - 1)) - 1 if self.signed else self._mask
        return top * self.scale

    def pack(self, word: int, value: float) -> int:
        raw = int(round(value / self.scale))
        if self.signed:
            limit = 1 << (self.bits - 1)
            raw = max(-limit, min(limit - 1, raw))
            raw &= self._mask
        else:
            raw = max(0, min(self._mask, raw))
        return (word & ~(self._mask << self.offset)) | (raw << self.offset)

    def unpack(self, word: int) -> int:
        raw = (word >> self.offset) & self._mask
        if self.signed and raw >= (1 << (self.bits - 1)):
            raw -= 1 << self.bits
        return raw * self.scale


# --- slot 0: economy ---------------------------------------------------------
#
# Titanium arriving per round, in whole stacks (STACK_SIZE = 10), for the five
# rounds a reader can actually act on.
#
# Why the window starts at t+2 and not t+1: a stack one hop from the Core at
# the Core's turn in round T is credited to the balance at T+1, and the Core's
# write only becomes readable at T+1 -- so by the time anybody can read a t+1
# figure it is already in get_global_resources(). Publishing it would be
# publishing a number every reader already has.
#
# Why it stops at t+6: a hop-h tile is at most h steps from the footprint, so
# dist_sq <= h^2, and CORE_VISION_RADIUS_SQ is 36. Six hops is therefore the
# last one guaranteed visible for ANY chain shape; hop 7 can reach dist_sq 49
# and is only visible if the chain happens to bend.
#
# Three bits each: the Core has exactly 8 orthogonally adjacent feed tiles, so
# 8 stacks/round is the hard ceiling -- and reaching it sustained needs ~32
# Harvesters delivering at once, against MAX_TEAM_UNITS = 50. Clamping at 7
# costs nothing reachable.
ECON_HORIZON = 5   # buckets, covering t+2 .. t+6
FIRST_ECON_HOP = 2  # bucket 0 is hop 2, i.e. write_round + 2
ECON_ARRIVALS = tuple(Field(3 * i, 3) for i in range(ECON_HORIZON))
ECON_HEARTBEAT = Field(HEARTBEAT_OFFSET, HEARTBEAT_BITS)

# Enemy Core intel rides in this word's spare bits (15..27) rather than taking
# a slot of its own: slots are the scarce resource here (one writer each,
# forced by the engine) and bits inside an already-spent word are free.
# hp in 8-hp bins covers CORE_MAX_HP 500 in 6 bits, which is ample for the
# only question it answers -- are we close enough to finishing them.
ECON_ENEMY_SEEN = Field(15, 1)
ECON_ENEMY_HP = Field(16, 6, scale=8)


def pack_econ(arrivals, round_no: int, enemy_hp: int | None = None) -> int:
    word = 0
    for field, stacks in zip(ECON_ARRIVALS, arrivals):
        word = field.pack(word, stacks)
    if enemy_hp is not None:
        word = ECON_ENEMY_SEEN.pack(word, 1)
        word = ECON_ENEMY_HP.pack(word, enemy_hp)
    return ECON_HEARTBEAT.pack(word, round_no & HEARTBEAT_MASK)


def unpack_enemy_core(word: int) -> int | None:
    """Enemy Core hp if anyone has seen it, else None."""
    if not ECON_ENEMY_SEEN.unpack(word):
        return None
    return ECON_ENEMY_HP.unpack(word)


def unpack_econ(word: int) -> list[int]:
    """Stacks expected at t+2 .. t+6, indexed from the round that WROTE it.

    Almost nobody wants this directly -- see arrivals_from_now(). A reader is
    always at least one round behind the writer, so bucket i does not mean
    "i rounds from now", and treating it that way is an off-by-one that
    produces plausible numbers instead of an error.
    """
    return [f.unpack(word) for f in ECON_ARRIVALS]


def arrivals_from_now(word: int, round_no: int) -> dict[int, int]:
    """Stacks expected, keyed by ABSOLUTE round. The safe way to read econ.

    The store word carries the round that wrote it in its heartbeat, so the
    schedule can be re-anchored to real rounds rather than to the reader's
    guess about latency. Buckets that have already landed are dropped -- they
    are in get_global_resources() by now, and reporting them twice is how a
    consumer talks itself into waiting for titanium it already has.

    Observed live: the Core computed [1,0,0,0,0] at round R while Builders
    read [0,1,0,0,0] from the R-1 write. Same stack, one hop further out, one
    bucket later. This function is what makes those agree.
    """
    written = (word >> HEARTBEAT_OFFSET) & HEARTBEAT_MASK
    age = (round_no - written) & HEARTBEAT_MASK
    out = {}
    for i, stacks in enumerate(unpack_econ(word)):
        target = round_no - age + FIRST_ECON_HOP + i
        if target > round_no and stacks:
            out[target] = stacks
    return out


# --- slot 1: threat ----------------------------------------------------------
#
# hp is binned to 2 because HEAL_AMOUNT is 4 -- a 2-hp step is already finer
# than the smallest action anyone can take. It is NOT binned to 4: damage
# comes in 2 (builder), 7 (gunner) and 18 (sentinel), whose gcd with 4 is 1,
# so core hp lands on every residue and 4-hp bins would throw away real state
# at exactly the low-hp end where it decides whether you survive a round.
#
# dhp is the mean hp change per round over the last 4 rounds. Four is the
# smallest correct window, not a round number: SENTINEL_FIRE_COOLDOWN is 2, so
# a 4-round window holds exactly two Sentinel shots whatever the phase. An odd
# window holds one or two depending on when you sampled and manufactures
# variation that is not there. Signed, because out-healing the incoming fire
# is a state worth telling menders about.
#
# burst is the worst case: every visible enemy turret that COULD be aimed at
# the Core (one rotate is 10 Ti and a single round away) plus adjacent enemy
# Builders. It is an upper bound, not a forecast -- enemy ammo and cooldowns
# are both unreadable, so this routinely overshoots. That is the right shape
# for "can I survive the worst round", and the name says bound, not estimate.
THREAT_HP = Field(0, 8, scale=2)          # 0..510, covers CORE_MAX_HP 500
THREAT_DHP = Field(8, 6, signed=True)     # -32..+31 hp/round
THREAT_BURST = Field(14, 6)               # 0..63 hp in one round
THREAT_HEARTBEAT = Field(HEARTBEAT_OFFSET, HEARTBEAT_BITS)


def pack_threat(hp: int, dhp: float, burst: int, round_no: int) -> int:
    word = THREAT_HP.pack(0, hp)
    word = THREAT_DHP.pack(word, dhp)
    word = THREAT_BURST.pack(word, burst)
    return THREAT_HEARTBEAT.pack(word, round_no & HEARTBEAT_MASK)


def unpack_threat(word: int) -> dict:
    return {
        "hp": THREAT_HP.unpack(word),
        "dhp": THREAT_DHP.unpack(word),
        "burst": THREAT_BURST.unpack(word),
    }


# --- slots 2-3: enemy turrets near the core ----------------------------------
#
# Only the Core can supply this. Max Sentinel reach is dist_sq 32 and
# CORE_VISION_RADIUS_SQ is 36, so the Core sees everything able to shoot it --
# while a Builder sees only BUILDER_BOT_VISION_RADIUS_SQ = 20, radius ~4.5,
# and genuinely cannot see what is shooting at it as it approaches.
#
# Stored as an offset from the Core anchor, which is why 4 bits per axis is
# enough: anything that matters is within dist_sq 32.
#
# Facing is worth its 3 bits precisely because turrets are line weapons. A
# Builder that knows the facings can route between the live rays instead of
# treating the whole area as lethal.
TURRET_RECORD_BITS = 12
TURRET_PER_WORD = 2

_TURRET_FIELDS = tuple(
    (
        Field(base + 0, 4, signed=True),   # dx from core anchor, -8..+7
        Field(base + 4, 4, signed=True),   # dy
        Field(base + 8, 1),                # 0 = gunner, 1 = sentinel
        Field(base + 9, 3),                # facing, index into geometry.COMPASS
    )
    for base in (0, TURRET_RECORD_BITS)
)
TURRET_COUNT = Field(24, 2)               # how many records in this word
TURRET_HEARTBEAT = Field(HEARTBEAT_OFFSET, HEARTBEAT_BITS)


def pack_turrets(records, round_no: int) -> int:
    """records: up to 2 tuples of (dx, dy, is_sentinel, facing_index)."""
    word = 0
    used = 0
    for fields, rec in zip(_TURRET_FIELDS, records):
        dx, dy, is_sentinel, facing = rec
        word = fields[0].pack(word, dx)
        word = fields[1].pack(word, dy)
        word = fields[2].pack(word, 1 if is_sentinel else 0)
        word = fields[3].pack(word, facing)
        used += 1
    word = TURRET_COUNT.pack(word, used)
    return TURRET_HEARTBEAT.pack(word, round_no & HEARTBEAT_MASK)


def unpack_turrets(word: int) -> list[dict]:
    out = []
    for fields in _TURRET_FIELDS[: TURRET_COUNT.unpack(word)]:
        out.append(
            {
                "dx": fields[0].unpack(word),
                "dy": fields[1].unpack(word),
                "is_sentinel": bool(fields[2].unpack(word)),
                "facing": fields[3].unpack(word),
            }
        )
    return out


# --- slots 4-15: one per broadcasting Builder --------------------------------
#
# Each Builder owns its word outright, which is the only way to avoid the
# lost-update problem above. Three bits of action rather than two: bits are
# free inside a word we already spend a slot on, and re-cutting a schema that
# other modules decode is much more expensive than over-sizing it now.
#
# The action report is what lets the Core separate gross damage from healing.
# The timing lines up exactly: a Builder's write during round R is readable at
# R+1, and the Core at its turn in R+1 holds an hp delta that also covers
# round R. Same window, no skew:
#
#     damage(R) = HEAL_AMOUNT * healers(R) - hp_delta(R)
ACT_NONE = 0
ACT_HEAL_CORE = 1
ACT_BUILD_HARVESTER = 2
ACT_BUILD_CONVEYOR = 3
ACT_BUILD_GUNNER = 4
ACT_BUILD_SENTINEL = 5
ACT_ATTACK = 6
ACT_BLOCKED = 7

BUILDER_ACTION = Field(0, 3)
BUILDER_TARGET_X = Field(3, 6)     # tile the Builder is committed to, absolute
BUILDER_TARGET_Y = Field(9, 6)
BUILDER_HAS_TARGET = Field(15, 1)
BUILDER_HP = Field(16, 4, scale=4)  # own hp in 4-hp bins, 0..60 of MAX 40
BUILDER_HEARTBEAT = Field(HEARTBEAT_OFFSET, HEARTBEAT_BITS)


def pack_builder(action: int, hp: int, round_no: int, target=None) -> int:
    word = BUILDER_ACTION.pack(0, action)
    word = BUILDER_HP.pack(word, hp)
    if target is not None:
        word = BUILDER_HAS_TARGET.pack(word, 1)
        word = BUILDER_TARGET_X.pack(word, target[0])
        word = BUILDER_TARGET_Y.pack(word, target[1])
    return BUILDER_HEARTBEAT.pack(word, round_no & HEARTBEAT_MASK)


def unpack_builder(word: int) -> dict:
    out = {
        "action": BUILDER_ACTION.unpack(word),
        "hp": BUILDER_HP.unpack(word),
        "target": None,
    }
    if BUILDER_HAS_TARGET.unpack(word):
        out["target"] = (BUILDER_TARGET_X.unpack(word), BUILDER_TARGET_Y.unpack(word))
    return out


def is_fresh(word: int, round_no: int) -> bool:
    """Has this slot been written recently enough to believe?

    An all-zero word is the untouched initial state, not a live report. The
    heartbeat wraps at 16, so the comparison is done modulo that.
    """
    if word == 0:
        return False
    age = (round_no - ((word >> HEARTBEAT_OFFSET) & HEARTBEAT_MASK)) & HEARTBEAT_MASK
    return age <= STALE_AFTER


def claim_builder_slot(ct, round_no: int) -> int | None:
    """Pick a store slot for this Builder, preferring one nobody is using.

    Deliberately deterministic on unit id rather than first-free: every
    Builder computes the same assignment from the same snapshot, so two
    Builders spawned in the same round cannot both decide they own slot 4.
    Falls back to a stale slot, then to the id hash, so a Builder always has
    somewhere to write even when the team has outgrown the store.
    """
    mine = ct.get_id()
    live = []
    for slot in BUILDER_SLOTS:
        if is_fresh(ct.read_store(slot), round_no):
            live.append(slot)
    free = [s for s in BUILDER_SLOTS if s not in live]
    if free:
        # Lowest free slot, not a hash of the unit id. Dense, contiguous slots
        # keep the role rank dense, which is what lets a two-role mix reach
        # every Builder. Spawns are paced to roughly one per dozen rounds, so
        # two Builders racing for the same slot is rare, and the loser simply
        # re-claims next round when the winner's heartbeat appears.
        return free[0]
    return BUILDER_SLOTS[mine % len(BUILDER_SLOTS)]
