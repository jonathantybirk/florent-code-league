"""Build and parse GCS messages.

Stateless: every function takes the sender's entity kind, the sender's
position (facts are FOV-relative), and the live map size.  All format
knowledge comes from protocol.py; all packing from codec.py.

Encoders return None instead of raising when a message cannot be expressed —
callers degrade (drop facts) or fall back to the idle heartbeat.  Decoders
raise CodecError on malformed input; the facade catches and reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import codec, fov
from .codec import CodecError
from .protocol import (
    ASSIGN_ARG_RADICES,
    CONTROL_KINDS,
    CORE_HP_BASE,
    CORE_HP_MAX,
    CTRL_ASSIGN,
    CTRL_DIRECTIVE,
    CTRL_SYMMETRY,
    ESCAPE_CONTROL,
    ESCAPE_REMOTE,
    ESCAPE_RUN,
    FOV_TILES,
    IDLE_A,
    IDLE_B,
    LAYOUTS,
    PAYLOAD_SPACE,
    RUN_DIR_RADIX,
    S_ALPHABET,
    STATE_CODE,
    TASK_RADIX,
)

UNKNOWN = STATE_CODE["UNKNOWN"]
# cardinal order used by the RUN escape and the move digit: N, E, S, W
CARDINAL_DELTAS = ((0, -1), (1, 0), (0, 1), (-1, 0))


@dataclass(frozen=True)
class Fact:
    """One tile of knowledge in absolute map coordinates."""
    x: int
    y: int
    state: int          # index into protocol.TILE_STATES


@dataclass(frozen=True)
class ControlEvent:
    kind: int           # CTRL_ASSIGN / CTRL_SYMMETRY / CTRL_DIRECTIVE
    args: tuple[int, ...]


@dataclass
class Decoded:
    """Everything one slot value said this round."""
    facts: list[Fact] = field(default_factory=list)
    move: int = 0               # MOVE_VALUES index (builders)
    turn: int = 0               # TURN_VALUES index (gunners)
    speaker: int = 0            # SPEAKER_VALUES index (turret/launcher slots)
    aux: int = 0                # slot grant (builders; 0 = none)
    events: list[ControlEvent] = field(default_factory=list)
    position: tuple[int, int] | None = None   # absolute pos (resync messages)


# ---------------------------------------------------------------------------
# layout helpers
# ---------------------------------------------------------------------------

def _radices(kind: str) -> tuple[tuple[str, ...], tuple[int, ...]]:
    names, radices = zip(*LAYOUTS[kind])
    return names, radices


def _fact_a_pos(kind: str) -> int:
    names, _ = _radices(kind)
    return names.index("fact_a")


def _trailing_capacity(kind: str) -> int:
    """FOV * (product of radices after fact_a): the combined space escapes use."""
    names, radices = _radices(kind)
    i = names.index("fact_a")
    after = 1
    for r in radices[i + 1:]:
        after *= r
    return FOV_TILES[kind] * after, after


def run_max_len(kind: str, map_w: int, map_h: int) -> int:
    """Longest run this sender can express (capped by the map's longer side)."""
    _, after = _trailing_capacity(kind)
    return min(after // (RUN_DIR_RADIX * S_ALPHABET), max(map_w, map_h))


def ctrl_args_cap(kind: str) -> int:
    total, _ = _trailing_capacity(kind)
    return total // CONTROL_KINDS


# ---------------------------------------------------------------------------
# raw (reserved) values
# ---------------------------------------------------------------------------

def classify_raw(value: int):
    """('idle'|'core_hp'|'free'|'payload', detail) for a slot value."""
    if value in (IDLE_A, IDLE_B):
        return "idle", None
    if CORE_HP_BASE <= value < CORE_HP_BASE + CORE_HP_MAX + 1:
        return "core_hp", value - CORE_HP_BASE
    if value >= PAYLOAD_SPACE:
        return "free", value
    return "payload", value


def core_hp_value(hp: int) -> int:
    return CORE_HP_BASE + max(0, min(CORE_HP_MAX, hp))


# ---------------------------------------------------------------------------
# standard format
# ---------------------------------------------------------------------------

def _fact_digit(kind: str, sender_pos, f: Fact | None) -> int | None:
    """FOV-relative digit for a fact, or 0 (index 0, UNKNOWN) as filler.

    Returns None if the fact's tile is outside the sender's disc.
    """
    if f is None:
        return 0
    idx = fov.index_of(kind, f.x - sender_pos[0], f.y - sender_pos[1])
    if idx is None or not 0 <= f.state < S_ALPHABET:
        return None
    return idx * S_ALPHABET + f.state


def encode_standard(kind: str, sender_pos, facts, *, move=0, turn=0, aux=0, parity=0):
    """Pack up to two FOV-relative facts plus the sender's prefix fields.

    facts: list of Fact (absolute coords).  Unencodable facts are skipped;
    returns (value, facts_actually_encoded) or (None, []) if nothing packs.

    parity (0/1) is the FOV index of the filler used for a missing fact.
    Receivers ignore UNKNOWN-state facts whatever their index, so toggling it
    lets a unit with nothing new to say still send its move/turn digits every
    round without ever repeating a value (the liveness rule).
    """
    usable: list[Fact] = []
    digits_ab: list[int] = []
    for f in facts:
        if len(usable) == 2:
            break
        d = _fact_digit(kind, sender_pos, f)
        if d is not None and f.state not in (ESCAPE_RUN, ESCAPE_REMOTE, ESCAPE_CONTROL):
            usable.append(f)
            digits_ab.append(d)
    while len(digits_ab) < 2:
        digits_ab.append(parity * S_ALPHABET)   # filler: state UNKNOWN, ignored

    names, radices = _radices(kind)
    values = {"move": move, "turn": turn, "speaker": 0, "aux": aux,
              "fact_a": digits_ab[0], "fact_b": digits_ab[1]}
    try:
        return codec.pack([values[n] for n in names], radices), usable
    except ValueError:
        return None, []


def _decode_fact(kind: str, sender_pos, digit: int) -> Fact | None:
    idx, state = divmod(digit, S_ALPHABET)
    if state == UNKNOWN:
        return None                       # filler
    dx, dy = fov.offset_of(kind, idx)
    return Fact(sender_pos[0] + dx, sender_pos[1] + dy, state)


def decode_standard(kind: str, value: int, sender_pos, map_w: int, map_h: int) -> Decoded:
    """Decode a standard-format payload.

    sender_pos must be the sender's position *after* applying this message's
    move digit — for builders the caller dead-reckons first (peek the move
    with peek_move()), for static units it is their known tile.
    """
    names, radices = _radices(kind)
    digits = dict(zip(names, codec.unpack(value, radices)))
    out = Decoded(move=digits.get("move", 0), turn=digits.get("turn", 0),
                  speaker=digits.get("speaker", 0), aux=digits.get("aux", 0))

    state_a = digits["fact_a"] % S_ALPHABET
    if state_a in (ESCAPE_RUN, ESCAPE_REMOTE, ESCAPE_CONTROL):
        _decode_escape(kind, state_a, digits, sender_pos, map_w, map_h, out)
        return out

    for key in ("fact_a", "fact_b"):
        f = _decode_fact(kind, sender_pos, digits[key])
        if f is not None and 0 <= f.x < map_w and 0 <= f.y < map_h:
            out.facts.append(f)
    return out


def peek_move(kind: str, value: int) -> int:
    """Read just the move digit so the caller can dead-reckon before decoding."""
    names, radices = _radices(kind)
    if "move" not in names:
        return 0
    return codec.unpack(value, radices)[names.index("move")]


# ---------------------------------------------------------------------------
# escapes: shared combined-space plumbing
# ---------------------------------------------------------------------------

def _encode_with_combined(kind: str, escape_state: int, idx: int, combined_trailing: int,
                          *, move=0, turn=0):
    """Pack a message whose fact_a carries (idx, escape_state) and whose
    fields after fact_a jointly hold combined_trailing."""
    names, radices = _radices(kind)
    a = names.index("fact_a")
    trailing = list(codec.unpack(combined_trailing, radices[a + 1:])) if a + 1 < len(names) else []
    values = {"move": move, "turn": turn, "speaker": 0,
              "fact_a": idx * S_ALPHABET + escape_state}
    digits = []
    for i, n in enumerate(names):
        if i <= a:
            digits.append(values.get(n, 0))
        else:
            digits.append(trailing[i - a - 1])
    try:
        return codec.pack(digits, radices)
    except ValueError:
        return None


def _combined_parts(kind: str, digits: dict) -> tuple[int, int]:
    """(fact_a index, combined value of all fields after fact_a)."""
    names, radices = _radices(kind)
    a = names.index("fact_a")
    combined = 0
    for i in range(a + 1, len(names)):
        combined = combined * radices[i] + digits[names[i]]
    return digits["fact_a"] // S_ALPHABET, combined


def _decode_escape(kind, state, digits, sender_pos, map_w, map_h, out: Decoded):
    idx, trailing = _combined_parts(kind, digits)
    _, after = _trailing_capacity(kind)

    if state == ESCAPE_RUN:
        max_len = run_max_len(kind, map_w, map_h)
        d, rest = divmod(trailing, max_len * S_ALPHABET)
        length_m1, run_state = divmod(rest, S_ALPHABET)
        if d >= RUN_DIR_RADIX:
            raise CodecError("run direction out of range")
        dx0, dy0 = fov.offset_of(kind, idx)
        sx, sy = sender_pos[0] + dx0, sender_pos[1] + dy0
        ddx, ddy = CARDINAL_DELTAS[d]
        for i in range(length_m1 + 1):
            x, y = sx + i * ddx, sy + i * ddy
            if 0 <= x < map_w and 0 <= y < map_h:
                out.facts.append(Fact(x, y, run_state))

    elif state == ESCAPE_REMOTE:
        combined = idx * after + trailing
        x, rest = divmod(combined, map_h * S_ALPHABET)
        y, r_state = divmod(rest, S_ALPHABET)
        if 0 <= x < map_w and 0 <= y < map_h:
            out.facts.append(Fact(x, y, r_state))

    elif state == ESCAPE_CONTROL:
        combined = idx * after + trailing
        cap = ctrl_args_cap(kind)
        ckind, args_val = divmod(combined, cap)
        if ckind == CTRL_ASSIGN:
            out.events.append(ControlEvent(CTRL_ASSIGN,
                                           codec.unpack(args_val, ASSIGN_ARG_RADICES)))
        elif ckind == CTRL_SYMMETRY:
            out.events.append(ControlEvent(CTRL_SYMMETRY, (args_val,)))
        elif ckind == CTRL_DIRECTIVE:
            x, rest = divmod(args_val, map_h * TASK_RADIX)
            y, task = divmod(rest, TASK_RADIX)
            out.events.append(ControlEvent(CTRL_DIRECTIVE, (x, y, task)))
        else:
            raise CodecError(f"unknown control kind {ckind}")


# ---------------------------------------------------------------------------
# escape encoders
# ---------------------------------------------------------------------------

def encode_run(kind: str, sender_pos, start: tuple[int, int], direction: int,
               length: int, state: int, map_w: int, map_h: int, *, move=0, turn=0):
    """A run of `length` same-state tiles from `start` (in the sender's FOV)."""
    idx = fov.index_of(kind, start[0] - sender_pos[0], start[1] - sender_pos[1])
    max_len = run_max_len(kind, map_w, map_h)
    if idx is None or not 1 <= length <= max_len or not 0 <= direction < RUN_DIR_RADIX:
        return None
    trailing = (direction * max_len + (length - 1)) * S_ALPHABET + state
    return _encode_with_combined(kind, ESCAPE_RUN, idx, trailing, move=move, turn=turn)


def encode_remote(kind: str, f: Fact, map_w: int, map_h: int, *, move=0, turn=0):
    """One absolute-coordinate fact outside the sender's FOV."""
    if not (0 <= f.x < map_w and 0 <= f.y < map_h and 0 <= f.state < S_ALPHABET):
        return None
    combined = (f.x * map_h + f.y) * S_ALPHABET + f.state
    _, after = _trailing_capacity(kind)
    return _encode_with_combined(kind, ESCAPE_REMOTE, combined // after,
                                 combined % after, move=move, turn=turn)


def encode_control(kind: str, ckind: int, args_val: int, *, move=0, turn=0):
    cap = ctrl_args_cap(kind)
    if args_val >= cap:
        return None
    combined = ckind * cap + args_val
    _, after = _trailing_capacity(kind)
    return _encode_with_combined(kind, ESCAPE_CONTROL, combined // after,
                                 combined % after, move=move, turn=turn)


def assign_args(slot: int, period: int = 1, phase: int = 0) -> int:
    return codec.pack((slot, period, phase), ASSIGN_ARG_RADICES)


def directive_args(x: int, y: int, task: int, map_h: int) -> int:
    return (x * map_h + y) * TASK_RADIX + task


# ---------------------------------------------------------------------------
# resync format:  pos(W*H) * fact(FOV*S)
# ---------------------------------------------------------------------------

def encode_resync(kind: str, pos: tuple[int, int], f: Fact | None,
                  map_w: int, map_h: int):
    fact_digit = _fact_digit(kind, pos, f)
    if fact_digit is None:
        fact_digit = 0
    radices = (map_w * map_h, FOV_TILES[kind] * S_ALPHABET)
    try:
        return codec.pack((pos[0] * map_h + pos[1], fact_digit), radices)
    except ValueError:
        return None


def decode_resync(kind: str, value: int, map_w: int, map_h: int) -> Decoded:
    radices = (map_w * map_h, FOV_TILES[kind] * S_ALPHABET)
    pos_v, fact_digit = codec.unpack(value, radices)
    pos = divmod(pos_v, map_h)
    out = Decoded(position=pos)
    f = _decode_fact(kind, pos, fact_digit)
    if f is not None and 0 <= f.x < map_w and 0 <= f.y < map_h:
        out.facts.append(f)
    return out


# ---------------------------------------------------------------------------
# onboarding chain (Core speaking; absolute + one delta-chained fact)
# ---------------------------------------------------------------------------

def chain_params(map_w: int, map_h: int, borrowed_slot: bool) -> tuple[int, int]:
    """(delta radius r, rel-digit radix) for the onboarding chain.

    borrowed_slot=True halves the capacity for the turret slot's speaker bit.
    r is the largest Chebyshev radius whose chain still fits; the rel digit is
    1 + n_offsets*S with value 0 meaning "no second fact".
    """
    cap = PAYLOAD_SPACE // (2 if borrowed_slot else 1)
    abs_radix = map_w * map_h * S_ALPHABET
    budget = cap // abs_radix
    r = 0
    while True:
        n_off = (2 * (r + 1) + 1) ** 2 - 1
        if 1 + n_off * S_ALPHABET > budget:
            break
        r += 1
    n_off = (2 * r + 1) ** 2 - 1
    return r, 1 + n_off * S_ALPHABET


def _delta_offsets(r: int) -> list[tuple[int, int]]:
    return [(dx, dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1)
            if (dx, dy) != (0, 0)]


def encode_onboard(abs_fact: Fact, rel_fact: Fact | None,
                   map_w: int, map_h: int, borrowed_slot: bool):
    """Chain of one absolute fact plus an optional near-by second fact."""
    r, rel_radix = chain_params(map_w, map_h, borrowed_slot)
    rel_digit = 0
    if rel_fact is not None:
        dx, dy = rel_fact.x - abs_fact.x, rel_fact.y - abs_fact.y
        offs = _delta_offsets(r)
        if (dx, dy) in dict.fromkeys(offs) and max(abs(dx), abs(dy)) <= r:
            rel_digit = 1 + offs.index((dx, dy)) * S_ALPHABET + rel_fact.state
    abs_digit = (abs_fact.x * map_h + abs_fact.y) * S_ALPHABET + abs_fact.state
    radices = [map_w * map_h * S_ALPHABET, rel_radix]
    digits = [abs_digit, rel_digit]
    if borrowed_slot:
        radices.insert(0, 2)
        digits.insert(0, 1)     # speaker = CORE
    try:
        return codec.pack(digits, radices)
    except ValueError:
        return None


def decode_onboard(value: int, map_w: int, map_h: int, borrowed_slot: bool) -> Decoded:
    r, rel_radix = chain_params(map_w, map_h, borrowed_slot)
    radices = [map_w * map_h * S_ALPHABET, rel_radix]
    if borrowed_slot:
        radices.insert(0, 2)
    digits = codec.unpack(value, radices)
    if borrowed_slot:
        speaker, abs_digit, rel_digit = digits
        if speaker == 0:
            # the turret itself is speaking: not an onboarding payload after all
            raise CodecError("speaker=SELF in onboarding decode")
    else:
        abs_digit, rel_digit = digits
    pos_v, state = divmod(abs_digit, S_ALPHABET)
    x, y = divmod(pos_v, map_h)
    out = Decoded(speaker=1)
    if 0 <= x < map_w and 0 <= y < map_h:
        out.facts.append(Fact(x, y, state))
    if rel_digit:
        off_i, rel_state = divmod(rel_digit - 1, S_ALPHABET)
        dx, dy = _delta_offsets(r)[off_i]
        rx, ry = x + dx, y + dy
        if 0 <= rx < map_w and 0 <= ry < map_h:
            out.facts.append(Fact(rx, ry, rel_state))
    return out
