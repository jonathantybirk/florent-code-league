"""Core meta-command broadcasting: scaffolding for the Core to distill
whatever it alone can see -- its own wide vision (vision radius^2 = 36,
easily the widest of any unit), plus anything teammates have already
reported into the Communication Store -- into one directive value, and
broadcast that to GCS slot 0 for every other unit to read at the top of
its own run(). See README.md for the trigger-priority design, worked
examples, and why this lives in the Core rather than being decided
independently by each unit.

Pure logic, no run() of its own -- meant to be called from a real Core's
run(), e.g.:

    if ct.get_entity_type() == EntityType.CORE:
        broadcast_meta_command(ct, MY_TRIGGERS)

and from every other unit's run():

    command = read_meta_command(ct)
    if command == MetaCommand.DEFEND:
        ...
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable

from fcode import Controller, EntityType

# Default GCS slot this module reads/writes. Override via the `slot`
# argument on broadcast_meta_command/read_meta_command if a bot's own
# layout already claims slot 0 for something else.
SLOT_META_COMMAND = 0


class MetaCommand(IntEnum):
    """Starter vocabulary -- extend or replace freely with a bot-specific
    IntEnum of your own. The scaffolding below doesn't interpret these
    values at all, it only needs them to be small non-negative ints (the
    GCS's own constraint, see docs/official/docs/global-comms.txt). HOLD
    is deliberately 0: every slot starts at 0 before the Core ever writes
    (see read_meta_command), so "no directive yet" and "explicitly told to
    hold" collapse into the same, harmless default.
    """

    HOLD = 0
    DEFEND = 1
    RALLY = 2
    EXPAND = 3
    RETREAT = 4
    ATTACK = 5


@dataclass(frozen=True)
class Trigger:
    """One rule: if condition(ct) is true, command is a candidate this
    round, competing against every other Trigger whose condition also
    matched. The highest-priority match wins; a tie keeps whichever
    Trigger appears first in the list passed to evaluate/broadcast.
    """

    command: MetaCommand
    priority: int
    condition: Callable[[Controller], bool]


def evaluate_meta_command(
    ct: Controller,
    triggers: list[Trigger],
    default: MetaCommand = MetaCommand.HOLD,
) -> MetaCommand:
    """The highest-priority Trigger whose condition currently holds, or
    default if none do.

    Doesn't touch the store -- see broadcast_meta_command for the
    Core-only entry point that also writes the result. Kept separate so a
    bot can preview the outcome (logging, a resign() message, deciding
    whether a write is even worth it) without committing a write.

    Every trigger is evaluated once, in list order, with no short-circuit
    once a winner is found -- triggers is expected to hold a handful of
    entries, not run as a hot inner loop, so this favours predictable
    (condition always called) over marginally cheaper.
    """
    best: MetaCommand | None = None
    best_priority: int | None = None
    for trigger in triggers:
        if best_priority is not None and trigger.priority <= best_priority:
            continue
        if trigger.condition(ct):
            best, best_priority = trigger.command, trigger.priority
    return best if best is not None else default


def broadcast_meta_command(
    ct: Controller,
    triggers: list[Trigger],
    default: MetaCommand = MetaCommand.HOLD,
    slot: int = SLOT_META_COMMAND,
) -> MetaCommand:
    """Core only: evaluate triggers and write the winning command to slot.

    Call once per round from the Core's own run(). Like every store write,
    this is buffered: teammates reading slot this round still see last
    round's value, and only see this round's write starting next round
    (docs/official/docs/global-comms.txt) -- design triggers assuming a
    one-round-old world by the time anyone reacts to them.
    """
    if ct.get_entity_type() != EntityType.CORE:
        raise ValueError("broadcast_meta_command must be called from the Core's own turn")
    command = evaluate_meta_command(ct, triggers, default)
    ct.write_store(slot, int(command))
    return command


def read_meta_command(
    ct: Controller,
    slot: int = SLOT_META_COMMAND,
    default: MetaCommand = MetaCommand.HOLD,
) -> MetaCommand:
    """Any unit: the last-committed meta command, or default if the raw
    value in slot isn't a known MetaCommand member.

    That fallback covers more than "the Core hasn't written yet" (which
    reads as 0 = HOLD anyway): it also guards a custom vocabulary passed
    to broadcast_meta_command where 0 isn't the intended first member, and
    a stale value left by a differently-versioned Core after a vocabulary
    change mid-development.
    """
    raw = ct.read_store(slot)
    try:
        return MetaCommand(raw)
    except ValueError:
        return default
