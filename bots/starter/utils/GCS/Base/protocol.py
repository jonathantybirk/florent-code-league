"""GCS wire-format definition — the single source of truth for the protocol.

Everything here is declarative: names, numbers, and tables. The encoder/decoder
in messages.py, the packing in codec.py, and the human-readable dump at the
bottom are all generated from these declarations, so the spec cannot drift from
the implementation.

Vocabulary
----------
slot        one of the 16 engine store indices (0-15), each holding one u32.
fact        one unit of knowledge: "tile T is in state S".
FOV index   a tile's rank in a fixed scan order of the full geometric vision
            disc of the sender's entity type (reading order: top-to-bottom,
            left-to-right).  Occlusion never changes the numbering — a unit
            simply never announces a tile it cannot currently see.
mixed radix pack several values into one integer by multiplying by each
            value's own count instead of rounding up to powers of two.
escape code a tile-state code that does not mean a tile state but re-reads
            the rest of the message (RUN / REMOTE / CONTROL).
"""

from __future__ import annotations

U32 = 2**32

# ---------------------------------------------------------------------------
# Reserved raw values (the topmost 516 u32 values, outside the payload range)
# ---------------------------------------------------------------------------
# 2 idle-heartbeat values, 2 free for future use, and a 512-value block that
# announces the Core's exact HP.  Everything strictly below PAYLOAD_SPACE is a
# normal mixed-radix payload.

IDLE_A = U32 - 1          # zero-payload heartbeat, alternate with IDLE_B
IDLE_B = U32 - 2
RESERVED_FREE_1 = U32 - 3  # unassigned, held in reserve
RESERVED_FREE_2 = U32 - 4  # unassigned, held in reserve

CORE_HP_BLOCK_SIZE = 512   # raw value CORE_HP_BASE + h  means "Core HP is h"
CORE_HP_BASE = U32 - 4 - CORE_HP_BLOCK_SIZE          # h in 0..500, 11 spare
CORE_HP_MAX = 500
# The Core announces only when its true HP has drifted more than this from the
# last value it published; readers latch the value until told otherwise.
CORE_HP_ANNOUNCE_DRIFT = 50

PAYLOAD_SPACE = CORE_HP_BASE     # == 2**32 - 516; payloads are 0..PAYLOAD_SPACE-1

# ---------------------------------------------------------------------------
# Slot map
# ---------------------------------------------------------------------------
SLOT_CORE = 0                    # the Core always owns slot 0
BUILDER_SLOTS_FROM = 1           # builders take 1, 2, ... upward
TURRET_SLOTS_FROM = 15           # turrets/launchers take 15, 14, ... downward
TURRET_RESERVED_SLOTS = 2        # hyperparameter n: bottom slots builders may
                                 # never evict turrets from (14 and 15)
STORE_SIZE = 16

# ---------------------------------------------------------------------------
# Timing conventions (all common knowledge, so none costs wire bits)
# ---------------------------------------------------------------------------
# The Core writes CONTROL/ASSIGN in the round it spawned a builder (and writes
# no other ASSIGN that round).  The write is readable next round; that round
# every unit's message is in RESYNC format (absolute position + one fact), the
# newborn's first message included.  For the following ONBOARD_ROUNDS rounds
# the Core streams archive knowledge through turret/launcher slots
# (speaker=1); those units stay silent and are exempt from liveness
# reclamation for the duration.
ONBOARD_ROUNDS = 8               # hyperparameter W
# Verified against the live engine (fcode 2.3.9): a builder spawned by the
# Core in round R gets its first run() in round R+1 — the very round the
# Core's ASSIGN becomes readable.  A newborn therefore knows it was spawned
# in (first_run_round - NEWBORN_FIRST_RUN_DELAY) and matches the ASSIGN
# whose write round equals that.
NEWBORN_FIRST_RUN_DELAY = 1

# ---------------------------------------------------------------------------
# Vision (tile counts of the full geometric disc per entity type)
# ---------------------------------------------------------------------------
VISION_RADIUS_SQ = {
    "core": 36, "builder_bot": 20, "gunner": 13, "sentinel": 32, "launcher": 26,
}
FOV_TILES = {
    "core": 113, "builder_bot": 69, "gunner": 45, "sentinel": 101, "launcher": 89,
}   # asserted against the radii in fov.py at import

# ---------------------------------------------------------------------------
# Tile-state alphabet — one flat enumeration, S = 106 codes
# ---------------------------------------------------------------------------
# 0 is UNKNOWN/filler.  "OUR_"/"ENEMY_" blocks are 29 codes each.  Facings use
# cardinal order N,E,S,W and eight-direction order N,NE,E,SE,S,SW,W,NW.
_CARDINALS = ("N", "E", "S", "W")
_EIGHT = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _team_block(prefix: str) -> list[str]:
    names = [f"{prefix}HARVESTER", f"{prefix}BARRIER"]
    names += [f"{prefix}CONVEYOR_{d}" for d in _CARDINALS]
    names += [f"{prefix}SPLITTER_{d}" for d in _CARDINALS]
    names += [f"{prefix}GUNNER_{d}" for d in _EIGHT]
    names += [f"{prefix}SENTINEL_{d}" for d in _EIGHT]
    names += [f"{prefix}LAUNCHER", f"{prefix}CORE", f"{prefix}BUILDER_BOT"]
    return names                                             # 29 names


TILE_STATES: tuple[str, ...] = tuple(
    ["UNKNOWN", "EMPTY", "WALL", "ORE_FREE"]                 # 4  terrain
    + _team_block("OUR_")                                    # 29 ours
    + _team_block("ENEMY_")                                  # 29 theirs
    + [f"OUR_BOT_ON_CONVEYOR_{d}" for d in _CARDINALS]       # 4  combos ours
    + [f"ENEMY_BOT_ON_CONVEYOR_{d}" for d in _CARDINALS]     # 4  combos theirs
    + ["TOOK_FIRE_HERE", "CONVEYOR_ISSUE", "HARVESTER_ISSUE"]  # 3 overlays
)
# Codes 73..102 are spare; 103..105 are the escape codes.
S_ALPHABET = 106
ESCAPE_RUN = 103
ESCAPE_REMOTE = 104
ESCAPE_CONTROL = 105
ESCAPES = (ESCAPE_RUN, ESCAPE_REMOTE, ESCAPE_CONTROL)

STATE_CODE: dict[str, int] = {name: i for i, name in enumerate(TILE_STATES)}
assert len(TILE_STATES) == 73 and len(STATE_CODE) == 73
assert max(STATE_CODE.values()) < ESCAPE_RUN <= S_ALPHABET - 3

# CONVEYOR_ISSUE / HARVESTER_ISSUE are a *status overlay*: the receiver keeps
# the building it already recorded on the tile and merely flags it.
OVERLAY_STATES = frozenset(
    {STATE_CODE["TOOK_FIRE_HERE"], STATE_CODE["CONVEYOR_ISSUE"],
     STATE_CODE["HARVESTER_ISSUE"]}
)

# ---------------------------------------------------------------------------
# Field vocabulary
# ---------------------------------------------------------------------------
# move (radix 5)  — Builder Bots only: the move made last round.  Readers
#                   dead-reckon the sender's position from these.
MOVE_VALUES = ("NONE", "N", "E", "S", "W")
# turn (radix 3)  — Gunners only (the engine's rotate() is Gunner-only;
#                   Sentinels cannot rotate).  Our gunners rotate at most one
#                   step per round by convention, so this is complete.
TURN_VALUES = ("NONE", "CW", "CCW")
# speaker (radix 2) — turret/launcher slots only: 1 = the Core is speaking
#                   through this slot (onboarding, absolute coordinates).
SPEAKER_VALUES = ("SELF", "CORE")
# aux (radix 16)  — Builder Bots only: a GCS slot id.  When a fact in the same
#                   message names a friendly turret/launcher, aux grants that
#                   unit this slot (0 = no grant; slot 0 is the Core's and can
#                   never be granted).
AUX_NO_GRANT = 0
# States that make a Builder Bot's aux digit mean "this unit is granted a slot".
GRANT_STATES = frozenset(
    STATE_CODE[n] for n in STATE_CODE
    if n.startswith(("OUR_GUNNER_", "OUR_SENTINEL_")) or n == "OUR_LAUNCHER"
)

# ---------------------------------------------------------------------------
# Per-sender-type message layouts (standard format)
# ---------------------------------------------------------------------------
# Each layout is a tuple of (field_name, radix); "fact" radix is
# FOV_TILES[kind] * S_ALPHABET.  Fields are packed most-significant first.
# Nobody carries a field it cannot use (Sentinels have no turn — they cannot
# rotate; only builders move; only builders grant slots).


def fact_radix(kind: str) -> int:
    return FOV_TILES[kind] * S_ALPHABET


LAYOUTS: dict[str, tuple[tuple[str, int], ...]] = {
    "builder_bot": (
        ("move", 5),
        ("fact_a", fact_radix("builder_bot")),
        ("fact_b", fact_radix("builder_bot")),
        ("aux", 16),
    ),
    "gunner": (
        ("speaker", 2),
        ("turn", 3),
        ("fact_a", fact_radix("gunner")),
        ("fact_b", fact_radix("gunner")),
    ),
    "sentinel": (
        ("speaker", 2),
        ("fact_a", fact_radix("sentinel")),
        ("fact_b", fact_radix("sentinel")),
    ),
    "launcher": (
        ("speaker", 2),
        ("fact_a", fact_radix("launcher")),
        ("fact_b", fact_radix("launcher")),
    ),
    "core": (
        ("fact_a", fact_radix("core")),
        ("fact_b", fact_radix("core")),
    ),
}

# Capacity check: every layout must fit the payload space.  Import fails loudly
# if the alphabet or a layout outgrows the budget.
for _kind, _layout in LAYOUTS.items():
    _cost = 1
    for _, _radix in _layout:
        _cost *= _radix
    assert _cost <= PAYLOAD_SPACE, (
        f"layout for {_kind} needs {_cost} values, only {PAYLOAD_SPACE} exist"
    )

# ---------------------------------------------------------------------------
# CONTROL escape
# ---------------------------------------------------------------------------
# When fact_a's state is ESCAPE_CONTROL, fact_a's index digit and every field
# after fact_a are read together as one integer  combined = kind * CTRL_ARGS_CAP
# + args,  where CTRL_ARGS_CAP is the sender's combined trailing capacity
# divided by CONTROL_KINDS (computed in messages.py).
CONTROL_KINDS = 8
CTRL_ASSIGN = 0     # args = slot(16) * period(8) * phase(8)   [Core only]
CTRL_SYMMETRY = 1   # args = kind(3)                           [Core only]
CTRL_DIRECTIVE = 2  # args = x(W) * y(H) * task(24)
# kinds 3..7 spare

ASSIGN_ARG_RADICES = (16, 8, 8)        # slot, period, phase
SYMMETRY_KINDS = ("MIRROR_X", "MIRROR_Y", "ROT_180")   # args radix 3
# MIRROR_X:  (x, y) -> (W-1-x, y);  MIRROR_Y: (x, y) -> (x, H-1-y);
# ROT_180:   (x, y) -> (W-1-x, H-1-y).
# SYMMETRY carries no coordinates: every unit knows its own Core's position,
# and the enemy Core follows from applying the symmetry to it.

# DIRECTIVE task table (addressing is folded into the task value):
#   0      FIX_HARVESTER   Core or any builder; unaddressed (best-placed acts)
#   1-15   FIX_CONVEYOR    Core only; value k addresses the builder in slot k
#   16-18  BUILD_HERE / SCOUT_HERE / DEFEND_HERE   Core; unaddressed
#   19-23  spare
TASK_RADIX = 24
TASK_FIX_HARVESTER = 0
TASK_FIX_CONVEYOR_BASE = 1       # +slot  (1..15)
TASK_BUILD_HERE = 16
TASK_SCOUT_HERE = 17
TASK_DEFEND_HERE = 18

# ---------------------------------------------------------------------------
# RUN escape
# ---------------------------------------------------------------------------
# fact_a's index = start tile (a FOV index of the sender); the combined
# trailing capacity is read as  dir(4) * length * state(S), where the maximum
# length is computed per sender as   trailing_capacity // (4 * S)   capped at
# the map diagonal.  Directions use cardinal order N,E,S,W.
RUN_DIR_RADIX = 4

# ---------------------------------------------------------------------------
# REMOTE escape
# ---------------------------------------------------------------------------
# The combined trailing capacity (fact_a's index digit folded in) is read as
# absolute  x(W) * y(H) * state(S)  for one fact outside the sender's FOV.

# ---------------------------------------------------------------------------
# RESYNC round format
# ---------------------------------------------------------------------------
# The round after an ASSIGN becomes readable, every unit writes
#   pos(W*H) * fact(FOV*S)
# — its absolute position plus one ordinary fact.  The newborn's first-ever
# message uses the same format.  Readers know the round from having decoded
# the ASSIGN, so the format costs no header.

# ---------------------------------------------------------------------------
# Onboarding chain format (Core speaking, absolute coordinates)
# ---------------------------------------------------------------------------
# In the Core's own slot during onboarding, and in turret/launcher slots with
# speaker=1, the payload is a chain:
#   abs fact:  pos(W*H) * state(S)
#   rel fact:  1 + offset((2r+1)^2 - 1) * state(S)    (0 = "no second fact")
# where r is the largest radius whose chain still fits the sender's capacity.
# Computed per map in messages.py; on 30x30 this gives r=6 (168 offsets) for
# the Core slot and turret slots alike.


def dump_protocol() -> str:
    """Render the whole wire format as markdown tables (the spec, generated)."""
    out = ["# GCS wire protocol (generated from protocol.py)", ""]
    out += ["## Reserved raw values", "",
            f"- payload space: 0 .. {PAYLOAD_SPACE - 1}",
            f"- IDLE_A={IDLE_A}, IDLE_B={IDLE_B} (alternating heartbeat)",
            f"- free: {RESERVED_FREE_1}, {RESERVED_FREE_2}",
            f"- Core HP block: {CORE_HP_BASE} + h (h=0..{CORE_HP_MAX}), "
            f"announced on >{CORE_HP_ANNOUNCE_DRIFT} HP drift", ""]
    out += ["## Layouts (most-significant field first)", "",
            "| sender | layout | cost | headroom |", "|---|---|---|---|"]
    for kind, layout in LAYOUTS.items():
        cost = 1
        for _, radix in layout:
            cost *= radix
        desc = " · ".join(f"{n}({r})" for n, r in layout)
        out.append(f"| {kind} | {desc} | {cost:,} | "
                   f"{PAYLOAD_SPACE / cost:.2f}x |")
    out += ["", "## Tile states", "",
            "| code | name |", "|---|---|"]
    for i, name in enumerate(TILE_STATES):
        out.append(f"| {i} | {name} |")
    out += [f"| {ESCAPE_RUN} | ESCAPE_RUN |",
            f"| {ESCAPE_REMOTE} | ESCAPE_REMOTE |",
            f"| {ESCAPE_CONTROL} | ESCAPE_CONTROL |",
            f"| 73..102 | (spare) |", ""]
    out += ["## Field values", "",
            f"- move: {', '.join(f'{i}={v}' for i, v in enumerate(MOVE_VALUES))}",
            f"- turn: {', '.join(f'{i}={v}' for i, v in enumerate(TURN_VALUES))}"
            "  (Gunners only; one step per round by convention)",
            f"- speaker: {', '.join(f'{i}={v}' for i, v in enumerate(SPEAKER_VALUES))}",
            "- aux: GCS slot id granted to the friendly turret/launcher named "
            "by a fact in the same message; 0 = no grant", ""]
    out += ["## Control kinds", "",
            "| kind | args |", "|---|---|",
            "| ASSIGN | slot(16) · period(8) · phase(8) |",
            "| SYMMETRY | kind(3): MIRROR_X / MIRROR_Y / ROT_180 |",
            "| DIRECTIVE | x(W) · y(H) · task(24) |", "",
            "task: 0=FIX_HARVESTER (unaddressed, any sender), "
            "1-15=FIX_CONVEYOR for the builder in that slot (Core only), "
            "16=BUILD_HERE, 17=SCOUT_HERE, 18=DEFEND_HERE, 19-23 spare", ""]
    return "\n".join(out)
