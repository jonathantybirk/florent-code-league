"""The 16-slot shared store, used as a plain blackboard.

This is deliberately not the full GCS wire protocol in `utils/GCS`. That
protocol streams map facts and is worth its complexity once units are far
enough apart to have genuinely different maps; what the economy needs first is
three scalars and a claim board, and mixing the two would make an untested
encoder a dependency of the opening. The GCS goes in behind this interface
once it has games behind it.

Writes are buffered: a value written in round N is readable in round N+1. Two
places depend on that one-round lag and would be wrong without it:

  * `claim_index` -- the Core writes the running spawn count *after* each
    spawn, so a newborn Builder reading the slot on its first round sees the
    count from before it existed. That is its index, with no handshake.
  * `claimed` -- every Builder sees the same claim board for the whole round
    regardless of who acts first, so two Builders cannot both believe a
    deposit is free because of turn order.
"""

SLOT_SPAWN_COUNT = 0
SLOT_SYMMETRY = 1
SLOT_ALARM = 2
CLAIM_BASE = 3
CLAIM_SLOTS = 6           # slots 3..8
ORE_BASE = 9
ORE_SLOTS = 6             # slots 9..14
SLOT_SIEGE = 15


def claim_index(ct) -> int:
    """This Builder's spawn order, read on its first round."""
    return _read(ct, SLOT_SPAWN_COUNT)


def note_spawn(ct, count: int) -> None:
    _write(ct, SLOT_SPAWN_COUNT, count)


def alarm(ct) -> bool:
    return _read(ct, SLOT_ALARM) != 0


def alarm_level(ct) -> int:
    """How many Builders the Core wants at home; 0 when calm."""
    return _read(ct, SLOT_ALARM)


def raise_alarm(ct, menders: int) -> None:
    _write(ct, SLOT_ALARM, max(1, menders))


def clear_alarm(ct) -> None:
    _write(ct, SLOT_ALARM, 0)


def publish_symmetry(ct, kind: int) -> None:
    _write(ct, SLOT_SYMMETRY, kind + 1)


def symmetry(ct):
    value = _read(ct, SLOT_SYMMETRY)
    return value - 1 if value else None


# ----------------------------------------------------------------------
# deposit claims
# ----------------------------------------------------------------------
def claim(ct, index, deposit) -> None:
    if index is None:
        return
    _write(ct, CLAIM_BASE + index % CLAIM_SLOTS, _pack(deposit))


def claimed(ct, index) -> set:
    """Deposits other Builders have claimed."""
    mine = None if index is None else CLAIM_BASE + index % CLAIM_SLOTS
    out = set()
    for slot in range(CLAIM_BASE, CLAIM_BASE + CLAIM_SLOTS):
        if slot == mine:
            continue
        tile = _unpack(_read(ct, slot))
        if tile is not None:
            out.add(tile)
    return out


# The siege slot carries two numbers, because there are only 16 and they are
# all spoken for: sentinels in the high field, our team's measured income in
# tenths of a titanium per round in the low one. Income has to travel because
# only the Core can measure it (it watches the team balance) and only a
# harasser, twenty tiles away in the enemy half, needs to act on it.
_INCOME_RADIX = 4096


def team_income(ct) -> float:
    """Titanium a round arriving, as the Core last measured it."""
    return (_read(ct, SLOT_SIEGE) % _INCOME_RADIX) / 10.0


def note_economy(ct, sentinels: int, income: float) -> None:
    tenths = max(0, min(_INCOME_RADIX - 1, int(income * 10)))
    _write(ct, SLOT_SIEGE, sentinels * _INCOME_RADIX + tenths)


def siege_sentinels(ct) -> int:
    """Sentinels our attackers have planted at the enemy Core.

    The Core cannot see them -- they are five tiles from the *enemy* base,
    far outside its vision -- so it cannot decide whether to convert
    ammunition without being told. This is that channel.
    """
    return _read(ct, SLOT_SIEGE) // _INCOME_RADIX


def note_sentinel(ct, built: int) -> None:
    _write(ct, SLOT_SIEGE, built * _INCOME_RADIX + (_read(ct, SLOT_SIEGE) % _INCOME_RADIX))


# ----------------------------------------------------------------------
# the ore bulletin
# ----------------------------------------------------------------------
def ore_board(ct) -> list:
    """Deposits any unit has reported, as tiles."""
    out = []
    for slot in range(ORE_BASE, ORE_BASE + ORE_SLOTS):
        tile = _unpack(_read(ct, slot))
        if tile is not None:
            out.append(tile)
    return out


def publish_ore(ct, index, tile) -> None:
    """Put one deposit on the bulletin.

    Each unit owns a slot by index so two reporters do not silently overwrite
    one another every round. A collision between units sharing a slot costs
    one report, which the next round re-sends.
    """
    if index is None:
        return
    _write(ct, ORE_BASE + index % ORE_SLOTS, _pack(tile))


def _pack(tile) -> int:
    return tile[0] * 32 + tile[1] + 1


def _unpack(value):
    if not value:
        return None
    value -= 1
    return (value // 32, value % 32)


def _read(ct, slot: int) -> int:
    try:
        return ct.read_store(slot)
    except Exception:
        return 0


def _write(ct, slot: int, value: int) -> None:
    try:
        ct.write_store(slot, value)
    except Exception:
        pass
